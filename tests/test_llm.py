from __future__ import annotations

import pytest

from app.agent.llm import build_model_client


def test_build_model_client_requires_api_key() -> None:
    '''验证缺少 LLM_API_KEY 时不会回退到空实现。'''
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        build_model_client(
            api_key=None,
            model="gpt-5",
            base_url=None,
            timeout_seconds=30,
        )
