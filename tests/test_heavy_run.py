import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "heavy-run.sh"

pytestmark = pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")


@pytest.fixture
def env(tmp_path):
    def make(slots):
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True, exist_ok=True)
        cfg = {"server": {"heavy_slots": slots, "state_dir": str(tmp_path / "state")}}
        (home / ".claude" / "software-factory.json").write_text(json.dumps(cfg), encoding="utf-8")
        e = dict(os.environ)
        e["HOME"] = str(home)
        e["SF_HEAVY_POLL"] = "0.2"
        return e, tmp_path / "state" / "heavy"
    return make


def run(args, e, **kw):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=30, **kw)


def hold(lock, seconds):
    lock.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["flock", str(lock), "sleep", str(seconds)], start_new_session=True)
    time.sleep(0.5)
    return p


def release(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()


def test_no_args_exit_2(env):
    e, _ = env(1)
    r = run([], e)
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_passes_exit_code(env):
    e, _ = env(1)
    assert run(["sh", "-c", "exit 7"], e).returncode == 7
    assert run(["true"], e).returncode == 0


def test_second_job_waits_with_one_slot(env):
    e, heavy = env(1)
    holder = hold(heavy / "slot-1.lock", 2)
    try:
        t0 = time.monotonic()
        r = run(["true"], e)
        waited = time.monotonic() - t0
    finally:
        release(holder)
    assert r.returncode == 0
    assert waited >= 1.0
    assert r.stderr.count("waiting for a heavy-run slot") == 1


def test_two_slots_run_parallel(env):
    e, heavy = env(2)
    holder = hold(heavy / "slot-1.lock", 10)
    try:
        t0 = time.monotonic()
        r = run(["true"], e)
        waited = time.monotonic() - t0
    finally:
        release(holder)
    assert r.returncode == 0
    assert waited < 5.0
    assert "waiting" not in r.stderr


def test_heavy_run_term_waits_for_child(env, tmp_path):
    e, heavy = env(1)
    pidfile = tmp_path / "child.pid"
    p = subprocess.Popen(["bash", str(SCRIPT), "sh", "-c", f"echo $$ > {pidfile}; exec sleep 30"],
                         env=e, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (pidfile.exists() and pidfile.read_text().strip()):
            time.sleep(0.1)
        child = int(pidfile.read_text().strip())
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=10)
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
        # slot lock is free again
        r = subprocess.run(["flock", "-n", str(heavy / "slot-1.lock"), "true"], timeout=10)
        assert r.returncode == 0
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()


def test_heavy_run_invalid_slots_falls_back_to_two(env):
    e, heavy = env(0)
    h1 = hold(heavy / "slot-1.lock", 10)
    h2 = None
    try:
        t0 = time.monotonic()
        r = run(["true"], e)
        assert r.returncode == 0 and time.monotonic() - t0 < 5.0 and "waiting" not in r.stderr
        h2 = hold(heavy / "slot-2.lock", 10)
        p = subprocess.Popen(["bash", str(SCRIPT), "true"], env=e, stderr=subprocess.PIPE, text=True)
        time.sleep(1.5)
        assert p.poll() is None
        release(h1)
        assert p.wait(timeout=10) == 0
    finally:
        release(h1)
        if h2 is not None:
            release(h2)
