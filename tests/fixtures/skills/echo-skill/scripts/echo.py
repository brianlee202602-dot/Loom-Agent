from __future__ import annotations

import argparse
import json
import sys


def parse_args() -> argparse.Namespace:
    '''解析测试脚本的命令行参数。'''
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="default")
    return parser.parse_args()


def main() -> int:
    '''读取标准输入并输出回显结果。'''
    args = parse_args()
    payload = {}
    raw_input = sys.stdin.read().strip()
    if raw_input:
        payload = json.loads(raw_input)

    print(
        json.dumps(
            {
                "ok": True,
                "status": "completed",
                "message": f"echo mode={args.mode}",
                "payload": payload,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
