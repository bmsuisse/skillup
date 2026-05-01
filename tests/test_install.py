import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from skillup.install import get_skills_in_zip, install_skill
from skillup.settings import settings


def _make_zip(tmp_path: Path, entries: list[str]) -> Path:
    """Create a zip file with the given entries (file paths relative to the repo root)."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for entry in entries:
            z.writestr(entry, f"content of {entry}")
    return zip_path


@pytest.fixture
def temp_dirs(tmp_path):
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


# ---------------------------------------------------------------------------
# get_skills_in_zip
# ---------------------------------------------------------------------------

def test_get_skills_flat(tmp_path):
    """Flat skills (skills/<name>/SKILL.md) are discovered correctly."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/pdf/SKILL.md",
        "owner-repo-abc123/skills/github/SKILL.md",
        "owner-repo-abc123/skills/github/tool.py",
    ])
    skills = get_skills_in_zip(zip_path)
    assert skills == ["github", "pdf"]


def test_get_skills_nested(tmp_path):
    """Nested skills (skills/<category>/<name>/SKILL.md) are discovered correctly."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/engineering/diagnose/SKILL.md",
        "owner-repo-abc123/skills/engineering/tdd/SKILL.md",
        "owner-repo-abc123/skills/misc/summarize/SKILL.md",
    ])
    skills = get_skills_in_zip(zip_path)
    assert skills == ["engineering/diagnose", "engineering/tdd", "misc/summarize"]


def test_get_skills_mixed(tmp_path):
    """Flat and nested skills can coexist."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/pdf/SKILL.md",
        "owner-repo-abc123/skills/engineering/tdd/SKILL.md",
    ])
    skills = get_skills_in_zip(zip_path)
    assert skills == ["engineering/tdd", "pdf"]


def test_get_skills_ignores_no_skill_md(tmp_path):
    """Folders without SKILL.md are not returned."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/draft/notes.txt",
        "owner-repo-abc123/skills/real/SKILL.md",
    ])
    skills = get_skills_in_zip(zip_path)
    assert skills == ["real"]


def test_get_skills_case_insensitive(tmp_path):
    """SKILL.MD is matched case-insensitively."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/mything/skill.md",
    ])
    skills = get_skills_in_zip(zip_path)
    assert skills == ["mything"]


# ---------------------------------------------------------------------------
# install_skill
# ---------------------------------------------------------------------------

def test_install_flat_skill(tmp_path, temp_dirs):
    """A flat skill is installed to both target directories."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/pdf/SKILL.md",
        "owner-repo-abc123/skills/pdf/tool.py",
    ])

    settings.skills_dir_agents.mkdir(parents=True, exist_ok=True)
    settings.skills_dir_claude.mkdir(parents=True, exist_ok=True)

    install_skill("pdf", zip_path)

    assert (settings.skills_dir_agents / "pdf" / "SKILL.md").exists()
    assert (settings.skills_dir_agents / "pdf" / "tool.py").exists()
    assert (settings.skills_dir_claude / "pdf" / "SKILL.md").exists()


def test_install_nested_skill(tmp_path, temp_dirs):
    """A nested skill (category/name) is installed to the correct subdirectory."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/engineering/tdd/SKILL.md",
        "owner-repo-abc123/skills/engineering/tdd/guide.md",
    ])

    settings.skills_dir_agents.mkdir(parents=True, exist_ok=True)
    settings.skills_dir_claude.mkdir(parents=True, exist_ok=True)

    install_skill("engineering/tdd", zip_path)

    assert (settings.skills_dir_agents / "engineering" / "tdd" / "SKILL.md").exists()
    assert (settings.skills_dir_agents / "engineering" / "tdd" / "guide.md").exists()
    assert (settings.skills_dir_claude / "engineering" / "tdd" / "SKILL.md").exists()


def test_install_skill_unknown_does_nothing(tmp_path, temp_dirs):
    """Requesting a non-existent skill name does not raise and creates nothing."""
    zip_path = _make_zip(tmp_path, [
        "owner-repo-abc123/skills/pdf/SKILL.md",
    ])

    settings.skills_dir_agents.mkdir(parents=True, exist_ok=True)
    settings.skills_dir_claude.mkdir(parents=True, exist_ok=True)

    install_skill("nonexistent", zip_path)

    assert not (settings.skills_dir_agents / "nonexistent").exists()
