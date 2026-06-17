import json
import zipfile
import requests
from pathlib import Path
from skillup.cli import app
from skillup.settings import settings
from skillup.lock import load_lock, save_lock
from skillup.install import ensure_dirs
from typer.testing import CliRunner
import pytest
from unittest.mock import patch, MagicMock

runner = CliRunner()

SKILLS = ["github", "prek", "nicegui"]


@pytest.fixture
def skill_zip(tmp_path):
    """A real zip file with a nested skill tree matching what GitHub serves."""
    zip_path = tmp_path / "skills-v1.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for skill in SKILLS:
            z.writestr(f"repo-v1.0.0/skills/{skill}/SKILL.md", f"# {skill}")
    return zip_path


@pytest.fixture
def temp_dirs(tmp_path):
    """Fixture to mock HOME, CWD and TEMP and redirect all paths to a temp directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_cwd = tmp_path / "cwd"
    fake_cwd.mkdir()
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home), \
         patch("pathlib.Path.cwd", return_value=fake_cwd), \
         patch("os.getenv", side_effect=lambda key, default=None: str(fake_temp) if key == "TEMP" else default):
        settings.is_global = False
        yield fake_home, fake_cwd


@pytest.fixture
def mock_network(skill_zip):
    """Mock only the HTTP layer; use a real zip for skill discovery and installation."""
    with patch("skillup.github.get_latest_release") as mock_latest, \
         patch("skillup.github.get_commit_sha") as mock_commit, \
         patch("skillup.cli.download_release") as mock_download:

        mock_latest.return_value = ("v1.0.0", "http://example.com/zip")
        mock_commit.side_effect = lambda repo, ref: {
            "v1.0.0": "release-sha",
            "v1.1.0": "release-sha-2",
            "main": "main-sha",
            "develop": "develop-sha",
        }.get(ref, f"{ref}-sha")
        mock_download.return_value = skill_zip

        yield {
            "latest": mock_latest,
            "commit": mock_commit,
            "download": mock_download,
        }

def test_add_skills_local_default(temp_dirs, mock_network):
    """Test that skills are installed to CWD by default."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"

    result = runner.invoke(app, ["add", repo, "--skill", "github"])
    if result.exit_code != 0:
        print(result.stdout)
    assert result.exit_code == 0

    lock_file = fake_cwd / ".agents" / "skills.lock.json"
    assert lock_file.exists()
    lock_data = json.loads(lock_file.read_text())
    assert lock_data["repos"][repo]["source"] == "release"
    assert lock_data["repos"][repo]["tag"] == "v1.0.0"
    assert lock_data["repos"][repo]["commit"] == "release-sha"

    assert (fake_cwd / ".agents" / "skills" / "github").exists()
    assert (fake_cwd / ".claude" / "skills" / "github").exists()

    assert not (fake_home / ".agents").exists()

def test_add_skills_global(temp_dirs, mock_network):
    """Test that skills are installed to HOME with --global flag."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"

    result = runner.invoke(app, ["--global", "add", repo, "--skill", "github"])
    if result.exit_code != 0:
        print(result.stdout)
    assert result.exit_code == 0

    lock_file = fake_home / ".agents" / "skills.lock.json"
    assert lock_file.exists()
    lock_data = json.loads(lock_file.read_text())
    assert lock_data["repos"][repo]["source"] == "release"
    assert lock_data["repos"][repo]["commit"] == "release-sha"

    assert (fake_home / ".agents" / "skills" / "github").exists()
    assert (fake_home / ".claude" / "skills" / "github").exists()

    assert not (fake_cwd / ".agents").exists()

def test_remove_skills_local(temp_dirs, mock_network):
    """Test removing skills from local installation."""
    fake_home, fake_cwd = temp_dirs
    repo = "test/repo"
    skill = "test-skill"

    ensure_dirs()
    (settings.skills_dir_agents / skill).mkdir(parents=True)
    (settings.skills_dir_agents / skill / "SKILL.md").write_text("test")

    lock_data = {
        "repos": {
            repo: {
                "tag": "v1.0.0",
                "skills": [skill]
            }
        }
    }
    save_lock(lock_data)

    assert (fake_cwd / ".agents" / "skills" / skill).exists()

    with patch("questionary.checkbox") as mock_checkbox:
        mock_checkbox.return_value.ask.return_value = [f"{repo}: {skill}"]
        result = runner.invoke(app, ["remove"])
        assert result.exit_code == 0

    assert not (fake_cwd / ".agents" / "skills" / skill).exists()
    assert not (fake_cwd / ".agents" / "skills.lock.json").exists()

def test_sync_local(temp_dirs, mock_network):
    """Test sync in local directory."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"
    skill = "github"

    lock_data = {
        "repos": {
            repo: {
                "tag": "v1.0.0",
                "skills": [skill]
            }
        }
    }
    ensure_dirs()
    save_lock(lock_data)

    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0

    assert (fake_cwd / ".agents" / "skills" / skill).exists()
    mock_network["download"].assert_called_with(repo, "v1.0.0", f"https://api.github.com/repos/{repo}/zipball/v1.0.0")

