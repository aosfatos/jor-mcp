"""Tests for the Aos Fatos search service."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.aosfatos import AosFatosResponseError, search_entries


@pytest.fixture
def client() -> Generator[AsyncMock, None, None]:
    """Provide a shared HTTP client without starting the application."""
    mock = AsyncMock(spec=httpx.AsyncClient)
    with (
        patch("src.services.aosfatos.get_http_client", return_value=mock),
        patch("src.services.aosfatos.AOSFATOS_API_KEY", "test-key"),
        patch("src.services.aosfatos.AOSFATOS_API_URL", "https://api.example.org/api/blog"),
    ):
        yield mock


@pytest.fixture
def payload() -> dict[str, object]:
    """Provide the relevant fields of a paginated entry response."""
    return {
        "count": 1,
        "current_page": 1,
        "next": None,
        "previous": None,
        "hero": None,
        "results": [
            {
                "id": 42,
                "title": "Uma checagem",
                "slug": "uma-checagem",
                "publish_date": "2026-01-15T12:00:00Z",
                "is_published": True,
                "stamp": None,
                "format": {
                    "label": "Checagem",
                    "slug": "checagem",
                    "description": "Verificação de informações",
                },
                "thumbnail_images": {},
            }
        ],
    }


async def test_search_entries_validates_response(
    client: AsyncMock, payload: dict[str, object]
) -> None:
    client.get.return_value = httpx.Response(
        200, json=payload, request=httpx.Request("GET", "https://api.example.org/")
    )

    result = await search_entries("vacinas")

    assert result.total_entries == 1
    assert result.results[0].slug == "uma-checagem"


async def test_search_entries_includes_canonical_link(
    client: AsyncMock, payload: dict[str, object]
) -> None:
    client.get.return_value = httpx.Response(
        200, json=payload, request=httpx.Request("GET", "https://api.example.org/")
    )

    result = await search_entries("vacinas")

    assert result.model_dump()["results"][0]["link"] == (
        "https://aosfatos.org/noticias/uma-checagem"
    )


async def test_search_entries_sends_authenticated_published_search(
    client: AsyncMock, payload: dict[str, object]
) -> None:
    client.get.return_value = httpx.Response(
        200, json=payload, request=httpx.Request("GET", "https://api.example.org/")
    )

    await search_entries("  vacinas  ", page=2)

    client.get.assert_awaited_once_with(
        "https://api.example.org/api/blog/entries/",
        params={"q": "vacinas", "published": "true", "page": 2},
        headers={"X-Api-Key": "test-key"},
    )


async def test_search_entries_returns_empty_page(client: AsyncMock) -> None:
    client.get.return_value = httpx.Response(
        200,
        json={"count": 0, "current_page": 1, "results": []},
        request=httpx.Request("GET", "https://api.example.org/"),
    )

    result = await search_entries("sem resultados")

    assert result.results == []


@pytest.mark.parametrize("query,page", [("", 1), ("  ", 1), ("vacinas", 0)])
async def test_search_entries_rejects_invalid_input(
    client: AsyncMock, query: str, page: int
) -> None:
    with pytest.raises(ValueError):
        await search_entries(query, page=page)

    client.get.assert_not_awaited()


async def test_search_entries_requires_api_key(client: AsyncMock) -> None:
    with patch("src.services.aosfatos.AOSFATOS_API_KEY", ""):
        with pytest.raises(ValueError, match="AOSFATOS_API_KEY"):
            await search_entries("vacinas")

    client.get.assert_not_awaited()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_search_entries_propagates_http_errors(client: AsyncMock, status: int) -> None:
    client.get.return_value = httpx.Response(
        status, request=httpx.Request("GET", "https://api.example.org/api/blog/entries/")
    )

    with pytest.raises(httpx.HTTPStatusError):
        await search_entries("vacinas")


async def test_search_entries_propagates_connection_errors(client: AsyncMock) -> None:
    client.get.side_effect = httpx.ConnectError("Connection failed")

    with pytest.raises(httpx.ConnectError):
        await search_entries("vacinas")


@pytest.mark.parametrize(
    "body",
    [b"<html>Unavailable</html>", b"[]", b'{"count": 1, "current_page": 1, "results": [{}]}'],
)
async def test_search_entries_rejects_invalid_response(client: AsyncMock, body: bytes) -> None:
    client.get.return_value = httpx.Response(
        200, content=body, request=httpx.Request("GET", "https://api.example.org/")
    )

    with pytest.raises(AosFatosResponseError):
        await search_entries("vacinas")
