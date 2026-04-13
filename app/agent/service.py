from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.llm import ModelClient
from app.agent.skills import SkillManifest, SkillRegistry
from app.agent.state import AgentGraphState, ToolTraceEntry
from app.agent.tools import WorkspaceToolExecutor
from app.agent.utils import extract_message_text, shorten_text
from app.schemas import AgentRequest, AgentResponse, ToolTrace

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteDecision:
    '''表示路由阶段的内部判定结果。'''

    mode: Literal["chat", "skill"]
    matched_skill: str | None = None
    skill_reason: str | None = None
    reply_text: str | None = None


class AgentService:
    '''负责统一编排普通对话、skill 路由与工具执行流程。'''

    def __init__(
        self,
        *,
        skill_registry: SkillRegistry,
        model_client: ModelClient,
        tool_executor: WorkspaceToolExecutor,
        max_skill_model_turns: int,
        max_history_messages: int,
    ) -> None:
        '''初始化 Agent 服务依赖，并编译 LangGraph 工作流。'''
        if not model_client.available:
            raise ValueError("当前项目必须依赖大模型运行，不再支持无模型降级路径。")
        self.skill_registry = skill_registry
        self.model_client = model_client
        self.tool_executor = tool_executor
        self.max_skill_model_turns = max_skill_model_turns
        self.max_history_messages = max_history_messages
        self.graph = self._build_graph()

    def handle(self, request: AgentRequest) -> AgentResponse:
        '''处理一次外部请求，并返回统一响应结构。'''
        started_at = time.perf_counter()
        trace_id = uuid.uuid4().hex
        initial_state = self._build_initial_state(request)

        final_state = self.graph.invoke(
            initial_state,
            config={"recursion_limit": max(40, self.max_skill_model_turns * 6)},
        )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        tool_traces = [
            trace if isinstance(trace, ToolTrace) else ToolTrace(**trace)
            for trace in final_state.get("tool_traces", [])
        ]

        return AgentResponse(
            chat_id=request.chat_id,
            message_id=request.message_id,
            trace_id=trace_id,
            mode=final_state.get("route_mode", "chat"),
            matched_skill=final_state.get("matched_skill"),
            skill_reason=final_state.get("skill_reason"),
            reply_text=final_state.get("reply_text", ""),
            tool_traces=tool_traces,
            duration_ms=duration_ms,
        )

    def _build_graph(self):
        '''构建并编译 LangGraph 状态图。'''
        graph = StateGraph(AgentGraphState)
        graph.add_node("route", self._route_node)
        graph.add_node("chat", self._chat_node)
        graph.add_node("load_skill", self._load_skill_node)
        graph.add_node("skill_model", self._skill_model_node)
        graph.add_node(
            "tools",
            ToolNode(
                self.tool_executor.tools,
                name="skill_tools",
                handle_tool_errors=True,
            ),
        )
        graph.add_node("finalize_skill", self._finalize_skill_node)
        graph.add_node("abort_skill", self._abort_skill_node)

        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            self._after_route,
            {
                "chat": "chat",
                "load_skill": "load_skill",
            },
        )
        graph.add_edge("load_skill", "skill_model")
        graph.add_conditional_edges(
            "skill_model",
            self._after_skill_model,
            {
                "tools": "tools",
                "finalize_skill": "finalize_skill",
                "abort_skill": "abort_skill",
            },
        )
        graph.add_edge("tools", "skill_model")
        graph.add_edge("chat", END)
        graph.add_edge("finalize_skill", END)
        graph.add_edge("abort_skill", END)

        return graph.compile()

    def _build_initial_state(self, request: AgentRequest) -> AgentGraphState:
        '''把 FastAPI 请求转换为 LangGraph 初始状态。'''
        return {
            "messages": self._build_messages(request),
            "tool_traces": [],
            "chat_id": request.chat_id,
            "message_id": request.message_id,
            "user_input": request.user_input,
            "chat_history": [item.model_dump() for item in request.chat_history],
            "route_mode": "chat",
            "matched_skill": None,
            "skill_reason": None,
            "reply_text": "",
            "skill_model_turns": 0,
        }

    def _route_node(self, state: AgentGraphState) -> AgentGraphState:
        '''执行路由判定，确定当前请求走普通对话还是 skill。'''
        manifests = self.skill_registry.list_manifests()
        decision = self._route_with_model(state, manifests)

        if decision.mode == "skill" and decision.matched_skill:
            self._log_skill_triggered(state, decision)

        return {
            "route_mode": decision.mode,
            "matched_skill": decision.matched_skill,
            "skill_reason": decision.skill_reason,
            "reply_text": decision.reply_text or "",
        }

    def _after_route(self, state: AgentGraphState) -> Literal["chat", "load_skill"]:
        '''根据路由结果选择下一节点。'''
        if state.get("route_mode") == "skill":
            return "load_skill"
        return "chat"

    def _chat_node(self, state: AgentGraphState) -> AgentGraphState:
        '''处理未命中 skill 时的普通对话逻辑。'''
        ai_message = self.model_client.chat(
            instructions=self._build_chat_instructions(),
            messages=list(state.get("messages", [])),
        )
        return {
            "messages": [ai_message],
            "reply_text": extract_message_text(ai_message.content),
        }

    def _load_skill_node(self, state: AgentGraphState) -> AgentGraphState:
        '''在命中 skill 后加载完整定义，实现渐进式披露。'''
        skill_name = state.get("matched_skill") or ""
        definition = self.skill_registry.load_definition(skill_name)
        LOGGER.info(
            "[SKILL_EXECUTION] chat_id=%s message_id=%s skill=%s available_files=%s",
            state.get("chat_id", ""),
            state.get("message_id", ""),
            skill_name,
            len(definition.available_files),
        )
        return {
            "skill_content": definition.content,
            "skill_description": definition.description,
            "skill_root": str(definition.root_dir),
            "skill_available_files": list(definition.available_files),
            "skill_model_turns": 0,
        }

    def _skill_model_node(self, state: AgentGraphState) -> AgentGraphState:
        '''调用绑定工具的模型，驱动 skill 执行。'''
        ai_message = self.model_client.skill(
            instructions=self._build_skill_instructions(state),
            messages=list(state.get("messages", [])),
            tools=self.tool_executor.tools,
        )
        return {
            "messages": [ai_message],
            # 统计单次 skill 执行中的模型回合数，用于限制 tools 循环。
            "skill_model_turns": int(state.get("skill_model_turns", 0)) + 1,
        }

    def _after_skill_model(
        self,
        state: AgentGraphState,
    ) -> Literal["tools", "finalize_skill", "abort_skill"]:
        '''根据模型输出决定继续调工具、结束 skill 或终止循环。'''
        if tools_condition(state, messages_key="messages") == "tools":
            if int(state.get("skill_model_turns", 0)) >= self.max_skill_model_turns:
                return "abort_skill"
            return "tools"
        return "finalize_skill"

    def _finalize_skill_node(self, state: AgentGraphState) -> AgentGraphState:
        '''从 skill 最后一条模型消息中整理最终回复。'''
        last_message = self._last_ai_message(state)
        reply_text = ""
        if last_message is not None:
            reply_text = extract_message_text(last_message.content)
        if not reply_text:
            reply_text = self._render_fallback_skill_reply(
                state.get("tool_traces", [])
            )
        LOGGER.info(
            "[SKILL_COMPLETED] chat_id=%s message_id=%s skill=%s model_turns=%s reply_preview=%s",
            state.get("chat_id", ""),
            state.get("message_id", ""),
            state.get("matched_skill", ""),
            state.get("skill_model_turns", 0),
            shorten_text(reply_text, 120),
        )
        return {"reply_text": reply_text}

    def _abort_skill_node(self, state: AgentGraphState) -> AgentGraphState:
        '''当 skill 工具循环超过最大步数时返回兜底结果。'''
        LOGGER.warning(
            "[SKILL_ABORTED] chat_id=%s message_id=%s skill=%s model_turns=%s",
            state.get("chat_id", ""),
            state.get("message_id", ""),
            state.get("matched_skill", ""),
            state.get("skill_model_turns", 0),
        )
        return {
            "reply_text": "skill 已命中，但执行超过最大步骤数，已终止。",
        }

    def _route_with_model(
        self,
        state: AgentGraphState,
        manifests: list[SkillManifest],
    ) -> RouteDecision:
        '''使用结构化输出模型完成路由决策。'''
        selection = self.model_client.route(
            instructions=self._build_router_instructions(manifests),
            messages=list(state.get("messages", [])),
        )

        if selection.mode == "skill":
            skill_name = selection.matched_skill or ""
            if any(manifest.name == skill_name for manifest in manifests):
                return RouteDecision(
                    mode="skill",
                    matched_skill=skill_name,
                    skill_reason=selection.skill_reason or "命中 skill",
                )

            LOGGER.warning("模型返回了未知 skill: %s", skill_name)

        return RouteDecision(mode="chat")

    def _build_messages(self, request: AgentRequest) -> list[BaseMessage]:
        '''把历史对话和当前用户输入转换为 LangChain 消息列表。'''
        history_items = request.chat_history[-self.max_history_messages :]
        messages: list[BaseMessage] = []
        for item in history_items:
            if item.role == "system":
                messages.append(SystemMessage(content=item.content))
            elif item.role == "assistant":
                messages.append(AIMessage(content=item.content))
            else:
                messages.append(HumanMessage(content=item.content))

        if (
            not messages
            or not isinstance(messages[-1], HumanMessage)
            or extract_message_text(messages[-1].content) != request.user_input
        ):
            messages.append(HumanMessage(content=request.user_input))
        return messages

    def _last_ai_message(self, state: AgentGraphState) -> AIMessage | None:
        '''从图状态中取出最后一条 AIMessage。'''
        for message in reversed(state.get("messages", [])):
            if isinstance(message, AIMessage):
                return message
        return None

    def _build_chat_instructions(self) -> str:
        '''生成普通对话阶段的系统提示词。'''
        return """
你是一个企业级 Agent 的普通对话助手。
如果当前请求没有命中任何 skill，请直接正常回答用户问题。

要求：
1. 回答使用中文。
2. 不要编造不存在的外部执行结果。
3. 保持回答自然、简洁、可直接返回给终端用户。
""".strip()

    def _build_router_instructions(self, manifests: list[SkillManifest]) -> str:
        '''生成路由阶段的系统提示词。'''
        skill_summaries = json.dumps(
            [manifest.summary for manifest in manifests],
            ensure_ascii=False,
            indent=2,
        )
        return f"""
你是一个企业 Agent 的对话路由器。
你的目标是在“普通对话”和“技能执行”之间做判断。

规则：
1. 只有当用户意图与某个 skill 的能力明确匹配时，才选择 mode=skill。
2. 如果用户只是闲聊、追问、解释、问候、泛化问答，选择 mode=chat。
3. 不要虚构 skill，不要猜测不存在的能力。
4. 输出使用结构化结果，不要输出额外说明。

当前可用的 skill 摘要如下：
{skill_summaries}
""".strip()

    def _build_skill_instructions(self, state: AgentGraphState) -> str:
        '''生成 skill 执行阶段的系统提示词。'''
        available_files = "\n".join(
            f"- {path}" for path in state.get("skill_available_files", [])
        )
        return f"""
你正在执行一个已经命中的 Agent Skill。
请严格遵守 skill 文档，不要脱离技能边界回答。

Skill 名称：{state.get("matched_skill")}
Skill 描述：{state.get("skill_description", "")}

完整 SKILL.md：
{state.get("skill_content", "")}

可按需读取或执行的资源：
{available_files}

执行规则：
1. 已经给你完整的 SKILL.md，不要重复读取 SKILL.md 本身。
2. 只有在需要额外细节时才调用 read_file。
3. 需要真正执行脚本时才调用 execute_script。
4. 如果脚本返回 JSON 且 ok=false，必须如实告知失败原因，不能虚构成功。
5. 工具返回后请继续分析，直到你可以给出最终中文回复。
""".strip()

    def _render_fallback_skill_reply(
        self,
        traces: list[ToolTraceEntry],
    ) -> str:
        '''当模型没有产出最终文本时，根据工具结果返回兜底说明。'''
        if not traces:
            return "skill 已命中，但没有生成最终回复。"
        last_trace = traces[-1]
        if last_trace.get("success"):
            return "skill 已执行完成。"
        return f"skill 执行失败：{last_trace.get('result_preview', '')}"

    def _log_skill_triggered(
        self,
        state: AgentGraphState,
        decision: RouteDecision,
    ) -> None:
        '''记录 skill 命中的关键日志，便于检索和排障。'''
        LOGGER.info(
            "[SKILL_TRIGGERED] chat_id=%s message_id=%s skill=%s reason=%s user_input=%s",
            state.get("chat_id", ""),
            state.get("message_id", ""),
            decision.matched_skill,
            decision.skill_reason or "",
            shorten_text(state.get("user_input", ""), 120),
        )
