import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "blocklist_check.py"


def run(tmp_path, blocklist_text, files, extra_env=None):
    env = dict(os.environ)
    bl = tmp_path / "bl.txt"
    if blocklist_text is not None:
        bl.write_text(blocklist_text, encoding="utf-8")
    env["SF_BLOCKLIST_FILE"] = str(bl)
    paths = []
    for name, content in files.items():
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        paths.append(str(p))
    return subprocess.run(
        [sys.executable, str(SCRIPT), *paths],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )


def test_hit_reports_file_line_and_index_not_term(tmp_path):
    r = run(tmp_path, "# comment\nsecretcorp\n", {"file.md": "a\nb\nuse secretcorp here\n"})
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "file.md:3" in out
    assert "term #1" in out
    assert "secretcorp" not in out.lower()


def test_case_insensitive(tmp_path):
    r = run(tmp_path, "secretcorp\n", {"file.md": "x SecretCorp y\n"})
    assert r.returncode == 1


def test_missing_blocklist_fails_closed(tmp_path):
    r = run(tmp_path, None, {"file.md": "clean\n"})
    assert r.returncode == 2


def test_empty_blocklist_fails_closed(tmp_path):
    r = run(tmp_path, "# only comment\n\n", {"file.md": "clean\n"})
    assert r.returncode == 2


def test_clean_files_pass(tmp_path):
    r = run(tmp_path, "secretcorp\n", {"file.md": "nothing here\n"})
    assert r.returncode == 0


def test_binary_files_skipped(tmp_path):
    bl = tmp_path / "bl.txt"
    bl.write_text("secretcorp\n", encoding="utf-8")
    b = tmp_path / "bin.dat"
    b.write_bytes(b"\x00secretcorp")
    env = dict(os.environ, SF_BLOCKLIST_FILE=str(bl))
    r = subprocess.run([sys.executable, str(SCRIPT), str(b)], capture_output=True, text=True, env=env)
    assert r.returncode == 0


def _raw(tmp_path, args):
    bl = tmp_path / "bl.txt"
    bl.write_text("secretcorp\n", encoding="utf-8")
    env = dict(os.environ, SF_BLOCKLIST_FILE=str(bl))
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, cwd=tmp_path)


def test_nonexistent_file_fails_closed(tmp_path):
    r = _raw(tmp_path, ["typo.md"])
    assert r.returncode == 2
    assert "cannot read typo.md" in r.stderr


def test_directory_fails_closed(tmp_path):
    assert _raw(tmp_path, [str(tmp_path)]).returncode == 2


def test_unknown_option_fails_closed(tmp_path):
    assert _raw(tmp_path, ["--help"]).returncode == 2
    assert _raw(tmp_path, ["--all", "x"]).returncode == 2


def test_empty_argv_fails_closed(tmp_path):
    assert _raw(tmp_path, []).returncode == 2


def _git(repo, *args, env_extra=None):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    env.update(env_extra or {})
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def _commit(repo, files, message="work", author="Plain Dev", email="dev@example.org"):
    for name, content in files.items():
        (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(
        repo, "commit", "-q", "-m", message,
        env_extra={
            "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": email,
        },
    )


def _history(tmp_path, repo, *revs):
    bl = tmp_path / "bl.txt"
    bl.write_text("secretcorp\n", encoding="utf-8")
    env = dict(os.environ, SF_BLOCKLIST_FILE=str(bl))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--history", *revs],
        capture_output=True, text=True, env=env, cwd=repo,
    )


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    return repo


def test_history_clean_passes(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "hello\n"})
    assert _history(tmp_path, repo, "--all").returncode == 0


def test_history_finds_term_only_in_removed_line(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "hello\n"})
    _commit(repo, {"a.txt": "hello secretcorp\n"})
    _commit(repo, {"a.txt": "hello\n"})
    r = _history(tmp_path, repo, "--all")
    assert r.returncode == 1
    assert "term #1" in r.stdout
    assert "secretcorp" not in (r.stdout + r.stderr).lower()


def test_history_finds_term_in_author_name(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "hello\n"}, author="Secretcorp Person")
    r = _history(tmp_path, repo, "HEAD")
    assert r.returncode == 1
    assert "secretcorp" not in (r.stdout + r.stderr).lower()


def test_history_finds_term_in_author_email_and_message(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "x\n"}, email="a@secretcorp.example")
    assert _history(tmp_path, repo, "HEAD").returncode == 1
    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    _git(repo2, "init", "-q")
    _commit(repo2, {"a.txt": "x\n"}, message="mention secretcorp")
    assert _history(tmp_path, repo2, "HEAD").returncode == 1


def test_history_finds_term_in_file_name(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"secretcorp-notes.txt": "x\n"})
    assert _history(tmp_path, repo, "HEAD").returncode == 1


def test_history_respects_range(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "secretcorp\n"})
    _commit(repo, {"a.txt": "clean\n"})
    assert _history(tmp_path, repo, "HEAD~1..HEAD").returncode == 1  # removal shows the term
    _commit(repo, {"a.txt": "still clean\n"})
    assert _history(tmp_path, repo, "HEAD~1..HEAD").returncode == 0


def test_history_bad_range_fails_closed(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "x\n"})
    assert _history(tmp_path, repo, "nonexistent..HEAD").returncode == 2


def test_history_without_range_fails_closed(tmp_path):
    repo = _repo(tmp_path)
    assert _history(tmp_path, repo).returncode == 2


def test_blocklist_with_bom_keeps_first_term(tmp_path):
    bl = tmp_path / "bl.txt"
    bl.write_bytes(b"\xef\xbb\xbfsecretcorp\n")
    f = tmp_path / "f.md"
    f.write_text("secretcorp\n", encoding="utf-8")
    env = dict(os.environ, SF_BLOCKLIST_FILE=str(bl))
    r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True, env=env)
    assert r.returncode == 1


def test_history_finds_term_only_in_merge_resolution(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.txt": "base\n"})
    _git(repo, "branch", "-M", "main")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, {"a.txt": "side\n"})
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"a.txt": "main\n"})
    env = {
        "GIT_AUTHOR_NAME": "Plain Dev", "GIT_AUTHOR_EMAIL": "dev@example.org",
        "GIT_COMMITTER_NAME": "Plain Dev", "GIT_COMMITTER_EMAIL": "dev@example.org",
    }
    subprocess.run(
        ["git", "merge", "-q", "side"], cwd=repo, capture_output=True,
        env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **env),
    )
    (repo / "a.txt").write_text("resolved secretcorp\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "--no-edit", env_extra=env)
    r = _history(tmp_path, repo, "HEAD")
    assert r.returncode == 1
    assert "secretcorp" not in (r.stdout + r.stderr).lower()
