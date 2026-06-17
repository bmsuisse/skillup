import os
from unittest.mock import MagicMock, patch

import pytest

from skillup.azdevops import (
    get_azdevops_headers,
    get_azdevops_repo_source,
    get_azdevops_sync_source,
    get_azdevops_token,
    parse_azdevops_repo,
)
from skillup.cli import _detect_provider, _parse_repo_input


# ---------------------------------------------------------------------------
# parse_azdevops_repo
# ---------------------------------------------------------------------------

class TestParseAzdevopsRepo:
    def test_dev_azure_com(self):
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        assert parse_azdevops_repo(url) == "myorg/myproject/myrepo"

    def test_dev_azure_com_with_user(self):
        url = "https://bmeurope@dev.azure.com/bmeurope/myproject/_git/myrepo"
        assert parse_azdevops_repo(url) == "bmeurope/myproject/myrepo"

    def test_url_encoded_names(self):
        url = "https://bmeurope@dev.azure.com/bmeurope/BMS%20%E2%80%93%20OnPrem/_git/BMS%20%E2%80%93%20OnPrem"
        assert parse_azdevops_repo(url) == "bmeurope/BMS – OnPrem/BMS – OnPrem"

    def test_visualstudio_com(self):
        url = "https://myorg.visualstudio.com/myproject/_git/myrepo"
        assert parse_azdevops_repo(url) == "myorg/myproject/myrepo"

    def test_passthrough_shorthand(self):
        assert parse_azdevops_repo("org/project/repo") == "org/project/repo"

    def test_passthrough_unknown_url(self):
        assert parse_azdevops_repo("https://example.com/some/path") == "https://example.com/some/path"


# ---------------------------------------------------------------------------
# _detect_provider / _parse_repo_input  (cli helpers)
# ---------------------------------------------------------------------------

class TestDetectProvider:
    def test_github_shorthand(self):
        assert _detect_provider("owner/repo") == "github"

    def test_github_url(self):
        assert _detect_provider("https://github.com/owner/repo") == "github"

    def test_azdevops_dev_azure_com(self):
        assert _detect_provider("https://dev.azure.com/org/proj/_git/repo") == "azdevops"

    def test_azdevops_visualstudio_com(self):
        assert _detect_provider("https://myorg.visualstudio.com/proj/_git/repo") == "azdevops"

    def test_azdevops_with_user(self):
        assert _detect_provider("https://user@dev.azure.com/org/proj/_git/repo") == "azdevops"


class TestParseRepoInput:
    def test_github_shorthand(self):
        lock_key, short_ref = _parse_repo_input("owner/repo")
        assert lock_key == "owner/repo"
        assert short_ref == "owner/repo"

    def test_github_url(self):
        lock_key, short_ref = _parse_repo_input("https://github.com/owner/repo")
        assert lock_key == "owner/repo"
        assert short_ref == "owner/repo"

    def test_azdevops_url(self):
        lock_key, short_ref = _parse_repo_input("https://dev.azure.com/org/proj/_git/repo")
        assert lock_key == "azdo:org/proj/repo"
        assert short_ref == "org/proj/repo"

    def test_azdevops_url_encoded(self):
        url = "https://bmeurope@dev.azure.com/bmeurope/BMS%20%E2%80%93%20OnPrem/_git/BMS%20%E2%80%93%20OnPrem"
        lock_key, short_ref = _parse_repo_input(url)
        assert short_ref == "bmeurope/BMS – OnPrem/BMS – OnPrem"
        assert lock_key == f"azdo:{short_ref}"


# ---------------------------------------------------------------------------
# get_azdevops_token
# ---------------------------------------------------------------------------

class TestGetAzdevopsToken:
    def test_env_var(self):
        with patch.dict(os.environ, {"AZURE_DEVOPS_TOKEN": "my-pat"}):
            assert get_azdevops_token() == "my-pat"

    def test_default_azure_credential(self):
        mock_cred = MagicMock()
        mock_cred.get_token.return_value = MagicMock(token="az-bearer")

        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"azure.identity": MagicMock(DefaultAzureCredential=lambda: mock_cred)}):
                token = get_azdevops_token()

        assert token == "az-bearer"

    def test_returns_none_when_no_auth(self):
        # Remove AZURE_DEVOPS_TOKEN and simulate azure.identity not installed
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"azure.identity": None}):
                token = get_azdevops_token()
        assert token is None

    def test_env_var_takes_priority_over_credential(self):
        mock_cred = MagicMock()
        with patch.dict(os.environ, {"AZURE_DEVOPS_TOKEN": "pat-wins"}):
            with patch.dict("sys.modules", {"azure.identity": MagicMock(DefaultAzureCredential=lambda: mock_cred)}):
                token = get_azdevops_token()
        assert token == "pat-wins"
        mock_cred.get_token.assert_not_called()


