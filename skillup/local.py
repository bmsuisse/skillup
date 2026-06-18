import re
import shutil
from pathlib import Path
from urllib.parse import urlparse


def is_local_path(s: str) -> bool:
    """True for paths starting with /, a Windows drive letter, or file:// URLs."""
    if s.startswith("/"):
        return True
    if re.match(r"^[a-zA-Z]:[/\\]", s):
        return True
    if urlparse(s).scheme == "file":
        return True
    return False


def resolve_local_path(s: str) -> Path:
    """Convert a local path input (including file:// URLs) to an absolute Path."""
    parsed = urlparse(s)
    if parsed.scheme == "file":
        from urllib.request import url2pathname
        return Path(url2pathname(parsed.path)).resolve()
    return Path(s).resolve()


def get_skill_paths_local(local_path: Path) -> dict[str, str]:
    """Return {skill_name: repo-relative path} by scanning local_path for SKILL.md files."""
    skills: dict[str, str] = {}
    for p in local_path.rglob("*"):
        if p.name.upper() == "SKILL.MD":
            skill_name = p.parent.name
            rel = p.parent.relative_to(local_path)
            path = str(rel).replace("\\", "/")
            skills[skill_name] = path
    return skills


def install_skill_local(skill_name: str, local_path: Path) -> None:
    """Copy a skill directory from local_path into all configured target dirs."""
    from .settings import settings

    skill_dir: Path | None = None
    for p in local_path.rglob("*"):
        if p.name.upper() == "SKILL.MD" and p.parent.name == skill_name:
            skill_dir = p.parent
            break

    if not skill_dir:
        return

    for target_dir in settings.target_dirs:
        dest = target_dir / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
