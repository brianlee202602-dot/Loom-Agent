from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatHistoryItem(BaseModel):
    '''表示一条历史聊天消息。'''

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="消息角色"
    )
    content: str = Field(..., min_length=1, description="消息内容")


class AgentRequest(BaseModel):
    '''表示 FastAPI 接口接收到的 Agent 请求体。'''

    chat_id: str = Field(..., min_length=1, description="聊天对话 ID")
    message_id: str = Field(..., min_length=1, description="对话文本 ID")
    user_input: str = Field(..., min_length=1, description="当前用户输入")
    chat_history: list[ChatHistoryItem] = Field(
        default_factory=list, description="历史聊天内容"
    )


class ToolTrace(BaseModel):
    '''记录一次工具调用的摘要结果，便于排查问题。'''

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool
    result_preview: str


class AgentResponse(BaseModel):
    '''表示 Agent 返回给调用方的统一响应结构。'''

    chat_id: str
    message_id: str
    trace_id: str
    mode: Literal["chat", "skill"]
    matched_skill: str | None = None
    skill_reason: str | None = None
    reply_text: str
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    duration_ms: int
