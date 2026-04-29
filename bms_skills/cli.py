import json
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import questionary
import requests
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(help="Minimal CLI to manage agent skills from GitHub releases or branches.")
console = Console()

@dataclass
class Settings:
    is_global: bool = False

    @property
    def base_dir(self) -> Path:
        return Path.home() if self.is_global else Path.cwd()

    @property
    def agents_dir(self) -> Path:
        return self.base_dir / ".agents"

    @property
    def skills_dir_agents(self) -> Path:
        return self.agents_dir / "skills"

    @property
    def skills_dir_claude(self) -> Path:
        # For local install, we might want to keep it in .claude in current dir
        # or maybe just under .agents. 
        # The prompt says "install to current directory".
        return self.base_dir / ".claude" / "skills"

    @property
    def cache_dir(self) -> Path:
        env_cache = os.getenv("BMS_SKILL_CACHE_DIR")
        if env_cache:
            return Path(env_cache)
        return Path(os.getenv("TEMP", "/tmp")) / "bms_skills_cache"

    @property
    def lock_file(self) -> Path:
        return self.agents_dir / "skills.lock.json"

settings = Settings()


@dataclass
class RepoSource:
    kind: str
    ref: str
    zip_url: str
    commit: Optional[str] = None

    @property
    def cache_key(self) -> str:
        return self.commit or self.ref


def format_source_label(source: RepoSource) -> str:
    """Format a human-readable source label for output."""
    if source.kind == "release" or not source.commit:
        return source.ref
    short_commit = source.commit[: min(len(source.commit), 7)]
    return f"{source.ref} ({short_commit})"

def ensure_dirs():
    """Ensure all required directories exist."""
    settings.skills_dir_agents.mkdir(parents=True, exist_ok=True)
    settings.skills_dir_claude.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

def load_lock() -> dict:
    """
    Load the skills lock file.
    Structure: { "repos": { "owner/repo": { "source": "...", "ref": "...", "commit": "...", "skills": [...] } } }
    """
    if settings.lock_file.exists():
        try:
            data = json.loads(settings.lock_file.read_text())
            if "repos" not in data:
                return {"repos": {}}
            return data
        except Exception:
            return {"repos": {}}
    return {"repos": {}}

def save_lock(data: dict):
    """Save the skills lock file. Deletes the file if no repos are left."""
    if not data.get("repos"):
        if settings.lock_file.exists():
            settings.lock_file.unlink()
        return

    settings.lock_file.parent.mkdir(parents=True, exist_ok=True)
    settings.lock_file.write_text(json.dumps(data, indent=2))

def get_github_token() -> Optional[str]:
    """Retrieve GitHub token from environment or gh CLI."""
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
                check=True
            )
            token = result.stdout.strip()
            if token:
                return token
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    console.print("[yellow]Warning: GitHub authentication not found. API rate limits may apply.[/yellow]")
    return None


def get_github_headers() -> dict[str, str]:
    """Build GitHub API headers with authentication when available."""
    headers = {}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def get_latest_release(repo: str):
    """Fetch latest release info from GitHub API."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url, headers=get_github_headers())
    response.raise_for_status()
    data = response.json()
    return data["tag_name"], data["zipball_url"]


def get_commit_sha(repo: str, ref: str) -> str:
    """Resolve a tag or branch name to its current commit SHA."""
    url = f"https://api.github.com/repos/{repo}/commits/{ref}"
    response = requests.get(url, headers=get_github_headers())
    response.raise_for_status()
    data = response.json()
    return data["sha"]


def get_repo_source(repo: str, branch: Optional[str] = None) -> RepoSource:
    """Resolve the repository source to install from."""
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


def normalize_repo_data(repo_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy lock file entries to the current structure."""
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
    """Persist source metadata to a lock-file entry."""
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
    """Build the exact source to use during sync from lock metadata."""
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

def download_release(repo: str, version: str, url: str) -> Path:
    """Download release zip using requests, with caching."""
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
    """List skills (directories under 'skills/' containing SKILL.md) in the zip file."""
    skills = set()
    with zipfile.ZipFile(zip_path, 'r') as z:
        # First, find all SKILL.md files and their parent directories
        for name in z.namelist():
            parts = Path(name).parts
            # Expecting: repo-tag/skills/skill-name/SKILL.md
            if len(parts) >= 4 and parts[1] == "skills" and parts[-1].upper() == "SKILL.MD":
                skills.add(parts[2])
    return sorted(list(skills))

