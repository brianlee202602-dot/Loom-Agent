from __future__ import annotations

import argparse
import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_URL = "http://192.168.134.128:8080/navigate"


def parse_args() -> argparse.Namespace:
    '''解析命令行参数。'''
    parser = argparse.ArgumentParser(description="发送去卧室的机器人导航请求。")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="导航请求接口地址。",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="请求超时时间（秒）。",
    )
    return parser.parse_args()


def try_parse_json(value: str) -> dict[str, Any] | list[Any] | None:
    '''尝试解析 JSON 响应。'''
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def post_navigation_request(*, url: str, timeout: float) -> dict[str, Any]:
    '''向固定接口发送卧室导航请求。'''
    payload = {"target": "Bedroom"}
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": "completed",
                "url": url,
                "request_body": payload,
                "status_code": getattr(response, "status", 200),
                "response_json": try_parse_json(response_text),
                "response_text": response_text,
            }
    except HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": "failed",
            "error_type": "HTTP_STATUS_ERROR",
            "url": url,
            "request_body": payload,
            "status_code": exc.code,
            "message": f"接口返回异常状态码：{exc.code}",
            "response_text": response_text,
            "response_json": try_parse_json(response_text),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error_type": "HTTP_REQUEST_ERROR",
            "url": url,
            "request_body": payload,
            "message": f"接口请求失败：{exc}",
        }
    except (TimeoutError, socket.timeout):
        return {
            "ok": False,
            "status": "failed",
            "error_type": "HTTP_TIMEOUT_ERROR",
            "url": url,
            "request_body": payload,
            "message": "接口请求超时。",
        }


def main() -> int:
    '''执行卧室导航请求并输出 JSON 结果。'''
    args = parse_args()
    result = post_navigation_request(url=args.url, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
