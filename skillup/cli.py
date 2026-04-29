import json
import shutil
from pathlib import Path
from typing import Any, List, Optional

import questionary
import typer
from rich.console import Console

from .github import get_repo_source
from .install import download_release, ensure_dirs, get_skills_in_zip, install_skill
from .lock import apply_source, get_sync_source, load_lock, normalize_repo_data, save_lock
from .settings import format_source_label, settings

app = typer.Typer(help="Minimal CLI to manage agent skills from GitHub releases or branches.")
console = Console()


@app.callback()
def main(
    is_global: bool = typer.Option(False, "--global", "-g", help="Use home directory instead of current directory"),
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
        selected = [s for s in skills if s in available_skills and s not in installed_skills]
        invalid = [s for s in skills if s not in available_skills]
        already_installed = [s for s in skills if s in installed_skills]

        if invalid:
            console.print(f"[yellow]Warning: Skills not found in {repo}: {', '.join(invalid)}[/yellow]")
        if already_installed:
            console.print(f"[blue]Note: Skills already installed from {repo}: {', '.join(already_installed)}[/blue]")
    else:
        to_show = [s for s in available_skills if s not in installed_skills]

        if not to_show:
            console.print(f"[yellow]No new skills available to add from {repo}.[/yellow]")
            return

        selected = questionary.checkbox(
            f"Select skills to add from {repo}:",
            choices=to_show,
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
        choices=all_installed,
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
                import shutil
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
    """Migrate a Claude Code skills-lock.json to the skillup lock format."""
    resolved = input_file if input_file is not None else settings.base_dir / "skills-lock.json"

    if not resolved.exists():
        console.print(f"[red]File not found: {resolved}[/red]")
        raise typer.Exit(1)

    try:
        data = json.loads(resolved.read_text())
    except Exception as e:
        console.print(f"[red]Failed to parse {resolved}:[/red] {e}")
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
