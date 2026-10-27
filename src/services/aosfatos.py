"""Read published entries from the Aos Fatos blog API."""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError, computed_field

from src.config import AOSFATOS_API_KEY, AOSFATOS_API_URL
from src.http_client import get_http_client


class AosFatosFormat(BaseModel):
    """Editorial format metadata returned by the API."""

    label: str
    slug: str
    description: str


class AosFatosEntry(BaseModel):
    """Search metadata with a canonical public link derived from the slug."""

    id: int
    title: str
    slug: str
    publish_date: str
    is_published: bool
    stamp: str | None = None
    format: AosFatosFormat | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def link(self) -> str:
        """Return the canonical article URL, including when serializing results."""
        return f"https://aosfatos.org/noticias/{self.slug}"


class AosFatosSearchResult(BaseModel):
    """One page of results; the upstream count is exposed as total_entries."""

    total_entries: int = Field(alias="count", ge=0)
    current_page: int = Field(ge=1)
    results: list[AosFatosEntry]


class AosFatosAuthor(BaseModel):
    """Public author information; unrelated personal fields are discarded."""

    name: str


class AosFatosReference(BaseModel):
    """An editorial reference or a link extracted from the article body."""

    name: str
    url: str
    exclude: bool = False


class AosFatosArticle(BaseModel):
    """Article detail, whose endpoint does not provide the list-only numeric id."""

    title: str
    slug: str
    is_published: bool
    publish_date: str
    updated_at: str
    authors: list[AosFatosAuthor]
    summary: str
    excerpt: str
    content: str
    references: list[AosFatosReference]
    stamp: str | None = None
    format: AosFatosFormat | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def link(self) -> str:
        """Return the canonical article URL."""
        return f"https://aosfatos.org/noticias/{self.slug}"


class AosFatosEntryNotFoundError(LookupError):
    """The requested article does not exist or is not published."""


class AosFatosInvalidSlugError(ValueError):
    """The supplied value is not a single article slug."""


class AosFatosResponseError(ValueError):
    """The API returned invalid JSON or an unexpected response schema."""


def _source_url(href: str, base_url: str) -> str | None:
    """Resolve a public HTTP link without following it or accepting fragment-only links."""
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    try:
        url = urljoin(base_url, href)
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url


def _clean_article(article: AosFatosArticle) -> None:
    """Clean editorial HTML in place and preserve distinct, nonexcluded source links."""
    soup = BeautifulSoup(article.content, "html.parser")
    for tag in soup.select("script, style, noscript, aside[data-type='read-more']"):
        tag.decompose()

    excluded_urls = {
        _source_url(ref.url, article.link)
        for ref in article.references
        if ref.exclude
    }
    references: list[AosFatosReference] = []
    seen: set[str] = set()
    for ref in article.references:
        url = _source_url(ref.url, article.link)
        if url is not None and url not in excluded_urls and url not in seen:
            references.append(AosFatosReference(name=ref.name, url=url))
            seen.add(url)
    for anchor in soup.select("a[href]"):
        url = _source_url(str(anchor["href"]), article.link)
        if url is not None and url not in excluded_urls and url not in seen:
            name = anchor.get_text(" ", strip=True) or url
            references.append(AosFatosReference(name=name, url=url))
            seen.add(url)

    for tag in soup.select("br"):
        tag.replace_with("\n")
    for tag in soup.select("p, div, h1, h2, h3, h4, h5, h6, li, figcaption, summary, tr"):
        tag.append("\n")
    for tag in soup.select("td, th"):
        tag.append(" ")
    lines = [" ".join(line.split()) for line in soup.get_text().splitlines()]
    article.content = "\n\n".join(line for line in lines if line)
    article.references = references


async def search_entries(query: str, page: int = 1) -> AosFatosSearchResult:
    """Search a single page of published entries using the shared HTTP client.

    Args:
        query: Nonempty search terms forwarded to the upstream q filter.
        page: Positive page number. The upstream API fixes the page size at 12.

    Returns:
        Validated search metadata and pagination, including empty results.
        Article content is only available from the separate detail endpoint.

    Raises:
        ValueError: If the query, page, or API key is missing or invalid.
        httpx.HTTPStatusError: If the API responds with an HTTP error.
        httpx.RequestError: If the request fails before receiving a response.
        AosFatosResponseError: If the response does not match the API contract.
    """
    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty")
    if page < 1:
        raise ValueError("Page must be greater than zero")
    if not AOSFATOS_API_KEY:
        raise ValueError("AOSFATOS_API_KEY must be configured")

    response = await get_http_client().get(
        f"{AOSFATOS_API_URL}/entries/",
        params={"q": query, "published": "true", "page": page},
        headers={"X-Api-Key": AOSFATOS_API_KEY},
    )
    response.raise_for_status()

    try:
        return AosFatosSearchResult.model_validate_json(response.content)
    except ValidationError as exc:
        raise AosFatosResponseError("Aos Fatos returned an invalid search response") from exc


async def fetch_entry(slug: str) -> AosFatosArticle:
    """Fetch published article detail with plain text and preserved source links.

    Args:
        slug: A single article slug, not a URL or filesystem path.

    Returns:
        Validated detail with cleaned content and public author names only.

    Raises:
        AosFatosInvalidSlugError: If the slug is empty or contains path/query syntax.
        AosFatosEntryNotFoundError: If the article is missing or unpublished.
        AosFatosResponseError: If the upstream response is invalid.
        ValueError: If the API key is not configured.
        httpx.HTTPStatusError: If the API returns an HTTP error other than 404.
        httpx.RequestError: If the connection fails.
    """
    slug = slug.strip()
    if re.fullmatch(r"[-a-zA-Z0-9_]+", slug) is None:
        raise AosFatosInvalidSlugError("Provide a single article slug")
    if not AOSFATOS_API_KEY:
        raise ValueError("AOSFATOS_API_KEY must be configured")

    response = await get_http_client().get(
        f"{AOSFATOS_API_URL}/entries/{slug}/",
        params={"published": "true"},
        headers={"X-Api-Key": AOSFATOS_API_KEY},
    )
    if response.status_code == 404:
        raise AosFatosEntryNotFoundError("Article not found")
    response.raise_for_status()

    try:
        article = AosFatosArticle.model_validate_json(response.content)
    except ValidationError as exc:
        raise AosFatosResponseError("Aos Fatos returned invalid article detail") from exc
    if not article.is_published:
        raise AosFatosEntryNotFoundError("Article is not published")
    if article.slug != slug:
        raise AosFatosResponseError("Aos Fatos returned a different article slug")
    _clean_article(article)
    return article
