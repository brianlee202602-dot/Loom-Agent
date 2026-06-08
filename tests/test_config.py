from __future__ import annotations

from pathlib import Path

from app.config import Settings


ENV_KEYS = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "AGENT_WORKSPACE_ROOT",
    "AGENT_SKILLS_DIR",
    "AGENT_LLM_TIMEOUT_SECONDS",
    "AGENT_MAX_SKILL_MODEL_TURNS",
    "AGENT_MAX_TOOL_STEPS",
    "AGENT_TOOL_MAX_READ_CHARS",
    "AGENT_SCRIPT_TIMEOUT_SECONDS",
    "AGENT_MAX_HISTORY_MESSAGES",
    "AGENT_LOG_LEVEL",
)


def clear_settings_env(monkeypatch) -> None:
    '''清理测试相关环境变量，避免污染 BaseSettings 读取结果。'''
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_load_values_from_env_file(tmp_path: Path, monkeypatch) -> None:
    '''验证 Settings 会自动从 .env 文件加载配置。'''
    clear_settings_env(monkeypatch)
    workspace_root = tmp_path / "workspace"
    skills_dir = workspace_root / "custom-skills"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_API_KEY=test-key",
                "LLM_BASE_URL=http://localhost:11434/v1",
                "LLM_MODEL=test-model",
                f"AGENT_WORKSPACE_ROOT={workspace_root}",
                f"AGENT_SKILLS_DIR={skills_dir}",
                "AGENT_LLM_TIMEOUT_SECONDS=12.5",
                "AGENT_MAX_SKILL_MODEL_TURNS=9",
                "AGENT_TOOL_MAX_READ_CHARS=4096",
                "AGENT_SCRIPT_TIMEOUT_SECONDS=22",
                "AGENT_MAX_HISTORY_MESSAGES=15",
                "AGENT_LOG_LEVEL=debug",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_api_key == "test-key"
    assert settings.llm_base_url == "http://localhost:11434/v1"
    assert settings.llm_model == "test-model"
    assert settings.workspace_root == workspace_root.resolve()
    assert settings.skills_dir == skills_dir.resolve()
    assert settings.llm_timeout_seconds == 12.5
    assert settings.max_skill_model_turns == 9
    assert settings.tool_read_max_chars == 4096
    assert settings.script_timeout_seconds == 22
    assert settings.max_history_messages == 15
    assert settings.log_level == "DEBUG"


def test_settings_build_default_skills_dir_from_workspace_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    '''验证未显式提供 skills 目录时会基于工作目录自动补齐。'''
    clear_settings_env(monkeypatch)
    workspace_root = tmp_path / "workspace"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"AGENT_WORKSPACE_ROOT={workspace_root}",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.workspace_root == workspace_root.resolve()
    assert settings.skills_dir == (workspace_root / ".agents" / "skills").resolve()
