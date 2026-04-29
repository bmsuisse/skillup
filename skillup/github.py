import os
import shutil
import subprocess
from typing import Optional

import requests
from rich.console import Console

from .settings import RepoSource, settings

console = Console()


def get_github_token() -> Optional[str]:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        return token

    gh_path = shutil.which("gh")
    if gh_path:
        try:
            result = subprocess.run(
                [gh_path, "auth", "token"],
                capture_output=True,
                text=True,
                check=True,
            )
            token = result.stdout.strip()
            if token:
                return token
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    console.print("[yellow]Warning: GitHub authentication not found. API rate limits may apply.[/yellow]")
    return None


def get_github_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def get_latest_release(repo: str) -> tuple[str, str]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url, headers=get_github_headers())
    response.raise_for_status()
    data = response.json()
    return data["tag_name"], data["zipball_url"]


def get_commit_sha(repo: str, ref: str) -> str:
    url = f"https://api.github.com/repos/{repo}/commits/{ref}"
    response = requests.get(url, headers=get_github_headers())
    response.raise_for_status()
    data = response.json()
    return data["sha"]


def get_repo_source(repo: str, branch: Optional[str] = None) -> RepoSource:
    if branch:
        commit = get_commit_sha(repo, branch)
        return RepoSource(
            kind="branch",
            ref=branch,
            commit=commit,
            zip_url=f"https://api.github.com/repos/{repo}/zipball/{commit}",
        )

    try:
        tag, zip_url = get_latest_release(repo)
        return RepoSource(
            kind="release",
            ref=tag,
            commit=get_commit_sha(repo, tag),
            zip_url=zip_url,
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            commit = get_commit_sha(repo, "main")
            return RepoSource(
                kind="branch",
                ref="main",
                commit=commit,
                zip_url=f"https://api.github.com/repos/{repo}/zipball/{commit}",
            )
        raise
