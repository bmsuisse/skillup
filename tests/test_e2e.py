import json
import requests
from pathlib import Path
from skillup.cli import app
from skillup.settings import settings
from skillup.lock import load_lock, save_lock
from skillup.install import ensure_dirs
from typer.testing import CliRunner
import pytest
from unittest.mock import patch, MagicMock

runner = CliRunner()

@pytest.fixture
def temp_dirs(tmp_path):
    """Fixture to mock HOME, CWD and TEMP and redirect all paths to a temp directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_cwd = tmp_path / "cwd"
    fake_cwd.mkdir()
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home), \
         patch("pathlib.Path.cwd", return_value=fake_cwd), \
         patch("os.getenv", side_effect=lambda key, default=None: str(fake_temp) if key == "TEMP" else default):
        # Reset settings to default before each test
        settings.is_global = False
        yield fake_home, fake_cwd

@pytest.fixture
def mock_network():
    """Fixture to mock network-dependent functions."""
    with patch("skillup.github.get_latest_release") as mock_latest, \
         patch("skillup.github.get_commit_sha") as mock_commit, \
         patch("skillup.cli.download_release") as mock_download, \
         patch("skillup.cli.get_skills_in_zip") as mock_get_skills, \
         patch("skillup.cli.install_skill") as mock_install:

        mock_latest.return_value = ("v1.0.0", "http://example.com/zip")
        mock_commit.side_effect = lambda repo, ref: {
            "v1.0.0": "release-sha",
            "v1.1.0": "release-sha-2",
            "main": "main-sha",
            "develop": "develop-sha",
        }.get(ref, f"{ref}-sha")
        mock_download.return_value = Path("dummy.zip")
        mock_get_skills.return_value = ["github", "prek", "nicegui"]

        def side_effect_install(skill_name, zip_path):
            for target_dir in [settings.skills_dir_agents, settings.skills_dir_claude]:
                dest = target_dir / skill_name
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text(f"Mocked {skill_name}")

        mock_install.side_effect = side_effect_install

        yield {
            "latest": mock_latest,
            "commit": mock_commit,
            "download": mock_download,
            "get_skills": mock_get_skills,
            "install": mock_install
        }

def test_add_skills_local_default(temp_dirs, mock_network):
    """Test that skills are installed to CWD by default."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"

    result = runner.invoke(app, ["add", repo, "--skill", "github"])
    if result.exit_code != 0:
        print(result.stdout)
    assert result.exit_code == 0

    lock_file = fake_cwd / ".agents" / "skills.lock.json"
    assert lock_file.exists()
    lock_data = json.loads(lock_file.read_text())
    assert lock_data["repos"][repo]["source"] == "release"
    assert lock_data["repos"][repo]["tag"] == "v1.0.0"
    assert lock_data["repos"][repo]["commit"] == "release-sha"

    assert (fake_cwd / ".agents" / "skills" / "github").exists()
    assert (fake_cwd / ".claude" / "skills" / "github").exists()

    assert not (fake_home / ".agents").exists()

