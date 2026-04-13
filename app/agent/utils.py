from __future__ import annotations

from typing import Any


def to_jsonable(value: Any) -> Any:
    '''把对象递归转换成可 JSON 序列化的普通 Python 结构。'''
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return to_jsonable(value.dict())
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def shorten_text(value: str, limit: int = 280) -> str:
    '''按指定长度截断文本，避免日志或 trace 过长。'''
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


def extract_message_text(content: Any) -> str:
    '''从 LangChain 消息内容中提取适合返回给用户的纯文本。'''
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                    continue
                if isinstance(item.get("content"), str):
                    text_parts.append(item["content"])
        return "\n".join(part.strip() for part in text_parts if part.strip()).strip()

    return str(content).strip()
