# Aos Fatos

The service in `src/services/aosfatos.py` exposes `search_entries(query, page=1)` internally. The dedicated MCP tool `search_aosfatos` adapts its results to the shared search item schema while preserving pagination, stamp, and format. The unified `search_content` tool remains unchanged.

## Configuration

- `AOSFATOS_API_URL`: blog API base URL, default `https://api.aosfatos.org/api/blog`.
- `AOSFATOS_API_KEY`: required when calling the service. Use a read-only key and inject it through the environment, not source code.

The client sends `X-Api-Key: <key>`. The header value contains only the API key, without an authorization scheme prefix.

## Search contract

- Calls `GET /entries/` with `q`, `published=true`, and `page`.
- Reuses the shared asynchronous HTTP client and its configured timeout.
- Fetches only one page per call; the supplied upstream code fixes the page size at 12.
- Validates the response using Pydantic and returns `AosFatosSearchResult` with `total_entries` (upstream `count`), `current_page`, and `results`.
- Each result contains `id`, `title`, `slug`, `publish_date`, `is_published`, `stamp`, and `format` metadata. Other upstream fields are ignored.
- Empty results are valid. HTTP and connection errors propagate; malformed responses raise `AosFatosResponseError`.

Each result also includes a computed `link`, serialized as `https://aosfatos.org/noticias/<slug>` according to the canonical URL contract. It requires no additional request.

The search tool includes `slug` for the dedicated `get_aosfatos_article(slug)` MCP tool. Article retrieval is on demand.

## Article detail

- `fetch_entry(slug)` calls `GET /entries/<slug>/` with `published=true` and the same API key.
- Rejects empty slugs, URLs, paths and query syntax before requesting the API.
- Uses a separate Pydantic detail model: this endpoint does not return numeric `id`.
- Treats 404 and unpublished articles as unavailable. A response with a different slug is invalid.
- Keeps author names only; discards emails and unrelated metadata.
- Removes scripts, styles, noscript elements and promotional `read-more` asides. Plain text separates paragraphs, headings, list items, captions and table rows.
- Preserves editorial references and adds HTTP(S) links from the body. Relative URLs resolve against the canonical article URL; links are not fetched. URLs are deduplicated and explicit reference exclusions are honored.

The detail tool returns title, slug, date, updated_at, canonical link, source, author names, summary (string), excerpt, content, references (name and url), stamp and format. The HTML body is not returned. Cite title, date and link when using article content.

Tests use small synthetic responses based on the supplied upstream code and detail example. Search authentication and sample records were manually verified against the deployed API. Live detail retrieval still needs verification.