def test_update_local(temp_dirs, mock_network):
    """Test update in local directory."""
    fake_home, fake_cwd = temp_dirs
    repo = "bmsuisse/skills"
    skill = "github"

    ensure_dirs()
    lock_data = {
        "repos": {
            repo: {
                "tag": "v0.9.0",
                "skills": [skill]
            }
        }
    }
    save_lock(lock_data)

    mock_network["latest"].return_value = ("v1.1.0", "http://example.com/zip2")

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "v0.9.0" in result.stdout
    assert "v1.1.0" in result.stdout

    lock = load_lock()
    assert lock["repos"][repo]["tag"] == "v1.1.0"
    assert lock["repos"][repo]["source"] == "release"
    assert lock["repos"][repo]["commit"] == "release-sha-2"

def test_add_skills_from_branch(temp_dirs, mock_network):
    """Test that branch-based installs store branch and commit metadata."""
    fake_home, fake_cwd = temp_dirs
    repo = "anthropics/skills"

    result = runner.invoke(app, ["add", repo, "--branch", "develop", "--skill", "github"])
    assert result.exit_code == 0

    lock = load_lock()
    assert lock["repos"][repo]["source"] == "branch"
    assert lock["repos"][repo]["branch"] == "develop"
    assert lock["repos"][repo]["commit"] == "develop-sha"
    mock_network["latest"].assert_not_called()
    mock_network["download"].assert_called_with(repo, "develop-sha", "https://api.github.com/repos/anthropics/skills/zipball/develop-sha")

def test_add_skills_falls_back_to_main_branch(temp_dirs, mock_network):
    """Test that repos without releases fall back to main."""
    fake_home, fake_cwd = temp_dirs
    repo = "anthropics/skills"

    response = MagicMock(status_code=404)
    mock_network["latest"].side_effect = requests.HTTPError(response=response)

    result = runner.invoke(app, ["add", repo, "--skill", "github"])
    assert result.exit_code == 0

    lock = load_lock()
    assert lock["repos"][repo]["source"] == "branch"
    assert lock["repos"][repo]["branch"] == "main"
    assert lock["repos"][repo]["commit"] == "main-sha"
    mock_network["download"].assert_called_with(repo, "main-sha", "https://api.github.com/repos/anthropics/skills/zipball/main-sha")

def test_cache_dir_override(temp_dirs, mock_network):
    """Test that SKILLUP_CACHE_DIR environment variable overrides the default cache dir."""
    fake_home, fake_cwd = temp_dirs
    custom_cache = fake_home / "custom_cache"
    custom_cache.mkdir()

    with patch("os.getenv", side_effect=lambda key, default=None: str(custom_cache) if key == "SKILLUP_CACHE_DIR" else default):
        assert settings.cache_dir == custom_cache

        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0

        assert custom_cache.exists()


# --- tree selection tests ---

@pytest.fixture
def nested_skill_zip(tmp_path):
    """Zip with skills spread across two subdirectories."""
    zip_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("repo-v1.0.0/tools/hammer/SKILL.md", "# hammer")
        z.writestr("repo-v1.0.0/tools/saw/SKILL.md", "# saw")
        z.writestr("repo-v1.0.0/docs/readme/SKILL.md", "# readme")
    return zip_path


