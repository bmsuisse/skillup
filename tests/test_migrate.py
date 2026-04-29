import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bms_skills.cli import app
from bms_skills.lock import load_lock
from bms_skills.settings import settings

runner = CliRunner()


@pytest.fixture
def temp_dirs(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_cwd = tmp_path / "cwd"
    fake_cwd.mkdir()
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home), \
         patch("pathlib.Path.cwd", return_value=fake_cwd), \
         patch("os.getenv", side_effect=lambda key, default=None: str(fake_temp) if key == "TEMP" else default):
        settings.is_global = False
        yield fake_home, fake_cwd


@pytest.fixture
def mock_network():
    with patch("bms_skills.github.get_latest_release") as mock_latest, \
         patch("bms_skills.github.get_commit_sha") as mock_commit:
        mock_latest.return_value = ("v1.0.0", "http://example.com/zip")
        mock_commit.side_effect = lambda repo, ref: f"{ref}-sha"
        yield {"latest": mock_latest, "commit": mock_commit}


def _write_skills_lock(directory: Path, skills: dict) -> Path:
    path = directory / ".claude" / "skills-lock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "skills": skills}))
    return path


def test_migrate_missing_file(temp_dirs):
    fake_home, fake_cwd = temp_dirs
    result = runner.invoke(app, ["migrate", str(fake_cwd / "nonexistent.json")])
    assert result.exit_code == 1
    assert "File not found" in result.stdout


def test_migrate_creates_lock(temp_dirs, mock_network):
    fake_home, fake_cwd = temp_dirs

    _write_skills_lock(fake_cwd, {
        "code-reviewer": {"source": "google-gemini/gemini-cli", "sourceType": "github", "computedHash": "aaa"},
        "coding-guidelines": {"source": "bmsuisse/skills", "sourceType": "github", "computedHash": "bbb"},
    })

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0, result.stdout

    lock = load_lock()
    assert "google-gemini/gemini-cli" in lock["repos"]
    assert "bmsuisse/skills" in lock["repos"]

    gemini = lock["repos"]["google-gemini/gemini-cli"]
    assert "code-reviewer" in gemini["skills"]
    assert gemini["source"] == "release"
    assert gemini["tag"] == "v1.0.0"
    assert gemini["commit"] == "v1.0.0-sha"

    bms = lock["repos"]["bmsuisse/skills"]
    assert "coding-guidelines" in bms["skills"]


def test_migrate_groups_skills_by_repo(temp_dirs, mock_network):
    fake_home, fake_cwd = temp_dirs

    _write_skills_lock(fake_cwd, {
        "skill-a": {"source": "owner/repo", "sourceType": "github", "computedHash": "aaa"},
        "skill-b": {"source": "owner/repo", "sourceType": "github", "computedHash": "bbb"},
    })

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0, result.stdout

    lock = load_lock()
    assert len(lock["repos"]) == 1
    repo_entry = lock["repos"]["owner/repo"]
    assert set(repo_entry["skills"]) == {"skill-a", "skill-b"}


def test_migrate_skips_non_github_source(temp_dirs, mock_network):
    fake_home, fake_cwd = temp_dirs

    _write_skills_lock(fake_cwd, {
        "local-skill": {"source": "some/path", "sourceType": "local", "computedHash": "aaa"},
        "gh-skill": {"source": "owner/repo", "sourceType": "github", "computedHash": "bbb"},
    })

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0, result.stdout
    assert "Skipping local-skill" in result.stdout

    lock = load_lock()
    assert "owner/repo" in lock["repos"]
    assert len(lock["repos"]) == 1


def test_migrate_no_github_skills(temp_dirs):
    fake_home, fake_cwd = temp_dirs

    _write_skills_lock(fake_cwd, {
        "local-skill": {"source": "some/path", "sourceType": "local", "computedHash": "aaa"},
    })

    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 0
    assert "No GitHub skills found" in result.stdout


def test_migrate_custom_input_path(temp_dirs, mock_network):
    fake_home, fake_cwd = temp_dirs

    custom_path = fake_cwd / "custom-lock.json"
    custom_path.write_text(json.dumps({"version": 1, "skills": {
        "my-skill": {"source": "owner/repo", "sourceType": "github", "computedHash": "aaa"},
    }}))

    result = runner.invoke(app, ["migrate", str(custom_path)])
    assert result.exit_code == 0, result.stdout

    lock = load_lock()
    assert "owner/repo" in lock["repos"]
    assert "my-skill" in lock["repos"]["owner/repo"]["skills"]


def test_migrate_global_flag(temp_dirs, mock_network):
    fake_home, fake_cwd = temp_dirs

    _write_skills_lock(fake_home, {
        "my-skill": {"source": "owner/repo", "sourceType": "github", "computedHash": "aaa"},
    })

    result = runner.invoke(app, ["--global", "migrate"])
    assert result.exit_code == 0, result.stdout

    lock_file = fake_home / ".agents" / "skills.lock.json"
    assert lock_file.exists()
    lock = json.loads(lock_file.read_text())
    assert "owner/repo" in lock["repos"]
