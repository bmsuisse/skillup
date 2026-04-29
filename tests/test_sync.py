import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from skillup.cli import app
from skillup.install import ensure_dirs
from skillup.lock import save_lock
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


def test_sync_no_lock(temp_dirs):
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "No skills defined in lock file" in result.stdout


@patch("skillup.cli.download_release")
@patch("skillup.cli.install_skill")
def test_sync_with_lock(mock_install, mock_download, temp_dirs):
    fake_home, fake_cwd = temp_dirs
    repo = "test/repo"
    tag = "v1.0.0"
    skills = ["skill1", "skill2"]

    lock_data = {
        "repos": {
            repo: {
                "tag": tag,
                "skills": skills,
            }
        }
    }
    ensure_dirs()
    save_lock(lock_data)

    mock_download.return_value = Path("dummy.zip")

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert f"Syncing {repo} at {tag}" in result.stdout
    assert "Installing skill1" in result.stdout
    assert "Installing skill2" in result.stdout

    expected_url = f"https://api.github.com/repos/{repo}/zipball/{tag}"
    mock_download.assert_called_once_with(repo, tag, expected_url)

    assert mock_install.call_count == 2
    mock_install.assert_any_call("skill1", mock_download.return_value)
    mock_install.assert_any_call("skill2", mock_download.return_value)

    assert "Synchronization complete!" in result.stdout
