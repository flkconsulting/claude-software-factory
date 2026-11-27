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


def _commit(work, name, text="x\n"):
    (work / name).write_text(text)
    _git("add", name, cwd=work)
    _git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", name, cwd=work)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                          capture_output=True, text=True).stdout.strip()


def test_git_cherry_with_real_repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "-b", "main", cwd=work)
    _commit(work, "base.txt")
    _git("checkout", "-b", "release/1.0.0", cwd=work)
    sha = _commit(work, "fix.txt", "fix\n")
    _git("checkout", "main", cwd=work)
    assert effects.git_cherry(work, "main", "release/1.0.0") == [sha]
    _git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "cherry-pick", sha, cwd=work)
    assert effects.git_cherry(work, "main", "release/1.0.0") == []
    assert effects.git_cherry(work, "main", "release/9.9.9") is None


def test_git_cherry_timeout_or_missing_git_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(effects, "_run", lambda *a, **k: None)
    assert effects.git_cherry(tmp_path, "main", "release/1.0.0") is None