def test_tree_nodes_structure():
    """build_flat_nodes produces directory nodes and leaf nodes in DFS order."""
    from skillup._tree_ui import build_flat_nodes

    skill_paths = {
        "hammer": "tools/hammer",
        "saw": "tools/saw",
        "readme": "docs/readme",
    }
    nodes = build_flat_nodes(skill_paths)
    values = [n.value for n in nodes]

    assert "__dir__:docs" in values
    assert "__dir__:tools" in values
    assert "hammer" in values
    assert "saw" in values
    assert "readme" in values

    # directory node must appear before its children
    tools_idx = values.index("__dir__:tools")
    assert values.index("hammer") > tools_idx
    assert values.index("saw") > tools_idx


def test_toggle_dir_selects_children():
    """Toggling a dir node checks all skills beneath it."""
    from skillup._tree_ui import build_flat_nodes, toggle, dir_state

    skill_paths = {"hammer": "tools/hammer", "saw": "tools/saw", "readme": "docs/readme"}
    nodes = build_flat_nodes(skill_paths)
    tools_idx = next(i for i, n in enumerate(nodes) if n.value == "__dir__:tools")

    assert dir_state(tools_idx, nodes) == "none"
    toggle(tools_idx, nodes)
    assert dir_state(tools_idx, nodes) == "all"
    assert all(nodes[c].checked for c in nodes[tools_idx].children)


def test_toggle_dir_partial_then_full():
    """Dir shows partial state when only some children are checked; toggling again checks all."""
    from skillup._tree_ui import build_flat_nodes, toggle, dir_state

    skill_paths = {"hammer": "tools/hammer", "saw": "tools/saw"}
    nodes = build_flat_nodes(skill_paths)
    tools_idx = next(i for i, n in enumerate(nodes) if n.value == "__dir__:tools")
    hammer_idx = next(i for i, n in enumerate(nodes) if n.value == "hammer")

    toggle(hammer_idx, nodes)
    assert dir_state(tools_idx, nodes) == "some"

    toggle(tools_idx, nodes)  # partial → check all
    assert dir_state(tools_idx, nodes) == "all"

    toggle(tools_idx, nodes)  # all → uncheck all
    assert dir_state(tools_idx, nodes) == "none"


def test_add_interactive_subtree_selection(temp_dirs, nested_skill_zip):
    """Selecting a directory in interactive mode installs all skills under it."""
    fake_home, fake_cwd = temp_dirs
    repo = "org/nested"

    with patch("skillup.github.get_latest_release", return_value=("v1.0.0", "http://x")), \
         patch("skillup.github.get_commit_sha", return_value="sha1"), \
         patch("skillup.cli.download_release", return_value=nested_skill_zip), \
         patch("skillup.cli.tree_checkbox", return_value=["hammer", "saw"]):

        result = runner.invoke(app, ["add", repo])

    assert result.exit_code == 0
    assert (fake_cwd / ".agents" / "skills" / "hammer").exists()
    assert (fake_cwd / ".agents" / "skills" / "saw").exists()
    assert not (fake_cwd / ".agents" / "skills" / "readme").exists()

    lock = load_lock()
    assert sorted(lock["repos"][repo]["skills"]) == ["hammer", "saw"]


def test_add_search_filter(temp_dirs, nested_skill_zip):
    """--search filters the tree to skills whose name or path contains the term."""
    fake_home, fake_cwd = temp_dirs
    repo = "org/nested"

    with patch("skillup.github.get_latest_release", return_value=("v1.0.0", "http://x")), \
         patch("skillup.github.get_commit_sha", return_value="sha1"), \
         patch("skillup.cli.download_release", return_value=nested_skill_zip), \
         patch("skillup.cli.tree_checkbox", return_value=["hammer"]) as mock_tree:

        result = runner.invoke(app, ["add", repo, "--search", "tool"])

    assert result.exit_code == 0
    # Only skills under tools/ passed to the tree UI
    passed_paths = mock_tree.call_args[0][1]
    assert all("tool" in v for v in passed_paths.values())
    assert "readme" not in passed_paths


def test_add_search_no_match(temp_dirs, nested_skill_zip):
    """--search with no matching skills exits early with a message."""
    fake_home, fake_cwd = temp_dirs
    repo = "org/nested"

    with patch("skillup.github.get_latest_release", return_value=("v1.0.0", "http://x")), \
         patch("skillup.github.get_commit_sha", return_value="sha1"), \
         patch("skillup.cli.download_release", return_value=nested_skill_zip):

        result = runner.invoke(app, ["add", repo, "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "nonexistent" in result.stdout
