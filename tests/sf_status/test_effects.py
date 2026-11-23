import subprocess

from sf_status import effects


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_git_remote_head_parses_ls_remote(tmp_path):
    bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git("init", "--bare", str(bare), cwd=tmp_path)
    _git("clone", str(bare), str(work), cwd=tmp_path)
    (work / "f.txt").write_text("x\n")
    _git("add", "f.txt", cwd=work)
    _git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "init", cwd=work)
    _git("push", "origin", "HEAD:refs/heads/feature/x", cwd=work)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                         capture_output=True, text=True).stdout.strip()
    assert effects.git_remote_head(work, "feature/x") == sha
    assert effects.git_remote_head(work, "nope") is None


def test_git_remote_head_disables_prompts(tmp_path, monkeypatch):
    seen = {}

    def fake_run(args, timeout=10, env=None):
        seen["env"] = env
        return None

    monkeypatch.setattr(effects, "_run", fake_run)
    assert effects.git_remote_head(tmp_path, "x") is None
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"
