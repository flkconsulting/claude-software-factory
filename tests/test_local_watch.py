import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local-watch.sh"
LINE = '{"id": "s1-l1", "strand": "s1", "step": "ext-test", "branch": "feature/x", "commit": "abc1234", "time": "t"}'


@pytest.fixture
def fake(tmp_path):
    """Fake ssh: logs argv to calls.txt, behaviour from `plan` (one word per call, last repeats)."""

    def make(plan, **extra):
        calls = tmp_path / "calls.txt"
        counter = tmp_path / "counter"
        counter.write_text("0", encoding="utf-8")
        ssh = tmp_path / "fakessh"
        ssh.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> "{calls}"\n'
            f'n=$(cat "{counter}"); n=$((n+1)); echo $n > "{counter}"\n'
            f"plan=({' '.join(plan)})\n"
            'i=$((n-1)); [ "$i" -ge "${#plan[@]}" ] && i=$((${#plan[@]}-1))\n'
            'case "${plan[$i]}" in\n'
            "  empty) exit 0 ;;\n"
            f"  line) echo '{LINE}'; exit 0 ;;\n"
            "  fail) exit 255 ;;\n"
            "  nocmd) echo 'bash: sf-status: command not found' >&2; echo >&2; exit 127 ;;\n"
            "  hang) exec sleep 987 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        ssh.chmod(0o755)
        e = dict(os.environ)
        e["SF_LOCAL_WATCH_SSH"] = str(ssh)
        e["SF_LOCAL_WATCH_INTERVAL"] = "0.1"
        e.update(extra)
        return e, calls

    return make


def run(args, e):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=30)


def count(calls):
    return len(calls.read_text().splitlines()) if calls.exists() else 0


@pytest.mark.parametrize("args", [[], ["-oProxyCommand=x", "alpha"], ["host", "Bad;Name"], ["host"], ["host", "alpha", "x"], ["host", "alpha\nx"], ["ho\nst", "alpha"], ["host\ntouch x", "alpha"]])
def test_usage_exit_2(fake, args):
    e, calls = fake(["empty"])
    r = run(args, e)
    assert r.returncode == 2
    assert "usage" in r.stderr
    assert count(calls) == 0


def test_pending_exits_10_and_prints_lines(fake):
    e, _ = fake(["line"])
    r = run(["host", "alpha"], e)
    assert r.returncode == 10
    assert r.stdout == LINE + "\n"


def test_polls_until_pending(fake):
    e, calls = fake(["empty", "empty", "line"])
    r = run(["host", "alpha"], e)
    assert r.returncode == 10
    assert count(calls) == 3


def test_passes_target_project_and_options(fake):
    e, calls = fake(["line"])
    run(["host", "alpha"], e)
    argv = calls.read_text()
    assert "-o BatchMode=yes" in argv
    assert " -- host " in argv
    assert "sf-status local pending --project alpha" in argv


def test_ssh_failure_exits_11(fake):
    e, calls = fake(["fail"])
    r = run(["host", "alpha"], e)
    assert r.returncode == 11
    assert "ssh failed (exit 255)" in r.stderr
    assert count(calls) == 1


def test_max_duration_exits_12(fake):
    e, _ = fake(["empty"], SF_LOCAL_WATCH_MAX_SECONDS="1")
    r = run(["host", "alpha"], e)
    assert r.returncode == 12


def test_hung_ssh_times_out_exit_11(fake, tmp_path):
    e, calls = fake(["hang"], SF_LOCAL_WATCH_SSH_TIMEOUT="1")
    start = time.time()
    r = run(["host", "alpha"], e)
    assert r.returncode == 11
    assert "timed out" in r.stderr
    assert time.time() - start < 15
    assert count(calls) == 1
    ps = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout
    assert "sleep 987" not in [l.strip() for l in ps.splitlines()]


@pytest.mark.parametrize("name,value", [
    ("SF_LOCAL_WATCH_INTERVAL", "abc"), ("SF_LOCAL_WATCH_INTERVAL", "0"), ("SF_LOCAL_WATCH_INTERVAL", "-1"),
    ("SF_LOCAL_WATCH_INTERVAL", "1.2.3"),
    ("SF_LOCAL_WATCH_MAX_SECONDS", "0"), ("SF_LOCAL_WATCH_MAX_SECONDS", "1.5"), ("SF_LOCAL_WATCH_MAX_SECONDS", "x"),
    ("SF_LOCAL_WATCH_SSH_TIMEOUT", "0"), ("SF_LOCAL_WATCH_SSH_TIMEOUT", "2.5"), ("SF_LOCAL_WATCH_SSH_TIMEOUT", "-3"),
])
def test_bad_numbers_exit_2_without_ssh(fake, name, value):
    e, calls = fake(["empty"], **{name: value})
    r = run(["host", "alpha"], e)
    assert r.returncode == 2
    assert "usage" in r.stderr
    assert count(calls) == 0


def test_decimal_interval_accepted(fake):
    e, _ = fake(["line"], SF_LOCAL_WATCH_INTERVAL="0.5")
    assert run(["host", "alpha"], e).returncode == 10


def test_ssh_failure_shows_last_stderr_line(fake):
    e, _ = fake(["nocmd"])
    r = run(["host", "alpha"], e)
    assert r.returncode == 11
    assert "ssh failed (exit 127): bash: sf-status: command not found" in r.stderr