def test_add_skills_global(temp_dirs, mock_network):
    """Test that skills are installed to HOME with --global flag."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"

    result = runner.invoke(app, ["--global", "add", repo, "--skill", "github"])
    if result.exit_code != 0:
        print(result.stdout)
    assert result.exit_code == 0

    lock_file = fake_home / ".agents" / "skills.lock.json"
    assert lock_file.exists()
    lock_data = json.loads(lock_file.read_text())
    assert lock_data["repos"][repo]["source"] == "release"
    assert lock_data["repos"][repo]["commit"] == "release-sha"

    assert (fake_home / ".agents" / "skills" / "github").exists()
    assert (fake_home / ".claude" / "skills" / "github").exists()

    assert not (fake_cwd / ".agents").exists()

def test_remove_skills_local(temp_dirs, mock_network):
    """Test removing skills from local installation."""
    fake_home, fake_cwd = temp_dirs
    repo = "test/repo"
    skill = "test-skill"

    ensure_dirs()
    (settings.skills_dir_agents / skill).mkdir(parents=True)
    (settings.skills_dir_agents / skill / "SKILL.md").write_text("test")

    lock_data = {
        "repos": {
            repo: {
                "tag": "v1.0.0",
                "skills": [skill]
            }
        }
    }
    save_lock(lock_data)

    assert (fake_cwd / ".agents" / "skills" / skill).exists()

    with patch("questionary.checkbox") as mock_checkbox:
        mock_checkbox.return_value.ask.return_value = [f"{repo}: {skill}"]
        result = runner.invoke(app, ["remove"])
        assert result.exit_code == 0

    assert not (fake_cwd / ".agents" / "skills" / skill).exists()
    assert not (fake_cwd / ".agents" / "skills.lock.json").exists()

def test_sync_local(temp_dirs, mock_network):
    """Test sync in local directory."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"
    skill = "github"

    lock_data = {
        "repos": {
            repo: {
                "tag": "v1.0.0",
                "skills": [skill]
            }
        }
    }
    ensure_dirs()
    save_lock(lock_data)

    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0

    assert (fake_cwd / ".agents" / "skills" / skill).exists()
    mock_network["download"].assert_called_with(repo, "v1.0.0", f"https://api.github.com/repos/{repo}/zipball/v1.0.0")

def test_update_local(temp_dirs, mock_network):
    """Test update in local directory."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"
    skill = "github"

    ensure_dirs()
    lock_data = {
        "repos": {
            repo: {
                "tag": "v0.9.0",
                "skills": [skill]
            }
        }
    }
    save_lock(lock_data)

    mock_network["latest"].return_value = ("v1.1.0", "http://example.com/zip2")

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "v0.9.0" in result.stdout
    assert "v1.1.0" in result.stdout

    lock = load_lock()
    assert lock["repos"][repo]["tag"] == "v1.1.0"
    assert lock["repos"][repo]["source"] == "release"
    assert lock["repos"][repo]["commit"] == "release-sha-2"

def test_add_skills_from_branch(temp_dirs, mock_network):
    """Test that branch-based installs store branch and commit metadata."""
    fake_home, fake_cwd = temp_dirs
    repo = "anthropics/skills"

    result = runner.invoke(app, ["add", repo, "--branch", "develop", "--skill", "github"])
    assert result.exit_code == 0

    lock = load_lock()
    assert lock["repos"][repo]["source"] == "branch"
    assert lock["repos"][repo]["branch"] == "develop"
    assert lock["repos"][repo]["commit"] == "develop-sha"
    mock_network["latest"].assert_not_called()
    mock_network["download"].assert_called_with(repo, "develop-sha", "https://api.github.com/repos/anthropics/skills/zipball/develop-sha")

def test_add_skills_falls_back_to_main_branch(temp_dirs, mock_network):
    """Test that repos without releases fall back to main."""
    fake_home, fake_cwd = temp_dirs
    repo = "anthropics/skills"

    response = MagicMock(status_code=404)
    mock_network["latest"].side_effect = requests.HTTPError(response=response)

    result = runner.invoke(app, ["add", repo, "--skill", "github"])
    assert result.exit_code == 0

    lock = load_lock()
    assert lock["repos"][repo]["source"] == "branch"
    assert lock["repos"][repo]["branch"] == "main"
    assert lock["repos"][repo]["commit"] == "main-sha"
    mock_network["download"].assert_called_with(repo, "main-sha", "https://api.github.com/repos/anthropics/skills/zipball/main-sha")

def test_cache_dir_override(temp_dirs, mock_network):
    """Test that SKILLUP_CACHE_DIR environment variable overrides the default cache dir."""
    fake_home, fake_cwd = temp_dirs
    custom_cache = fake_home / "custom_cache"
    custom_cache.mkdir()

    with patch("os.getenv", side_effect=lambda key, default=None: str(custom_cache) if key == "SKILLUP_CACHE_DIR" else default):
        assert settings.cache_dir == custom_cache

        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0

        assert custom_cache.exists()
