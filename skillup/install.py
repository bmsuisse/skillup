import shutil
import zipfile
from pathlib import Path
from typing import List

import requests
from rich.progress import Progress, SpinnerColumn, TextColumn

from .github import get_github_headers
from .settings import settings


def ensure_dirs() -> None:
    settings.skills_dir_agents.mkdir(parents=True, exist_ok=True)
    settings.skills_dir_claude.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)


def download_release(repo: str, version: str, url: str) -> Path:
    cache_path = settings.cache_dir / f"{repo.replace('/', '_')}_{version}.zip"

    if cache_path.exists():
        return cache_path

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Downloading {repo} {version}...", total=None)

        response = requests.get(url, headers=get_github_headers(), stream=True)
        response.raise_for_status()
        with open(cache_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)

    return cache_path


def get_skills_in_zip(zip_path: Path) -> List[str]:
    skills = set()
    with zipfile.ZipFile(zip_path, "r") as z:
        for name in z.namelist():
            parts = Path(name).parts
            if len(parts) >= 4 and parts[1] == "skills" and parts[-1].upper() == "SKILL.MD":
                # skill name is the relative path from 'skills/' to the folder containing SKILL.md
                skills.add("/".join(parts[2:-1]))
    return sorted(list(skills))


def install_skill(skill_name: str, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as z:
        skill_prefix = ""
        skill_parts = Path(skill_name).parts
        for name in z.namelist():
            parts = Path(name).parts
            if (
                len(parts) >= 2 + len(skill_parts)
                and parts[1] == "skills"
                and parts[2 : 2 + len(skill_parts)] == skill_parts
            ):
                skill_prefix = "/".join(parts[: 2 + len(skill_parts)]) + "/"
                break

        if not skill_prefix:
            return

        skill_files = [f for f in z.namelist() if f.startswith(skill_prefix)]

        for target_dir in [settings.skills_dir_agents, settings.skills_dir_claude]:
            dest = target_dir / skill_name
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)

            for file_info in skill_files:
                rel_path_str = file_info[len(skill_prefix):]
                if not rel_path_str:
                    continue

                target_file = dest / rel_path_str

                if file_info.endswith("/"):
                    target_file.mkdir(parents=True, exist_ok=True)
                else:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(file_info) as source, open(target_file, "wb") as target:
                        shutil.copyfileobj(source, target)
