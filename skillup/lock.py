import json
from typing import Any

from .settings import RepoSource, settings


def load_lock() -> dict:
    if settings.lock_file.exists():
        try:
            data = json.loads(settings.lock_file.read_text())
            if "repos" not in data:
                return {"repos": {}}
            return data
        except Exception:
            return {"repos": {}}
    return {"repos": {}}


def save_lock(data: dict) -> None:
    if not data.get("repos"):
        if settings.lock_file.exists():
            settings.lock_file.unlink()
        return

    settings.lock_file.parent.mkdir(parents=True, exist_ok=True)
    settings.lock_file.write_text(json.dumps(data, indent=2))


def normalize_repo_data(repo_data: dict[str, Any]) -> dict[str, Any]:
    skills = list(repo_data.get("skills", []))
    normalized: dict[str, Any] = {"skills": skills}

    if repo_data.get("source") in {"release", "branch"}:
        normalized["source"] = repo_data["source"]
        normalized["ref"] = repo_data.get("ref") or repo_data.get("tag") or repo_data.get("branch")
        if repo_data.get("tag"):
            normalized["tag"] = repo_data["tag"]
        if repo_data.get("branch"):
            normalized["branch"] = repo_data["branch"]
        if repo_data.get("commit"):
            normalized["commit"] = repo_data["commit"]
        return normalized

    if repo_data.get("branch"):
        normalized["source"] = "branch"
        normalized["ref"] = repo_data["branch"]
        normalized["branch"] = repo_data["branch"]
    elif repo_data.get("tag"):
        normalized["source"] = "release"
        normalized["ref"] = repo_data["tag"]
        normalized["tag"] = repo_data["tag"]

    if repo_data.get("commit"):
        normalized["commit"] = repo_data["commit"]

    return normalized


def apply_source(repo_data: dict[str, Any], source: RepoSource) -> dict[str, Any]:
    repo_data["source"] = source.kind
    repo_data["ref"] = source.ref
    repo_data["commit"] = source.commit

    if source.kind == "release":
        repo_data["tag"] = source.ref
        repo_data.pop("branch", None)
    else:
        repo_data["branch"] = source.ref
        repo_data.pop("tag", None)

    return repo_data


def get_sync_source(repo: str, repo_data: dict[str, Any]) -> RepoSource:
    normalized = normalize_repo_data(repo_data)
    ref = normalized.get("ref") or normalized.get("tag") or normalized.get("branch") or "main"
    commit = normalized.get("commit")
    zip_ref = commit or ref
    return RepoSource(
        kind=normalized.get("source", "release"),
        ref=ref,
        commit=commit,
        zip_url=f"https://api.github.com/repos/{repo}/zipball/{zip_ref}",
    )
