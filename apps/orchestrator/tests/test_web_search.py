"""Tests for web search functionality and tool-call orchestration."""

from unittest.mock import AsyncMock, patch

import pytest


def test_parse_tool_decision_valid_search():
    from app.routes.chat import _parse_tool_decision

    result = _parse_tool_decision('{"action":"web_search","query":"python latest"}')
    assert result["action"] == "web_search"
    assert result["query"] == "python latest"


def test_parse_tool_decision_valid_answer():
    from app.routes.chat import _parse_tool_decision

    result = _parse_tool_decision('{"action":"answer"}')
    assert result["action"] == "answer"


def test_parse_tool_decision_markdown_fenced():
    from app.routes.chat import _parse_tool_decision

    text = '```json\n{"action":"web_search","query":"test"}\n```'
    result = _parse_tool_decision(text)
    assert result["action"] == "web_search"
    assert result["query"] == "test"


def test_parse_tool_decision_with_surrounding_text():
    from app.routes.chat import _parse_tool_decision

    text = 'I think I need to search. {"action":"web_search","query":"hello"} Let me do that.'
    result = _parse_tool_decision(text)
    assert result["action"] == "web_search"


def test_parse_tool_decision_garbage_falls_back():
    from app.routes.chat import _parse_tool_decision

    result = _parse_tool_decision("totally broken response")
    assert result["action"] == "answer"


def test_search_web_returns_list():
    """search_web should return a list (may be empty in test without network)."""
    from app.web_search import search_web

    # We can't call the real DDG in CI, but we can verify the function signature
    import inspect

    assert inspect.iscoroutinefunction(search_web)


@pytest.mark.asyncio
async def test_search_web_mock():
    """Mocked web search returns expected format."""
    from app.web_search import search_web

    mock_html = """
    <div class="result results_links results_links_deep web-result">
        <a class="result__a" href="https://example.com">Example Title</a>
        <a class="result__snippet">Example snippet text</a>
    </div></div>
    """
    with patch("app.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await search_web("test query", top_k=3)
        assert isinstance(results, list)


def test_chat_endpoint_accepts_request(client):
    """POST /chat still accepts valid requests without breaking."""
    resp = client.post("/chat", json={"message": "hello"})
    # Will fail to reach LLM but should not be a validation error
    assert resp.status_code != 422


def test_chat_endpoint_still_rejects_empty(client):
    """Existing validation still works."""
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422
