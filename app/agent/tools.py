from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from app.agent.state import AgentGraphState, ToolTraceEntry
from app.agent.utils import shorten_text


class ToolExecutionError(RuntimeError):
    '''表示工具执行过程中出现了安全性或路径问题。'''


class WorkspaceToolExecutor:
    '''负责在工作区范围内执行 read_file 和 execute_script 两个工具。'''

    def __init__(
        self,
        *,
        workspace_root: Path,
        max_read_chars: int,
        default_script_timeout_seconds: float,
    ) -> None:
        '''初始化工作区工具执行器，并缓存 LangChain 工具对象。'''
        self.workspace_root = workspace_root.resolve()
        self.max_read_chars = max_read_chars
        self.default_script_timeout_seconds = default_script_timeout_seconds
        self._tools = self._build_langchain_tools()

    @property
    def tools(self) -> list[BaseTool]:
        '''返回供 LangGraph ToolNode 使用的工具列表。'''
        return self._tools

    def read_file_raw(
        self,
        *,
        path: str,
        skill_root: Path | None = None,
    ) -> dict[str, Any]:
        '''读取工作区内文本文件，并返回可供模型分析的内容。'''
        try:
            resolved_path = self._resolve_path(path=path, skill_root=skill_root)
            content = resolved_path.read_text(encoding="utf-8-sig", errors="replace")
        except FileNotFoundError:
            return {
                "ok": False,
                "error_type": "FILE_NOT_FOUND",
                "message": f"文件不存在: {path}",
            }
        except IsADirectoryError:
            return {
                "ok": False,
                "error_type": "PATH_IS_DIRECTORY",
                "message": f"路径不是文件: {path}",
            }
        except ToolExecutionError as exc:
            return {
                "ok": False,
                "error_type": "UNSAFE_PATH",
                "message": str(exc),
            }

        truncated = len(content) > self.max_read_chars
        if truncated:
            content = content[: self.max_read_chars]

        return {
            "ok": True,
            "path": self._relative_to_workspace(resolved_path),
            "content": content,
            "truncated": truncated,
        }

    def execute_script_raw(
        self,
        *,
        path: str,
        args: Sequence[str] | None = None,
        input_json: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        skill_root: Path | None = None,
    ) -> dict[str, Any]:
        '''在工作区内执行脚本，并返回标准输出、错误输出和解析结果。'''
        safe_args = [str(item) for item in (args or [])]
        safe_timeout = timeout_seconds or self.default_script_timeout_seconds

        try:
            resolved_path = self._resolve_path(path=path, skill_root=skill_root)
            command = self._build_command(resolved_path, safe_args)
        except ToolExecutionError as exc:
            return {
                "ok": False,
                "error_type": "UNSAFE_SCRIPT",
                "message": str(exc),
            }
        except ValueError as exc:
            return {
                "ok": False,
                "error_type": "UNSUPPORTED_SCRIPT",
                "message": str(exc),
            }

        stdin_text = ""
        if input_json is not None:
            stdin_text = json.dumps(input_json, ensure_ascii=False)

        try:
            completed = subprocess.run(
                command,
                cwd=str(self.workspace_root),
                input=stdin_text,
                text=True,
                capture_output=True,
                timeout=safe_timeout,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error_type": "SCRIPT_TIMEOUT",
                "message": f"脚本执行超时: {safe_timeout} 秒",
                "path": self._relative_to_workspace(resolved_path),
            }

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        parsed_json = self._try_parse_json(stdout)

        return {
            "ok": completed.returncode == 0,
            "path": self._relative_to_workspace(resolved_path),
            "command": command,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_preview": shorten_text(stdout, 600),
            "stderr_preview": shorten_text(stderr, 300),
            "parsed_json": parsed_json,
        }

    def _build_langchain_tools(self) -> list[BaseTool]:
        '''使用 LangChain @tool 装饰器构造工具对象。'''

        @tool
        def read_file(
            path: str,
            state: Annotated[AgentGraphState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            '''按需读取当前 skill 范围内的 UTF-8 文本文件。'''
            skill_root = self._state_skill_root(state)
            result = self.read_file_raw(path=path, skill_root=skill_root)
            return self._build_tool_command(
                tool_name="read_file",
                arguments={"path": path},
                result=result,
                tool_call_id=tool_call_id,
            )

        @tool
        def execute_script(
            path: str,
            state: Annotated[AgentGraphState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            args: list[str] | None = None,
            input_json: str = "",
            timeout_seconds: float | None = None,
        ) -> Command:
            '''执行当前 skill 范围内的脚本，并把结果回传给模型。'''
            payload = self._build_default_script_payload(state)
            if input_json:
                try:
                    extra_payload = json.loads(input_json)
                except json.JSONDecodeError:
                    extra_payload = {"raw_input_json": input_json}

                if isinstance(extra_payload, dict):
                    payload.update(extra_payload)
                else:
                    payload["tool_input"] = extra_payload

            result = self.execute_script_raw(
                path=path,
                args=args or [],
                input_json=payload,
                timeout_seconds=timeout_seconds,
                skill_root=self._state_skill_root(state),
            )
            return self._build_tool_command(
                tool_name="execute_script",
                arguments={
                    "path": path,
                    "args": list(args or []),
                    "input_json": input_json,
                    "timeout_seconds": timeout_seconds,
                },
                result=result,
                tool_call_id=tool_call_id,
            )

        return [read_file, execute_script]

    def _build_tool_command(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        tool_call_id: str,
    ) -> Command:
        '''把原始工具结果转换为 ToolNode 可消费的 Command 更新。'''
        trace: ToolTraceEntry = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": bool(result.get("ok")),
            "result_preview": shorten_text(
                json.dumps(result, ensure_ascii=False), 400
            ),
        }
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_call_id,
                    )
                ],
                "tool_traces": [trace],
            }
        )

    def _build_default_script_payload(
        self,
        state: AgentGraphState,
    ) -> dict[str, Any]:
        '''根据图状态构造 skill 脚本的默认输入载荷。'''
        return {
            "chat_id": state.get("chat_id", ""),
            "message_id": state.get("message_id", ""),
            "user_input": state.get("user_input", ""),
            "chat_history": list(state.get("chat_history", [])),
            "matched_skill": state.get("matched_skill"),
        }

    def _state_skill_root(self, state: AgentGraphState) -> Path | None:
        '''从图状态中提取当前 skill 的根目录。'''
        raw_path = state.get("skill_root")
        if not raw_path:
            return None
        return Path(raw_path)

    def _build_command(self, path: Path, args: list[str]) -> list[str]:
        '''根据脚本后缀生成安全的命令参数数组。'''
        suffix = path.suffix.lower()
        if suffix == ".py":
            return [sys.executable, str(path), *args]
        if suffix == ".ps1":
            return [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(path),
                *args,
            ]
        if suffix in {".cmd", ".bat"}:
            return [str(path), *args]
        raise ValueError(f"当前仅支持 .py / .ps1 / .cmd / .bat 脚本: {path.name}")

    def _resolve_path(self, *, path: str, skill_root: Path | None = None) -> Path:
        '''把相对路径解析为工作区内绝对路径，并阻止越界访问。'''
        candidate = Path(path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            base_dir = skill_root.resolve() if skill_root else self.workspace_root
            resolved = (base_dir / candidate).resolve()
            if not resolved.exists():
                resolved = (self.workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ToolExecutionError(
                f"禁止访问工作区外部路径: {resolved}"
            ) from exc

        return resolved

    def _relative_to_workspace(self, path: Path) -> str:
        '''把绝对路径转换成相对工作区的展示路径。'''
        return path.relative_to(self.workspace_root).as_posix()

    def _try_parse_json(self, value: str) -> dict[str, Any] | list[Any] | None:
        '''尝试把文本解析为 JSON，失败时返回空值。'''
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
