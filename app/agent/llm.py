from __future__ import annotations

from typing import Literal, Protocol, Sequence

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class RouteSelection(BaseModel):
    '''定义路由阶段输出的结构化结果。'''

    mode: Literal["chat", "skill"] = Field(..., description="当前请求应走普通对话还是 skill 执行")
    matched_skill: str | None = Field(
        default=None,
        description="当 mode=skill 时，命中的 skill 名称",
    )
    skill_reason: str | None = Field(
        default=None,
        description="选择该 skill 的简短原因",
    )


class ModelClient(Protocol):
    '''定义 Agent 编排层依赖的模型调用接口。'''

    @property
    def available(self) -> bool:
        '''返回当前模型客户端是否可用。'''
        ...

    def route(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> RouteSelection:
        '''执行路由决策，并返回结构化的 skill / chat 判断结果。'''
        ...

    def chat(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> AIMessage:
        '''执行普通对话生成。'''
        ...

    def skill(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> AIMessage:
        '''在 skill 执行阶段生成下一步动作或最终回复。'''
        ...


class LangChainOpenAIModelClient:
    '''基于 LangChain ChatOpenAI 封装路由、聊天和 skill 执行能力。'''

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        '''初始化底层 ChatOpenAI 客户端。'''
        client_kwargs: dict[str, object] = {
            "model": model,
            "api_key": api_key,
            "request_timeout": timeout_seconds,
            "max_retries": 2,
            "use_responses_api": True,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self._model = ChatOpenAI(**client_kwargs)

    @property
    def available(self) -> bool:
        '''标记当前模型客户端可用。'''
        return True

    def route(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> RouteSelection:
        '''使用结构化输出完成路由决策。'''
        structured_model = self._model.with_structured_output(RouteSelection)
        return structured_model.invoke(
            [SystemMessage(content=instructions), *messages]
        )

    def chat(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
    ) -> AIMessage:
        '''执行普通对话生成。'''
        return self._model.invoke([SystemMessage(content=instructions), *messages])

    def skill(
        self,
        *,
        instructions: str,
        messages: list[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> AIMessage:
        '''在 skill 阶段绑定工具并生成下一步动作。'''
        model_with_tools = self._model.bind_tools(list(tools))
        return model_with_tools.invoke(
            [SystemMessage(content=instructions), *messages]
        )


def build_model_client(
    *,
    api_key: str | None,
    model: str,
    base_url: str | None,
    timeout_seconds: float,
) -> ModelClient:
    '''根据配置构造模型客户端，缺少配置时直接报错。'''
    if not api_key:
        raise ValueError("当前项目必须配置可用的大模型客户端，请提供 LLM_API_KEY。")

    return LangChainOpenAIModelClient(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
