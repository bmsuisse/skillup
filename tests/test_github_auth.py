import os
import requests
from unittest.mock import patch, MagicMock, PropertyMock
from bms_skills.github import (
    console,
    get_commit_sha,
    get_github_token,
    get_latest_release,
    get_repo_source,
)
from bms_skills.install import download_release

def test_get_github_token_from_env():
    with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
        assert get_github_token() == "env_token"

def test_get_github_token_from_gh_env():
    with patch.dict(os.environ, {"GH_TOKEN": "gh_env_token"}):
        if "GITHUB_TOKEN" in os.environ:
            del os.environ["GITHUB_TOKEN"]
        assert get_github_token() == "gh_env_token"

def test_get_github_token_from_cli():
    with patch.dict(os.environ, {}, clear=True), \
         patch("shutil.which", return_value="/usr/bin/gh"), \
         patch("subprocess.run") as mock_run:

        mock_run.return_value = MagicMock(stdout="cli_token\n", check_returncode=lambda: None)
        assert get_github_token() == "cli_token"

def test_get_github_token_not_found():
    with patch.dict(os.environ, {}, clear=True), \
         patch("shutil.which", return_value=None), \
         patch.object(console, "print") as mock_print:

        assert get_github_token() is None
        mock_print.assert_called_once()
        assert "Warning" in mock_print.call_args[0][0]

@patch("bms_skills.github.get_github_token")
@patch("requests.get")
def test_get_latest_release_uses_token(mock_get, mock_token):
    mock_token.return_value = "test_token"
    mock_get.return_value.json.return_value = {"tag_name": "v1.0.0", "zipball_url": "url"}
    mock_get.return_value.raise_for_status = MagicMock()

    get_latest_release("owner/repo")

    args, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == "token test_token"

@patch("bms_skills.github.get_github_token")
@patch("requests.get")
def test_get_commit_sha_uses_token(mock_get, mock_token):
    mock_token.return_value = "test_token"
    mock_get.return_value.json.return_value = {"sha": "abc123"}
    mock_get.return_value.raise_for_status = MagicMock()

    assert get_commit_sha("owner/repo", "main") == "abc123"

    args, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == "token test_token"

@patch("bms_skills.github.get_commit_sha")
@patch("bms_skills.github.get_latest_release")
def test_get_repo_source_falls_back_to_main_branch(mock_latest, mock_commit):
    response = MagicMock(status_code=404)
    mock_latest.side_effect = requests.HTTPError(response=response)
    mock_commit.return_value = "main-sha"

    source = get_repo_source("owner/repo")

    assert source.kind == "branch"
    assert source.ref == "main"
    assert source.commit == "main-sha"
    assert source.zip_url == "https://api.github.com/repos/owner/repo/zipball/main-sha"

@patch("bms_skills.github.get_github_token")
@patch("requests.get")
@patch("shutil.copyfileobj")
@patch("builtins.open", new_callable=MagicMock)
def test_download_release_uses_token(mock_open, mock_copy, mock_get, mock_token, tmp_path):
    mock_token.return_value = "test_token"
    mock_get.return_value.raw = MagicMock()
    mock_get.return_value.raise_for_status = MagicMock()

    with patch("bms_skills.settings.Settings.cache_dir", new_callable=PropertyMock) as mock_cache:
        mock_cache.return_value = tmp_path
        download_release("owner/repo", "v1.0.0", "url")

    args, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == "token test_token"
