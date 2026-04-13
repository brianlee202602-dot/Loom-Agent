from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    '''集中管理 Agent 服务运行所需的环境配置。'''

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    workspace_root: Path = Field(
        default_factory=Path.cwd,
        alias="AGENT_WORKSPACE_ROOT",
    )
    skills_dir: Path | None = Field(
        default=None,
        alias="AGENT_SKILLS_DIR",
    )
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-5", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(
        default=60.0,
        alias="AGENT_LLM_TIMEOUT_SECONDS",
    )
    max_skill_model_turns: int = Field(
        default=6,
        alias="AGENT_MAX_SKILL_MODEL_TURNS",
    )
    tool_read_max_chars: int = Field(
        default=16000,
        alias="AGENT_TOOL_MAX_READ_CHARS",
    )
    script_timeout_seconds: float = Field(
        default=60.0,
        alias="AGENT_SCRIPT_TIMEOUT_SECONDS",
    )
    max_history_messages: int = Field(
        default=20,
        alias="AGENT_MAX_HISTORY_MESSAGES",
    )
    log_level: str = Field(default="INFO", alias="AGENT_LOG_LEVEL")

    @field_validator("workspace_root", "skills_dir", mode="before")
    @classmethod
    def normalize_optional_path(cls, value: object) -> object:
        '''把空字符串标准化为空值，避免生成无意义路径。'''
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        '''统一日志等级大小写。'''
        return value.upper()

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        '''解析工作目录与默认 skills 目录。'''
        workspace_root = Path(self.workspace_root).resolve()
        skills_dir = self.skills_dir
        if skills_dir is None:
            skills_dir = workspace_root / ".agents" / "skills"

        self.workspace_root = workspace_root
        self.skills_dir = Path(skills_dir).resolve()
        return self
