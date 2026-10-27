"""Tests for the dedicated Aos Fatos MCP search tool."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp.exceptions import ToolError

from src.services.aosfatos import AosFatosResponseError, AosFatosSearchResult
from src.tools import search_aosfatos


@pytest.fixture
def search_result() -> AosFatosSearchResult:
    """Build a validated page of editorial metadata."""
    return AosFatosSearchResult.model_validate(
        {
            "count": 25,
            "current_page": 2,
            "results": [
                {
                    "id": 42,
                    "title": "Uma checagem",
                    "slug": "uma-checagem",
                    "publish_date": "2026-01-15T12:00:00-03:00",
                    "is_published": True,
                    "stamp": "falso",
                    "format": {
                        "label": "Checagem",
                        "slug": "checagem",
                        "description": "Verificação de informações",
                    },
                }
            ],
        }
    )


@patch("src.tools.search_entries")
async def test_search_aosfatos_adapts_results(
    search: AsyncMock, search_result: AosFatosSearchResult
) -> None:
    search.return_value = search_result

    result = await search_aosfatos("vacinas", page=2)

    assert result == {
        "total_entries": 25,
        "current_page": 2,
        "results": [
            {
                "id": "42",
                "title": "Uma checagem",
                "excerpt": "",
                "date": "2026-01-15",
                "link": "https://aosfatos.org/noticias/uma-checagem",
                "source": "aosfatos",
                "slug": "uma-checagem",
                "stamp": "falso",
                "format": {
                    "label": "Checagem",
                    "slug": "checagem",
                    "description": "Verificação de informações",
                },
            }
        ],
    }
    search.assert_awaited_once_with("vacinas", page=2)


@patch("src.tools.search_entries")
async def test_search_aosfatos_preserves_nullable_metadata(
    search: AsyncMock, search_result: AosFatosSearchResult
) -> None:
    search_result.results[0].stamp = None
    search_result.results[0].format = None
    search.return_value = search_result

    result = await search_aosfatos("vacinas")

    assert result["results"][0]["stamp"] is None
    assert result["results"][0]["format"] is None


@patch("src.tools.search_entries")
async def test_search_aosfatos_returns_empty_search(search: AsyncMock) -> None:
    search.return_value = AosFatosSearchResult.model_validate(
        {"count": 0, "current_page": 1, "results": []}
    )

    result = await search_aosfatos("sem resultados")

    assert result == {"total_entries": 0, "current_page": 1, "results": []}


@pytest.mark.parametrize("query,page", [("", 1), ("  ", 1), ("vacinas", 0)])
@patch("src.tools.search_entries")
async def test_search_aosfatos_rejects_invalid_input(
    search: AsyncMock, query: str, page: int
) -> None:
    with pytest.raises(ToolError, match="termo de busca|página"):
        await search_aosfatos(query, page=page)

    search.assert_not_awaited()


@pytest.mark.parametrize(
    "status,message",
    [(401, "autenticar"), (403, "autenticar"), (429, "Limite"), (500, "consultar")],
)
@patch("src.tools.search_entries")
async def test_search_aosfatos_translates_http_errors(
    search: AsyncMock, status: int, message: str
) -> None:
    response = httpx.Response(status, request=httpx.Request("GET", "https://example.org/"))
    search.side_effect = httpx.HTTPStatusError(
        "Upstream error", request=response.request, response=response
    )

    with pytest.raises(ToolError, match=message):
        await search_aosfatos("vacinas")


@pytest.mark.parametrize(
    "error,message",
    [
        (httpx.ConnectError("Connection failed"), "conectar"),
        (AosFatosResponseError("Unexpected body"), "inválida"),
        (ValueError("Missing key"), "configurada"),
    ],
)
@patch("src.tools.search_entries")
async def test_search_aosfatos_translates_service_errors(
    search: AsyncMock, error: Exception, message: str
) -> None:
    search.side_effect = error

    with pytest.raises(ToolError, match=message):
        await search_aosfatos("vacinas")
