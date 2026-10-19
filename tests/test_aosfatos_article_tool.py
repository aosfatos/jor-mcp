"""Tests for the Aos Fatos full article MCP tool."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp.exceptions import ToolError

from src.services.aosfatos import (
    AosFatosArticle,
    AosFatosEntryNotFoundError,
    AosFatosInvalidSlugError,
    AosFatosResponseError,
)
from src.tools import get_aosfatos_article


@patch("src.tools.fetch_entry")
async def test_get_aosfatos_article_returns_public_content(fetch: AsyncMock) -> None:
    fetch.return_value = AosFatosArticle.model_validate(
        {
            "title": "Uma reportagem",
            "slug": "uma-reportagem",
            "is_published": True,
            "publish_date": "2026-01-15T12:00:00-03:00",
            "updated_at": "2026-01-16T15:00:00-03:00",
            "summary": "Um resumo",
            "excerpt": "Uma descrição",
            "content": "Texto limpo",
            "authors": [{"name": "Uma Autora", "email": "ignored@example.org"}],
            "references": [{"name": "Fonte", "url": "https://source.org/"}],
        }
    )

    result = await get_aosfatos_article("uma-reportagem")

    assert result == {
        "title": "Uma reportagem",
        "slug": "uma-reportagem",
        "date": "2026-01-15",
        "updated_at": "2026-01-16T15:00:00-03:00",
        "link": "https://aosfatos.org/noticias/uma-reportagem",
        "source": "aosfatos",
        "authors": ["Uma Autora"],
        "summary": "Um resumo",
        "excerpt": "Uma descrição",
        "content": "Texto limpo",
        "references": [{"name": "Fonte", "url": "https://source.org/"}],
        "stamp": None,
        "format": None,
    }
    fetch.assert_awaited_once_with("uma-reportagem")


@pytest.mark.parametrize(
    "error,message",
    [
        (AosFatosInvalidSlugError("Invalid"), "slug"),
        (AosFatosEntryNotFoundError("Missing"), "não encontrada"),
        (AosFatosResponseError("Invalid body"), "inválida"),
        (httpx.ConnectError("Failed"), "conectar"),
        (ValueError("Missing key"), "configurada"),
    ],
)
@patch("src.tools.fetch_entry")
async def test_get_aosfatos_article_translates_service_errors(
    fetch: AsyncMock, error: Exception, message: str
) -> None:
    fetch.side_effect = error

    with pytest.raises(ToolError, match=message):
        await get_aosfatos_article("uma-reportagem")


@pytest.mark.parametrize(
    "status,message",
    [(401, "autenticar"), (403, "autenticar"), (429, "Limite"), (500, "consultar")],
)
@patch("src.tools.fetch_entry")
async def test_get_aosfatos_article_translates_http_errors(
    fetch: AsyncMock, status: int, message: str
) -> None:
    response = httpx.Response(status, request=httpx.Request("GET", "https://example.org/"))
    fetch.side_effect = httpx.HTTPStatusError(
        "Upstream error", request=response.request, response=response
    )

    with pytest.raises(ToolError, match=message):
        await get_aosfatos_article("uma-reportagem")
