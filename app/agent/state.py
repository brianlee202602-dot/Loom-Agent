from __future__ import annotations

import operator
from typing import Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict


class ToolTraceEntry(TypedDict):
    '''表示一次工具调用在图状态中的记录结构。'''

    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result_preview: str


class AgentGraphState(TypedDict, total=False):
    '''定义 LangGraph 在运行过程中共享的状态字段。'''

    messages: Annotated[list[BaseMessage], add_messages]
    tool_traces: Annotated[list[ToolTraceEntry], operator.add]
    chat_id: str
    message_id: str
    user_input: str
    chat_history: list[dict[str, Any]]
    route_mode: Literal["chat", "skill"]
    matched_skill: str | None
    skill_reason: str | None
    reply_text: str
    skill_content: str
    skill_description: str
    skill_root: str
    skill_available_files: list[str]
    # 记录单次 skill 执行中已完成的模型回合数，用于防止 tools 循环失控。
    skill_model_turns: int
