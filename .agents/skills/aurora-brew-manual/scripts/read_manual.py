from __future__ import annotations

import argparse
import json
from pathlib import Path


MANUAL_PATH = Path(__file__).resolve().parents[1] / "references" / "product-manual.md"


def parse_args() -> argparse.Namespace:
    '''解析命令行参数。'''
    parser = argparse.ArgumentParser(description="读取幻曜萃饮仪产品说明书。")
    parser.add_argument(
        "--query",
        default="",
        help="可选关键词；提供后仅返回包含关键词的段落。",
    )
    return parser.parse_args()


def load_manual() -> str:
    '''读取说明书全文。'''
    return MANUAL_PATH.read_text(encoding="utf-8")


def filter_sections(content: str, query: str) -> str:
    '''根据关键词提取相关段落。'''
    if not query.strip():
        return content

    normalized_query = query.strip().lower()
    sections = content.split("\n## ")
    matched_sections: list[str] = []

    for index, section in enumerate(sections):
        rendered = section if index == 0 else f"## {section}"
        if normalized_query in rendered.lower():
            matched_sections.append(rendered)

    if matched_sections:
        return "\n\n".join(matched_sections)

    return "未在说明书中找到与该关键词直接匹配的章节。"


def main() -> int:
    '''读取说明书并输出 JSON 结果。'''
    args = parse_args()
    content = load_manual()
    filtered_content = filter_sections(content, args.query)
    result = {
        "ok": True,
        "status": "completed",
        "message": "已读取幻曜萃饮仪说明书。",
        "query": args.query,
        "content": filtered_content,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

