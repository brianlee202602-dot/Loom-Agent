from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.agent.llm import ModelClient, RouteSelection
from app.agent.service import AgentService
from app.agent.skills import SkillRegistry
from app.agent.tools import WorkspaceToolExecutor
from app.main import create_app
from app.schemas import AgentRequest


class FakeModelClient(ModelClient):
    '''用于测试场景的假模型客户端。'''

    def __init__(
        self,
        *,
        route_responses: list[RouteSelection] | None = None,
        chat_responses: list[AIMessage] | None = None,
        skill_responses: list[AIMessage] | None = None,
        available: bool = True,
    ) -> None:
        '''按顺序保存测试时要返回的模型结果。'''
        self._route_responses = list(route_responses or [])
        self._chat_responses = list(chat_responses or [])
        self._skill_responses = list(skill_responses or [])
        self._available = available

    @property
    def available(self) -> bool:
        '''标记测试客户端是否可用。'''
        return self._available

    def route(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> RouteSelection:
        '''模拟路由阶段的结构化输出。'''
        if not self._route_responses:
            raise AssertionError("没有可用的 route 响应。")
        return self._route_responses.pop(0)

    def chat(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> AIMessage:
        '''模拟普通对话阶段的模型输出。'''
        if not self._chat_responses:
            raise AssertionError("没有可用的 chat 响应。")
        return self._chat_responses.pop(0)

    def skill(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> AIMessage:
        '''模拟 skill 阶段的模型输出。'''
        if not self._skill_responses:
            raise AssertionError("没有可用的 skill 响应。")
        return self._skill_responses.pop(0)


def build_service(model_client: FakeModelClient) -> AgentService:
    '''构造一个使用测试 skill 目录的 AgentService。'''
    workspace_root = Path(__file__).resolve().parents[1]
    skills_dir = workspace_root / "tests" / "fixtures" / "skills"
    skill_registry = SkillRegistry(
        skills_dir=skills_dir,
        workspace_root=workspace_root,
    )
    tool_executor = WorkspaceToolExecutor(
        workspace_root=workspace_root,
        max_read_chars=8000,
        default_script_timeout_seconds=30,
    )
    return AgentService(
        skill_registry=skill_registry,
        model_client=model_client,
        tool_executor=tool_executor,
        max_skill_model_turns=4,
        max_history_messages=10,
    )


def test_service_requires_available_model_client() -> None:
    '''验证服务初始化时必须提供可用的大模型客户端。'''
    workspace_root = Path(__file__).resolve().parents[1]
    skills_dir = workspace_root / "tests" / "fixtures" / "skills"
    skill_registry = SkillRegistry(
        skills_dir=skills_dir,
        workspace_root=workspace_root,
    )
    tool_executor = WorkspaceToolExecutor(
        workspace_root=workspace_root,
        max_read_chars=8000,
        default_script_timeout_seconds=30,
    )

    try:
        AgentService(
            skill_registry=skill_registry,
            model_client=FakeModelClient(available=False),
            tool_executor=tool_executor,
            max_skill_model_turns=4,
            max_history_messages=10,
        )
    except ValueError as exc:
        assert "必须依赖大模型" in str(exc)
    else:
        raise AssertionError("未配置可用大模型时，AgentService 应拒绝启动。")


def test_plain_chat_response() -> None:
    '''验证未命中 skill 时会直接返回普通对话结果。'''
    service = build_service(
        FakeModelClient(
            route_responses=[RouteSelection(mode="chat")],
            chat_responses=[AIMessage(content="这是普通对话回复。")],
        )
    )
    app = create_app(agent_service=service)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/respond",
        json={
            "chat_id": "chat-1",
            "message_id": "msg-1",
            "user_input": "你好",
            "chat_history": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "chat"
    assert payload["reply_text"] == "这是普通对话回复。"
    assert payload["matched_skill"] is None


def test_frontend_and_health_endpoint() -> None:
    '''验证根路径前端和健康检查接口可用。'''
    service = build_service(
        FakeModelClient(
            route_responses=[RouteSelection(mode="chat")],
            chat_responses=[AIMessage(content="ok")],
        )
    )
    app = create_app(agent_service=service)
    client = TestClient(app)

    index_response = client.get("/")
    health_response = client.get("/healthz")

    assert index_response.status_code == 200
    assert "Loom Agent" in index_response.text
    assert health_response.status_code == 200
    assert health_response.json()["name"] == "Loom Agent"


def test_skill_execution_flow() -> None:
    '''验证命中 skill 后会进入 ToolNode 执行流程并返回最终结果。'''
    service = build_service(
        FakeModelClient(
            route_responses=[
                RouteSelection(
                    mode="skill",
                    matched_skill="echo-skill",
                    skill_reason="用户要求回显",
                )
            ],
            skill_responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_script",
                            "args": {
                                "path": "scripts/echo.py",
                                "args": ["--mode", "skill"],
                                "input_json": '{"extra": "value"}',
                            },
                            "id": "exec_1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="skill 执行完成。"),
            ],
        )
    )

    request = AgentRequest(
        chat_id="chat-2",
        message_id="msg-2",
        user_input="请回显当前请求",
        chat_history=[],
    )
    response = service.handle(request)

    assert response.mode == "skill"
    assert response.matched_skill == "echo-skill"
    assert response.reply_text == "skill 执行完成。"
    assert len(response.tool_traces) == 1
    assert response.tool_traces[0].tool_name == "execute_script"
    assert response.tool_traces[0].success is True


def test_skill_is_aborted_after_too_many_tool_turns() -> None:
    '''验证单个 skill 的工具循环超过上限时会被终止。'''
    repeated_tool_calls = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "execute_script",
                    "args": {
                        "path": "scripts/echo.py",
                    },
                    "id": f"exec_repeat_{index}",
                    "type": "tool_call",
                }
            ],
        )
        for index in range(4)
    ]
    service = build_service(
        FakeModelClient(
            route_responses=[
                RouteSelection(
                    mode="skill",
                    matched_skill="echo-skill",
                    skill_reason="用户要求回显",
                )
            ],
            skill_responses=repeated_tool_calls,
        )
    )

    request = AgentRequest(
        chat_id="chat-abort",
        message_id="msg-abort",
        user_input="请回显当前请求",
        chat_history=[],
    )
    response = service.handle(request)

    assert response.mode == "skill"
    assert response.matched_skill == "echo-skill"
    assert response.reply_text == "skill 已命中，但执行超过最大步骤数，已终止。"
    assert len(response.tool_traces) == 3


def test_skill_trigger_logs_are_emitted(caplog) -> None:
    '''验证命中 skill 时会输出带标记的关键日志。'''
    service = build_service(
        FakeModelClient(
            route_responses=[
                RouteSelection(
                    mode="skill",
                    matched_skill="echo-skill",
                    skill_reason="用户要求回显",
                )
            ],
            skill_responses=[AIMessage(content="skill 执行完成。")],
        )
    )

    request = AgentRequest(
        chat_id="chat-log",
        message_id="msg-log",
        user_input="请回显当前请求",
        chat_history=[],
    )

    with caplog.at_level(logging.INFO, logger="app.agent.service"):
        response = service.handle(request)

    assert response.mode == "skill"
    assert "[SKILL_TRIGGERED]" in caplog.text
    assert "[SKILL_EXECUTION]" in caplog.text
    assert "[SKILL_COMPLETED]" in caplog.text