def install_skill(skill_name: str, zip_path: Path):
    """Extract and install a specific skill from the 'skills/' folder to target directories."""
    with zipfile.ZipFile(zip_path, 'r') as z:
        # Find all files belonging to this skill under repo-tag/skills/skill-name/
        skill_prefix = ""
        # We need to find the actual prefix which includes the repo-tag
        for name in z.namelist():
            parts = Path(name).parts
            if len(parts) >= 3 and parts[1] == "skills" and parts[2] == skill_name:
                skill_prefix = "/".join(parts[:3]) + "/"
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
                # Remove the repo-tag/skills/skill-name/ prefix
                rel_path_str = file_info[len(skill_prefix):]
                if not rel_path_str: continue
                
                target_file = dest / rel_path_str
                
                if file_info.endswith('/'):
                    target_file.mkdir(parents=True, exist_ok=True)
                else:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(file_info) as source, open(target_file, "wb") as target:
                        shutil.copyfileobj(source, target)

@app.callback()
def main(
    is_global: bool = typer.Option(False, "--global", "-g", help="Use home directory instead of current directory")
):
    """Minimal CLI to manage agent skills from GitHub releases or branches."""
    settings.is_global = is_global

@app.command()
def add(
    repo: str = typer.Argument(..., help="GitHub repository (owner/repo)"),
    skills: Optional[List[str]] = typer.Option(None, "--skill", "-s", help="Specific skill(s) to add (non-interactive)"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch to install from instead of the latest release"),
):
    """Add skills from a GitHub release or branch."""
    ensure_dirs()
    lock = load_lock()
    
    try:
        source = get_repo_source(repo, branch)
    except Exception as e:
        console.print(f"[red]Error fetching source info for {repo}:[/red] {e}")
        raise typer.Exit(1)

    zip_path = download_release(repo, source.cache_key, source.zip_url)
    available_skills = get_skills_in_zip(zip_path)
    
    repo_data = normalize_repo_data(lock["repos"].get(repo, {"skills": []}))
    installed_skills = set(repo_data["skills"])
    
    if skills:
        # Non-interactive mode
        selected = [s for s in skills if s in available_skills and s not in installed_skills]
        invalid = [s for s in skills if s not in available_skills]
        already_installed = [s for s in skills if s in installed_skills]
        
        if invalid:
            console.print(f"[yellow]Warning: Skills not found in {repo}: {', '.join(invalid)}[/yellow]")
        if already_installed:
            console.print(f"[blue]Note: Skills already installed from {repo}: {', '.join(already_installed)}[/blue]")
    else:
        # Interactive mode
        to_show = [s for s in available_skills if s not in installed_skills]
        
        if not to_show:
            console.print(f"[yellow]No new skills available to add from {repo}.[/yellow]")
            return

        selected = questionary.checkbox(
            f"Select skills to add from {repo}:",
            choices=to_show
        ).ask()

    if not selected:
        console.print("No skills selected or available for installation.")
        return

    for skill in selected:
        console.print(f"Installing [cyan]{skill}[/cyan]...")
        install_skill(skill, zip_path)
        if skill not in repo_data["skills"]:
            repo_data["skills"].append(skill)

    repo_data = apply_source(repo_data, source)
    lock["repos"][repo] = repo_data
    save_lock(lock)
    console.print(f"[green]Skills from {repo} installed successfully![/green]")

@app.command()
def remove():
    """Interactively remove installed skills across all repositories."""
    lock = load_lock()
    
    all_installed = []
    for repo, data in lock["repos"].items():
        for skill in data["skills"]:
            all_installed.append(f"{repo}: {skill}")

    if not all_installed:
        console.print("[yellow]No skills installed.[/yellow]")
        return

    selected = questionary.checkbox(
        "Select skills to remove:",
        choices=all_installed
    ).ask()

    if not selected:
        console.print("No skills selected.")
        return

    for item in selected:
        repo, skill = item.split(": ", 1)
        console.print(f"Removing [red]{skill}[/red] from {repo}...")
        for target_dir in [settings.skills_dir_agents, settings.skills_dir_claude]:
            dest = target_dir / skill
            if dest.exists():
                shutil.rmtree(dest)
        
        lock["repos"][repo]["skills"].remove(skill)
        if not lock["repos"][repo]["skills"]:
            del lock["repos"][repo]
    
    save_lock(lock)
    console.print("[green]Skills removed successfully![/green]")

@app.command()
def update(repo: Optional[str] = typer.Option(None, "--repo", help="Specific repository to update")):
    """Update installed skills to the latest tracked release or branch commit."""
    lock = load_lock()
    repos_to_update = [repo] if repo else list(lock["repos"].keys())

    if not repos_to_update:
        console.print("[yellow]No skills installed to update.[/yellow]")
        return

    for r in repos_to_update:
        if r not in lock["repos"]:
            if repo:
                console.print(f"[red]Repository {r} is not tracked.[/red]")
            continue
            
        repo_data = normalize_repo_data(lock["repos"][r])
        console.print(f"Checking updates for [cyan]{r}[/cyan]...")
        
        try:
            tracked_branch = repo_data.get("branch") if repo_data.get("source") == "branch" else None
            source = get_repo_source(r, tracked_branch)
        except Exception as e:
            console.print(f"[red]Error fetching source info for {r}:[/red] {e}")
            continue

        current_version = repo_data.get("commit") or repo_data.get("tag") or repo_data.get("branch")
        new_version = source.commit or source.ref
        if current_version == new_version:
            console.print(f"  [green]{r} is already up-to-date ({format_source_label(source)}).[/green]")
            continue

        previous_label = repo_data.get("tag") or repo_data.get("branch") or repo_data.get("commit", "unknown")
        next_label = format_source_label(source)
        console.print(f"  Updating from {previous_label} to [cyan]{next_label}[/cyan]...", highlight=False)
        zip_path = download_release(r, source.cache_key, source.zip_url)
        
        for skill in repo_data["skills"]:
            console.print(f"  Updating [cyan]{skill}[/cyan]...")
            install_skill(skill, zip_path)
        
        repo_data = apply_source(repo_data, source)
        lock["repos"][r] = repo_data
        save_lock(lock)
        console.print(f"  [green]Successfully updated {r} to {next_label}![/green]")

@app.command()
def sync():
    """Install all skills as defined in the lock file."""
    ensure_dirs()
    lock = load_lock()
    
    if not lock["repos"]:
        console.print("[yellow]No skills defined in lock file. Use 'add' to add skills.[/yellow]")
        return

    for repo, repo_data in lock["repos"].items():
        source = get_sync_source(repo, repo_data)
        skills = repo_data["skills"]
        console.print(f"Syncing [cyan]{repo}[/cyan] at [green]{format_source_label(source)}[/green]...")
        
        try:
            zip_path = download_release(repo, source.cache_key, source.zip_url)
            for skill in skills:
                console.print(f"  Installing [cyan]{skill}[/cyan]...")
                install_skill(skill, zip_path)
        except Exception as e:
            console.print(f"[red]Error syncing {repo}:[/red] {e}")
            continue

    console.print("[green]Synchronization complete![/green]")


@app.command()
def migrate(
    input_file: Optional[Path] = typer.Argument(None, help="Path to skills-lock.json (defaults to .claude/skills-lock.json)"),
):
    """Migrate a Claude Code skills-lock.json to the bms-skills lock format."""
    if input_file is None:
        input_file = settings.base_dir / ".claude" / "skills-lock.json"

    if not input_file.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        data = json.loads(input_file.read_text())
    except Exception as e:
        console.print(f"[red]Failed to parse {input_file}:[/red] {e}")
        raise typer.Exit(1)

    skills_map: dict[str, Any] = data.get("skills", {})
    if not skills_map:
        console.print("[yellow]No skills found in the input file.[/yellow]")
        return

    repos: dict[str, list[str]] = {}
    for skill_name, skill_data in skills_map.items():
        if skill_data.get("sourceType") != "github":
            console.print(f"[yellow]Skipping {skill_name}: unsupported sourceType '{skill_data.get('sourceType')}'[/yellow]")
            continue
        repo = skill_data["source"]
        repos.setdefault(repo, []).append(skill_name)

    if not repos:
        console.print("[yellow]No GitHub skills found to migrate.[/yellow]")
        return

    lock = load_lock()

    for repo, skill_names in repos.items():
        console.print(f"Resolving [cyan]{repo}[/cyan]...")
        try:
            source = get_repo_source(repo)
        except Exception as e:
            console.print(f"[red]Error fetching source info for {repo}:[/red] {e}")
            continue

        repo_data = lock["repos"].get(repo, {"skills": []})
        existing = set(repo_data.get("skills", []))
        for skill in skill_names:
            if skill not in existing:
                repo_data.setdefault("skills", []).append(skill)

        repo_data = apply_source(repo_data, source)
        lock["repos"][repo] = repo_data
        console.print(f"  [green]Migrated {len(skill_names)} skill(s) at {format_source_label(source)}[/green]")

    ensure_dirs()
    save_lock(lock)
    console.print(f"[green]Migration complete! Lock file saved to {settings.lock_file}[/green]")


if __name__ == "__main__":
    app()
