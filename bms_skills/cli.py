import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import List, Optional

import questionary
import requests
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(help="Minimal CLI to manage agent skills from GitHub releases.")
console = Console()

# Constants
HOME = Path.home()
SKILLS_DIR_AGENTS = HOME / ".agents" / "skills"
SKILLS_DIR_CLAUDE = HOME / ".claude" / "skills"
CACHE_DIR = HOME / ".agents" / "cache"
LOCK_FILE = HOME / ".agents" / "skills.lock.json"

def ensure_dirs():
    """Ensure all required directories exist."""
    SKILLS_DIR_AGENTS.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR_CLAUDE.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_lock() -> dict:
    """
    Load the skills lock file.
    Structure: { "repos": { "owner/repo": { "tag": "...", "skills": [...] } } }
    """
    if LOCK_FILE.exists():
        try:
            data = json.loads(LOCK_FILE.read_text())
            if "repos" not in data:
                return {"repos": {}}
            return data
        except Exception:
            return {"repos": {}}
    return {"repos": {}}

def save_lock(data: dict):
    """Save the skills lock file."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps(data, indent=2))

def get_latest_release(repo: str):
    """Fetch latest release info from GitHub API."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return data["tag_name"], data["zipball_url"]

def download_release(repo: str, tag: str, url: str) -> Path:
    """Download release zip using gh CLI or requests, with caching."""
    cache_path = CACHE_DIR / f"{repo.replace('/', '_')}_{tag}.zip"
    
    if cache_path.exists():
        return cache_path

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Downloading {repo} {tag}...", total=None)
        
        # Try GH CLI first
        gh_path = shutil.which("gh")
        if gh_path:
            try:
                subprocess.run(
                    [gh_path, "release", "download", tag, "-R", repo, "--archive", "zip", "-O", str(cache_path)],
                    check=True,
                    capture_output=True
                )
                if cache_path.exists():
                    return cache_path
            except subprocess.CalledProcessError:
                pass # Fallback to requests

        # Fallback to requests
        response = requests.get(url, stream=True)
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
        
        for target_dir in [SKILLS_DIR_AGENTS, SKILLS_DIR_CLAUDE]:
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

@app.command()
def add(
    repo: str = typer.Argument(..., help="GitHub repository (owner/repo)"),
    skills: Optional[List[str]] = typer.Option(None, "--skill", "-s", help="Specific skill(s) to add (non-interactive)")
):
    """Add skills from a GitHub release (interactively or via --skill)."""
    ensure_dirs()
    lock = load_lock()
    
    try:
        tag, zip_url = get_latest_release(repo)
    except Exception as e:
        console.print(f"[red]Error fetching release info for {repo}:[/red] {e}")
        raise typer.Exit(1)
        
    zip_path = download_release(repo, tag, zip_url)
    available_skills = get_skills_in_zip(zip_path)
    
    repo_data = lock["repos"].get(repo, {"tag": tag, "skills": []})
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
    
    repo_data["tag"] = tag
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
        for target_dir in [SKILLS_DIR_AGENTS, SKILLS_DIR_CLAUDE]:
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
    """Update installed skills to the latest release."""
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
            
        repo_data = lock["repos"][r]
        console.print(f"Checking updates for [cyan]{r}[/cyan]...")
        
        try:
            tag, zip_url = get_latest_release(r)
        except Exception as e:
            console.print(f"[red]Error fetching release info for {r}:[/red] {e}")
            continue

        if tag == repo_data["tag"]:
            console.print(f"  [green]{r} is already up-to-date (tag: {tag}).[/green]")
            continue

        console.print(f"  Updating from {repo_data['tag']} to [cyan]{tag}[/cyan]...")
        zip_path = download_release(r, tag, zip_url)
        
        for skill in repo_data["skills"]:
            console.print(f"  Updating [cyan]{skill}[/cyan]...")
            install_skill(skill, zip_path)
        
        repo_data["tag"] = tag
        lock["repos"][r] = repo_data
        save_lock(lock)
        console.print(f"  [green]Successfully updated {r} to {tag}![/green]")

@app.command()
def sync():
    """Install all skills as defined in the lock file."""
    ensure_dirs()
    lock = load_lock()
    
    if not lock["repos"]:
        console.print("[yellow]No skills defined in lock file. Use 'add' to add skills.[/yellow]")
        return

    for repo, repo_data in lock["repos"].items():
        tag = repo_data["tag"]
        skills = repo_data["skills"]
        console.print(f"Syncing [cyan]{repo}[/cyan] at [green]{tag}[/green]...")
        
        # Use the tag-specific zipball URL
        zip_url = f"https://api.github.com/repos/{repo}/zipball/{tag}"
        
        try:
            zip_path = download_release(repo, tag, zip_url)
            for skill in skills:
                console.print(f"  Installing [cyan]{skill}[/cyan]...")
                install_skill(skill, zip_path)
        except Exception as e:
            console.print(f"[red]Error syncing {repo}:[/red] {e}")
            continue

    console.print("[green]Synchronization complete![/green]")

if __name__ == "__main__":
    app()
