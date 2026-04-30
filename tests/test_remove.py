from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from skillup.cli import app
from skillup.install import ensure_dirs
from skillup.lock import load_lock, save_lock
from skillup.settings import settings

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


def _setup_lock(with_dirs=True):
    lock_data = {
        "repos": {
            "owner/repo": {
                "tag": "v1.0.0",
                "skills": ["skill-a", "skill-b"],
            },
            "other/repo": {
                "tag": "v2.0.0",
                "skills": ["skill-c"],
            },
        }
    }
    if with_dirs:
        ensure_dirs()
    save_lock(lock_data)
    return lock_data


def test_remove_repo_removes_all_skills(temp_dirs):
    _setup_lock()

    result = runner.invoke(app, ["remove", "--repo", "owner/repo"])
    assert result.exit_code == 0, result.stdout
    assert "skill-a" in result.stdout
    assert "skill-b" in result.stdout
    assert "Skills removed successfully" in result.stdout

    lock = load_lock()
    assert "owner/repo" not in lock["repos"]
    assert "other/repo" in lock["repos"]


def test_remove_repo_with_skill_removes_single_skill(temp_dirs):
    _setup_lock()

    result = runner.invoke(app, ["remove", "--repo", "owner/repo", "--skill", "skill-a"])
    assert result.exit_code == 0, result.stdout
    assert "skill-a" in result.stdout
    assert "Skills removed successfully" in result.stdout

    lock = load_lock()
    assert "owner/repo" in lock["repos"]
    assert "skill-a" not in lock["repos"]["owner/repo"]["skills"]
    assert "skill-b" in lock["repos"]["owner/repo"]["skills"]


def test_remove_repo_with_multiple_skills(temp_dirs):
    _setup_lock()

    result = runner.invoke(app, ["remove", "--repo", "owner/repo", "--skill", "skill-a", "--skill", "skill-b"])
    assert result.exit_code == 0, result.stdout

    lock = load_lock()
    assert "owner/repo" not in lock["repos"]


def test_remove_repo_unknown(temp_dirs):
    _setup_lock()

    result = runner.invoke(app, ["remove", "--repo", "nonexistent/repo"])
    assert result.exit_code == 1
    assert "not tracked" in result.stdout


def test_remove_skill_not_in_repo(temp_dirs):
    _setup_lock()

    result = runner.invoke(app, ["remove", "--repo", "owner/repo", "--skill", "nonexistent-skill"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "No matching skills to remove" in result.stdout


def test_remove_skill_deletes_directory(temp_dirs):
    fake_home, fake_cwd = temp_dirs
    ensure_dirs()
    save_lock({
        "repos": {
            "owner/repo": {
                "tag": "v1.0.0",
                "skills": ["skill-a"],
            }
        }
    })

    # Create a fake skill directory so shutil.rmtree has something to delete
    skill_dir = settings.skills_dir_agents / "skill-a"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("skill")

    result = runner.invoke(app, ["remove", "--repo", "owner/repo", "--skill", "skill-a"])
    assert result.exit_code == 0, result.stdout
    assert not skill_dir.exists()

    lock = load_lock()
    assert "owner/repo" not in lock["repos"]


def test_remove_no_skills_installed(temp_dirs):
    ensure_dirs()
    save_lock({"repos": {}})

    result = runner.invoke(app, ["remove", "--repo", "owner/repo"])
    assert result.exit_code == 1
    assert "not tracked" in result.stdout
