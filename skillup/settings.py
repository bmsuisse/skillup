import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


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
    if source.kind == "release" or not source.commit:
        return source.ref
    short_commit = source.commit[: min(len(source.commit), 7)]
    return f"{source.ref} ({short_commit})"


@dataclass
class Settings:
    is_global: bool = False
    lock_file_override: Optional[Path] = None
    target_dirs_override: Optional[List[Path]] = field(default=None)

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
        return self.base_dir / ".claude" / "skills"

    @property
    def cache_dir(self) -> Path:
        env_cache = os.getenv("SKILLUP_CACHE_DIR")
        if env_cache:
            return Path(env_cache)
        return Path(os.getenv("TEMP", "/tmp")) / "skillup_cache"

    @property
    def lock_file(self) -> Path:
        if self.lock_file_override is not None:
            return self.lock_file_override
        return self.agents_dir / "skills.lock.json"

    @property
    def target_dirs(self) -> List[Path]:
        if self.target_dirs_override is not None:
            return self.target_dirs_override
        return [self.skills_dir_agents, self.skills_dir_claude]


settings = Settings()