# ---------------------------------------------------------------------------
# get_azdevops_headers
# ---------------------------------------------------------------------------

class TestGetAzdevopsHeaders:
    def test_returns_bearer_header(self):
        with patch("skillup.azdevops.get_azdevops_token", return_value="tok"):
            headers = get_azdevops_headers()
        assert headers == {"Authorization": "Bearer tok"}

    def test_raises_when_no_token(self):
        with patch("skillup.azdevops.get_azdevops_token", return_value=None):
            with pytest.raises(RuntimeError, match="AZURE_DEVOPS_TOKEN"):
                get_azdevops_headers()


# ---------------------------------------------------------------------------
# get_azdevops_repo_source
# ---------------------------------------------------------------------------

class TestGetAzdevopsRepoSource:
    def _mock_session(self, commit_id: str = "abc1234567890"):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"value": [{"commitId": commit_id}]}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        return mock_session

    def test_resolves_main_by_default(self):
        with patch("skillup.azdevops.get_azdevops_headers", return_value={}), \
             patch("skillup.http._session", self._mock_session("deadbeef")):
            source = get_azdevops_repo_source("org/project/repo")

        assert source.provider == "azdevops"
        assert source.kind == "branch"
        assert source.ref == "main"
        assert source.commit == "deadbeef"
        assert "deadbeef" in source.zip_url
        assert "versionDescriptor.versionType=commit" in source.zip_url

    def test_resolves_custom_branch(self):
        with patch("skillup.azdevops.get_azdevops_headers", return_value={}), \
             patch("skillup.http._session", self._mock_session("cafebabe")):
            source = get_azdevops_repo_source("org/project/repo", branch="develop")

        assert source.ref == "develop"
        assert source.commit == "cafebabe"

    def test_accepts_full_url(self):
        with patch("skillup.azdevops.get_azdevops_headers", return_value={}), \
             patch("skillup.http._session", self._mock_session("feedface")):
            source = get_azdevops_repo_source(
                "https://dev.azure.com/org/project/_git/repo"
            )

        assert source.commit == "feedface"

    def test_raises_on_empty_commits(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"value": []}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch("skillup.azdevops.get_azdevops_headers", return_value={}), \
             patch("skillup.http._session", mock_session):
            with pytest.raises(ValueError, match="No commits found"):
                get_azdevops_repo_source("org/project/repo")

    def test_url_encodes_special_chars(self):
        with patch("skillup.azdevops.get_azdevops_headers", return_value={}), \
             patch("skillup.http._session", self._mock_session("aabbcc")):
            source = get_azdevops_repo_source("org/BMS – OnPrem/BMS – OnPrem")

        assert "BMS%20%E2%80%93%20OnPrem" in source.zip_url

    def test_invalid_ref_raises(self):
        with pytest.raises(ValueError, match="org/project/repo"):
            get_azdevops_repo_source("only/two")


# ---------------------------------------------------------------------------
# get_azdevops_sync_source
# ---------------------------------------------------------------------------

class TestGetAzdevopsSyncSource:
    def test_from_commit(self):
        repo_data = {"source": "branch", "ref": "main", "branch": "main", "commit": "abc123"}
        source = get_azdevops_sync_source("org/project/repo", repo_data)

        assert source.provider == "azdevops"
        assert source.commit == "abc123"
        assert "abc123" in source.zip_url
        assert "versionDescriptor.versionType=commit" in source.zip_url

    def test_from_branch_when_no_commit(self):
        repo_data = {"source": "branch", "ref": "develop", "branch": "develop"}
        source = get_azdevops_sync_source("org/project/repo", repo_data)

        assert source.ref == "develop"
        assert source.commit is None
        assert "develop" in source.zip_url
        assert "versionDescriptor.versionType=branch" in source.zip_url

    def test_defaults_to_main(self):
        source = get_azdevops_sync_source("org/project/repo", {})
        assert source.ref == "main"
