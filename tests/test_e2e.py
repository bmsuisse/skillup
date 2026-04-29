import json
import shutil
from pathlib import Path
from bms_skills.cli import app
from typer.testing import CliRunner
import pytest
import bms_skills.cli as cli

runner = CliRunner()

@pytest.fixture
def temp_home(tmp_path):
    """Fixture to mock HOME and redirect all paths to a temp directory."""
    original_home = cli.HOME
    original_agents = cli.SKILLS_DIR_AGENTS
    original_claude = cli.SKILLS_DIR_CLAUDE
    original_cache = cli.CACHE_DIR
    original_lock = cli.LOCK_FILE

    # Setup temp paths
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    
    cli.HOME = fake_home
    cli.SKILLS_DIR_AGENTS = fake_home / ".agents" / "skills"
    cli.SKILLS_DIR_CLAUDE = fake_home / ".claude" / "skills"
    cli.CACHE_DIR = fake_home / ".agents" / "cache"
    cli.LOCK_FILE = fake_home / ".agents" / "skills.lock.json"

    yield fake_home

    # Restore original paths
    cli.HOME = original_home
    cli.SKILLS_DIR_AGENTS = original_agents
    cli.SKILLS_DIR_CLAUDE = original_claude
    cli.CACHE_DIR = original_cache
    cli.LOCK_FILE = original_lock

def test_add_skills_e2e(temp_home):
    """End-to-end test for bmsuisse/skills using --skill."""
    # We use a real repo that we know exists and has skills
    repo = "bmsuisse/skills"
    
    result = runner.invoke(app, ["add", repo, "--skill", "github"])
    assert result.exit_code == 0
    
    # Check if lock file was created
    if cli.LOCK_FILE.exists():
        lock_data = json.loads(cli.LOCK_FILE.read_text())
        assert repo in lock_data["repos"]
        
        # If 'github' was found and installed
        if "github" in lock_data["repos"][repo]["skills"]:
            assert (cli.SKILLS_DIR_AGENTS / "github").exists()
            assert (cli.SKILLS_DIR_CLAUDE / "github").exists()
            assert (cli.SKILLS_DIR_AGENTS / "github" / "SKILL.md").exists()

def test_add_specific_skills_e2e(temp_home):
    """End-to-end test for installing specific skills 'prek' and 'nicegui' from bmsuisse/skills."""
    repo = "bmsuisse/skills"
    
    # Install prek and nicegui
    result = runner.invoke(app, ["add", repo, "--skill", "prek", "--skill", "nicegui"])
    assert result.exit_code == 0
    
    # Check lock file
    assert cli.LOCK_FILE.exists()
    lock_data = json.loads(cli.LOCK_FILE.read_text())
    installed_skills = lock_data["repos"][repo]["skills"]
    
    for skill in ["prek", "nicegui"]:
        assert skill in installed_skills
        
        # Verify existence in both target directories
        for target_dir in [cli.SKILLS_DIR_AGENTS, cli.SKILLS_DIR_CLAUDE]:
            skill_path = target_dir / skill
            assert skill_path.exists(), f"Skill {skill} not found in {target_dir}"
            assert (skill_path / "SKILL.md").exists(), f"SKILL.md for {skill} not found in {target_dir}"
            
            # Verify it's a directory and not empty
            assert skill_path.is_dir()
            assert any(skill_path.iterdir())

def test_remove_skills_e2e(temp_home):
    """End-to-end test for removing skills."""
    # Setup: manually create a lock file and fake skill folders
    repo = "test/repo"
    skill = "test-skill"
    cli.ensure_dirs()
    
    (cli.SKILLS_DIR_AGENTS / skill).mkdir(parents=True)
    (cli.SKILLS_DIR_AGENTS / skill / "SKILL.md").write_text("test")
    
    lock_data = {
        "repos": {
            repo: {
                "tag": "v1.0.0",
                "skills": [skill]
            }
        }
    }
    cli.save_lock(lock_data)
    
    # Verify initial state
    assert (cli.SKILLS_DIR_AGENTS / skill).exists()
    assert cli.LOCK_FILE.exists()
