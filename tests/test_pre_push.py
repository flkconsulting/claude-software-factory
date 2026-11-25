import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "scripts" / "git-hooks" / "pre-push"
NULL = "0" * 40


def make_repo(tmp_path, gitleaks_body):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "blocklist_check.py", repo / "scripts")
    git = ["git", "-C", str(repo)]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                          "commit", "-qm", "init"], check=True)
    sha = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gitleaks"
    fake.write_text("#!/usr/bin/env bash\n" + gitleaks_body)
    fake.chmod(0o755)
    bl = tmp_path / "blocklist.txt"
    bl.write_text("# none\nunusedterm\n")
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               SF_BLOCKLIST_FILE=str(bl))
    return repo, sha, env


def push(repo, sha, env):
    return subprocess.run([str(HOOK)], input=f"refs/heads/x {sha} refs/heads/x {NULL}\n",
                          capture_output=True, text=True, cwd=repo, env=env)


def test_clean_scan_passes(tmp_path):
    repo, sha, env = make_repo(tmp_path, "exit 0\n")
    r = push(repo, sha, env)
    assert r.returncode == 0, r.stderr


def test_gitleaks_error_with_exit_zero_aborts(tmp_path):
    body = ("echo '10:52PM ERR [git] fatal: ambiguous argument' >&2\n"
            "echo '10:52PM ERR error=\"stderr is not empty\"' >&2\n"
            "exit 0\n")
    repo, sha, env = make_repo(tmp_path, body)
    r = push(repo, sha, env)
    assert r.returncode == 1
    assert "scan incomplete" in r.stderr
    assert "stderr is not empty" in r.stderr


def test_finding_aborts(tmp_path):
    repo, sha, env = make_repo(tmp_path, "echo 'Finding: REDACTED'\nexit 1\n")
    r = push(repo, sha, env)
    assert r.returncode == 1
    assert "possible secrets" in r.stderr
