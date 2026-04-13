from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.agent.llm import build_model_client
from app.agent.service import AgentService
from app.agent.skills import SkillRegistry
from app.agent.tools import WorkspaceToolExecutor
from app.config import Settings
from app.schemas import AgentRequest, AgentResponse


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    '''读取并缓存服务配置，同时初始化日志。'''
    settings = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    return settings


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    '''按配置组装 AgentService 单例。'''
    settings = get_settings()
    skill_registry = SkillRegistry(
        skills_dir=settings.skills_dir,
        workspace_root=settings.workspace_root,
    )
    model_client = build_model_client(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    tool_executor = WorkspaceToolExecutor(
        workspace_root=settings.workspace_root,
        max_read_chars=settings.tool_read_max_chars,
        default_script_timeout_seconds=settings.script_timeout_seconds,
    )
    return AgentService(
        skill_registry=skill_registry,
        model_client=model_client,
        tool_executor=tool_executor,
        max_skill_model_turns=settings.max_skill_model_turns,
        max_history_messages=settings.max_history_messages,
    )


def create_app(agent_service: AgentService | None = None) -> FastAPI:
    '''创建 FastAPI 应用并注册健康检查与主接口。'''
    settings = get_settings()
    app = FastAPI(
        title="Loom Agent",
        version="0.3.0",
        description="Loom Agent 是一个基于 LangGraph + LangChain 的单 Agent 服务，支持 skill 渐进式披露、普通对话和工具执行。",
    )

    service = agent_service or get_agent_service()
    frontend_file = settings.workspace_root / "index.html"

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        '''返回根目录中的最小前端页面。'''
        return FileResponse(frontend_file)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        '''返回服务健康状态与当前 skill 装载情况。'''
        manifests = service.skill_registry.list_manifests()
        return {
            "ok": True,
            "name": "Loom Agent",
            "skills_dir": str(settings.skills_dir),
            "skill_count": len(manifests),
            "llm_available": service.model_client.available,
        }

    @app.post("/api/v1/agent/respond", response_model=AgentResponse)
    def respond(request: AgentRequest) -> AgentResponse:
        '''接收一次 Agent 请求并返回处理结果。'''
        return service.handle(request)

    return app


app = create_app()
