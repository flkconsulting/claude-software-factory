import json
import shutil
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
        import os
        e = dict(os.environ)
        e["HOME"] = str(home)
        e["SF_HEAVY_POLL"] = "0.2"
        return e, tmp_path / "state" / "heavy"
    return make


def run(args, e, **kw):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=30, **kw)


def hold(lock, seconds):
    lock.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["flock", str(lock), "sleep", str(seconds)])
    time.sleep(0.5)
    return p


def test_no_args_exit_2(env):
    e, _ = env(1)
    r = run([], e)
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_passes_exit_code(env):
    e, _ = env(1)
    assert run(["sh", "-c", "exit 7"], e).returncode == 7
    assert run(["true"], e).returncode == 0


def test_second_job_waits_with_one_slot(env, tmp_path):
    e, heavy = env(1)
    holder = hold(heavy / "slot-1.lock", 2)
    try:
        t0 = time.monotonic()
        r = run(["true"], e)
        waited = time.monotonic() - t0
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 0
    assert waited >= 1.0
    assert r.stderr.count("waiting for a heavy-run slot") == 1


def test_two_slots_run_parallel(env):
    e, heavy = env(2)
    holder = hold(heavy / "slot-1.lock", 5)
    try:
        t0 = time.monotonic()
        r = run(["true"], e)
        waited = time.monotonic() - t0
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 0
    assert waited < 2.0
    assert "waiting" not in r.stderr
