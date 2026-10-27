"""Tests for Aos Fatos article details."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.aosfatos import (
    AosFatosEntryNotFoundError,
    AosFatosInvalidSlugError,
    AosFatosResponseError,
    fetch_entry,
)


@pytest.fixture
def client() -> Generator[AsyncMock, None, None]:
    """Provide a configured client without the server lifespan."""
    mock = AsyncMock(spec=httpx.AsyncClient)
    with (
        patch("src.services.aosfatos.get_http_client", return_value=mock),
        patch("src.services.aosfatos.AOSFATOS_API_KEY", "test-key"),
        patch("src.services.aosfatos.AOSFATOS_API_URL", "https://api.example.org/api/blog"),
    ):
        yield mock


@pytest.fixture
def article_body() -> dict[str, object]:
    """Build a minimal detail response without a list-only id."""
    return {
        "title": "Uma reportagem",
        "slug": "uma-reportagem",
        "is_published": True,
        "publish_date": "2026-01-15T12:00:00-03:00",
        "updated_at": "2026-01-16T15:00:00-03:00",
        "summary": "Primeiro ponto\r\nSegundo ponto",
        "excerpt": "Resumo editorial",
        "content": "<h2>Título</h2><p>Texto <strong>importante</strong>.</p>",
        "authors": [{"name": "Uma Autora", "email": "ignored@example.org"}],
        "references": [],
        "stamp": None,
        "format": None,
    }


async def test_fetch_entry_returns_clean_text(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    result = await fetch_entry("uma-reportagem")

    assert result.content == "Título\n\nTexto importante."
    assert result.authors[0].model_dump() == {"name": "Uma Autora"}


async def test_fetch_entry_requests_published_article(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    await fetch_entry("uma-reportagem")

    client.get.assert_awaited_once_with(
        "https://api.example.org/api/blog/entries/uma-reportagem/",
        params={"published": "true"},
        headers={"X-Api-Key": "test-key"},
    )


async def test_fetch_entry_preserves_sources(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    article_body["references"] = [
        {"name": "Fonte", "url": "https://source.org/", "exclude": False},
        {"name": "Excluída", "url": "https://excluded.org/", "exclude": True},
    ]
    article_body["content"] = (
        "<script>script text</script><style>style text</style>"
        '<p>Veja <a href="https://source.org/">a fonte</a> e '
        '<a href="/noticias/outra/">outra matéria</a>.</p>'
        '<a href="https://excluded.org/">Excluída</a>'
        '<a href="javascript:alert(1)">Não seguir</a>'
        '<a href="#secao">Seção</a><a href="http://[">Inválido</a>'
        '<aside data-type="read-more">Publicidade</aside>'
    )
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    result = await fetch_entry("uma-reportagem")

    assert [(ref.name, ref.url) for ref in result.references] == [
        ("Fonte", "https://source.org/"),
        ("outra matéria", "https://aosfatos.org/noticias/outra/"),
    ]
    assert "script text" not in result.content and "Publicidade" not in result.content


@pytest.mark.parametrize("slug", ["", " ", "../admin", "a/b", "a?x=1", "a%2fb"])
async def test_fetch_entry_rejects_invalid_slug(client: AsyncMock, slug: str) -> None:
    with pytest.raises(AosFatosInvalidSlugError):
        await fetch_entry(slug)

    client.get.assert_not_awaited()


async def test_fetch_entry_rejects_unpublished_article(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    article_body["is_published"] = False
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    with pytest.raises(AosFatosEntryNotFoundError):
        await fetch_entry("uma-reportagem")


async def test_fetch_entry_handles_missing_article(client: AsyncMock) -> None:
    client.get.return_value = httpx.Response(404)

    with pytest.raises(AosFatosEntryNotFoundError):
        await fetch_entry("uma-reportagem")


@pytest.mark.parametrize("body", [b"<html>Unavailable</html>", b"{}", b"[]"])
async def test_fetch_entry_rejects_invalid_response(client: AsyncMock, body: bytes) -> None:
    client.get.return_value = httpx.Response(
        200, content=body, request=httpx.Request("GET", "https://example.org/")
    )

    with pytest.raises(AosFatosResponseError):
        await fetch_entry("uma-reportagem")


async def test_fetch_entry_requires_key(client: AsyncMock) -> None:
    with patch("src.services.aosfatos.AOSFATOS_API_KEY", ""):
        with pytest.raises(ValueError, match="AOSFATOS_API_KEY"):
            await fetch_entry("uma-reportagem")

    client.get.assert_not_awaited()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_fetch_entry_propagates_http_errors(client: AsyncMock, status: int) -> None:
    client.get.return_value = httpx.Response(
        status, request=httpx.Request("GET", "https://example.org/")
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_entry("uma-reportagem")


async def test_fetch_entry_propagates_connection_errors(client: AsyncMock) -> None:
    client.get.side_effect = httpx.ConnectError("Failed")

    with pytest.raises(httpx.ConnectError):
        await fetch_entry("uma-reportagem")


async def test_fetch_entry_preserves_lists_and_captions(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    article_body["content"] = (
        "<p>Primeira linha<br>Segunda linha &amp; dados.</p>"
        "<ul><li>Item um</li><li>Item dois</li></ul>"
        '<figure><img src="image.jpg"><figcaption>Legenda</figcaption></figure>'
        "<table><tr><td>Uma</td><td>célula</td></tr></table>"
    )
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    result = await fetch_entry("uma-reportagem")

    assert result.content == (
        "Primeira linha\n\nSegunda linha & dados.\n\nItem um\n\nItem dois\n\nLegenda\n\nUma célula"
    )


async def test_fetch_entry_rejects_different_slug(
    client: AsyncMock, article_body: dict[str, object]
) -> None:
    article_body["slug"] = "outra-reportagem"
    client.get.return_value = httpx.Response(
        200, json=article_body, request=httpx.Request("GET", "https://example.org/")
    )

    with pytest.raises(AosFatosResponseError):
        await fetch_entry("uma-reportagem")
