import os
from typing import Any, Optional
from urllib.parse import quote, unquote, urlparse

from .http import session
from .settings import RepoSource

# Azure DevOps resource ID — used as the OAuth2 scope for DefaultAzureCredential
_AZDEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"
_API_VERSION = "7.1"


def parse_azdevops_repo(repo_or_url: str) -> str:
    """Return 'org/project/repo' from either a shorthand or a full Azure DevOps URL.

    Supported URL formats:
    - ``https://dev.azure.com/org/project/_git/repo``
    - ``https://user@dev.azure.com/org/project/_git/repo``
    - ``https://org.visualstudio.com/project/_git/repo``  (legacy)

    Names are URL-decoded so ``BMS%20%E2%80%93%20OnPrem`` becomes ``BMS – OnPrem``.
    The returned shorthand uses ``/`` as separator; names must not contain slashes.
    """
    parsed = urlparse(repo_or_url)
    if not parsed.scheme:
        return repo_or_url

    netloc = parsed.netloc  # may include user@
    host = netloc.split("@")[-1]  # strip optional user@ prefix

    if host == "dev.azure.com":
        path = unquote(parsed.path).strip("/")
        parts = path.split("/")
        try:
            git_idx = parts.index("_git")
            org = parts[0]
            project = "/".join(parts[1:git_idx])
            repo = parts[git_idx + 1]
            return f"{org}/{project}/{repo}"
        except (ValueError, IndexError):
            pass

    if host.endswith(".visualstudio.com"):
        org = host.split(".")[0]
        path = unquote(parsed.path).strip("/")
        parts = path.split("/")
        try:
            git_idx = parts.index("_git")
            project = "/".join(parts[:git_idx])
            repo = parts[git_idx + 1]
            return f"{org}/{project}/{repo}"
        except (ValueError, IndexError):
            pass

    return repo_or_url


def get_azdevops_token() -> Optional[str]:
    """Return a bearer token for Azure DevOps.

    Priority:
    1. ``AZURE_DEVOPS_TOKEN`` env var (PAT or bearer token)
    2. ``DefaultAzureCredential`` from the ``azure-identity`` package (requires
       the ``azure`` extra: ``pip install skillup[azure]``)
    """
    token = os.getenv("AZURE_DEVOPS_TOKEN")
    if token:
        return token
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

        credential = DefaultAzureCredential()
        token_obj = credential.get_token(_AZDEVOPS_SCOPE)
        return token_obj.token
    except ImportError:
        return None


def get_azdevops_headers() -> dict[str, str]:
    token = get_azdevops_token()
    if not token:
        raise RuntimeError(
            "Azure DevOps authentication not found.\n"
            "Set AZURE_DEVOPS_TOKEN, or install 'azure-identity' and sign in:\n"
            "  pip install 'skillup[azure]'"
        )
    return {"Authorization": f"Bearer {token}"}


def _api_base(org: str, project: str, repo: str) -> str:
    return (
        f"https://dev.azure.com/{quote(org, safe='')}"
        f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repo, safe='')}"
    )


def _get_latest_commit(org: str, project: str, repo: str, branch: str) -> str:
    url = (
        f"{_api_base(org, project, repo)}/commits"
        f"?searchCriteria.itemVersion.version={quote(branch, safe='')}&$top=1&api-version={_API_VERSION}"
    )
    response = session().get(url, headers=get_azdevops_headers())
    response.raise_for_status()
    commits = response.json().get("value", [])
    if not commits:
        raise ValueError(f"No commits found on branch '{branch}' in {org}/{project}/{repo}")
    return commits[0]["commitId"]


def _zip_url(org: str, project: str, repo: str, version: str, version_type: str) -> str:
    return (
        f"https://dev.azure.com/{quote(org, safe='')}/{quote(project, safe='')}/_apis/git/repositories"
        f"/{quote(repo, safe='')}/items"
        f"?scopePath=/&versionDescriptor.version={quote(version, safe='')}"
        f"&versionDescriptor.versionType={version_type}"
        f"&$format=zip&api-version={_API_VERSION}&recursionLevel=full"
    )


def _parse_ref(full_ref: str) -> tuple[str, str, str]:
    """Parse 'org/project/repo' into (org, project, repo)."""
    parts = full_ref.split("/")
    if len(parts) != 3:
        raise ValueError(f"Azure DevOps repo must be 'org/project/repo', got: {full_ref!r}")
    return parts[0], parts[1], parts[2]


def get_azdevops_repo_source(full_ref: str, branch: Optional[str] = None) -> RepoSource:
    """Resolve an Azure DevOps repo to a ``RepoSource``.

    Args:
        full_ref: ``org/project/repo`` — the three-part repo identifier, or a
            full Azure DevOps URL (parsed automatically).
        branch: Branch to track; defaults to ``"main"``.
    """
    full_ref = parse_azdevops_repo(full_ref)
    org, project, repo = _parse_ref(full_ref)
    resolved_branch = branch or "main"
    commit = _get_latest_commit(org, project, repo, resolved_branch)
    return RepoSource(
        kind="branch",
        ref=resolved_branch,
        commit=commit,
        zip_url=_zip_url(org, project, repo, commit, "commit"),
        provider="azdevops",
    )


def get_azdevops_sync_source(full_ref: str, repo_data: dict[str, Any]) -> RepoSource:
    """Reconstruct a ``RepoSource`` from lock file data (no network call)."""
    org, project, repo = _parse_ref(full_ref)
    ref = repo_data.get("ref") or repo_data.get("branch") or "main"
    commit = repo_data.get("commit")

    if commit:
        zip_url = _zip_url(org, project, repo, commit, "commit")
    else:
        zip_url = _zip_url(org, project, repo, ref, "branch")

    return RepoSource(
        kind=repo_data.get("source", "branch"),
        ref=ref,
        commit=commit,
        zip_url=zip_url,
        provider="azdevops",
    )
