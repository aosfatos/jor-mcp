# Aos Fatos

O serviço em `src/services/aosfatos.py` disponibiliza internamente `search_entries(query, page=1)`. A ferramenta MCP exclusiva `search_aosfatos` adapta seus resultados ao formato compartilhado de busca, preservando paginação, selo e formato editorial. A ferramenta unificada `search_content` permanece inalterada.

## Configuração

- `AOSFATOS_API_URL`: URL base da API de blog; padrão `https://api.aosfatos.org/api/blog`.
- `AOSFATOS_API_KEY`: obrigatória ao consultar o serviço. Use uma chave somente de leitura e injete-a pelo ambiente, nunca pelo código-fonte.

O cliente envia `X-Api-Key: <chave>`. O valor do header contém somente a chave, sem prefixo de esquema de autorização.

## Contrato de busca

- Consulta `GET /entries/` com `q`, `published=true` e `page`.
- Reutiliza o cliente HTTP assíncrono compartilhado e seu timeout.
- Recupera uma página por chamada; o código de origem fixa 12 itens por página.
- Valida a resposta com Pydantic e retorna `AosFatosSearchResult`, contendo `total_entries` (`count` na origem), `current_page` e `results`.
- Cada resultado contém `id`, `title`, `slug`, `publish_date`, `is_published`, `stamp` e metadados de `format`. Os demais campos são ignorados.
- Resultados vazios são válidos. Erros HTTP e de conexão são propagados; respostas inválidas geram `AosFatosResponseError`.

Cada resultado também inclui `link`, calculado e serializado como `https://aosfatos.org/noticias/<slug>`, conforme o contrato de URL canônica. Isso não exige requisição adicional.

A ferramenta de busca inclui `slug` para a ferramenta MCP exclusiva `get_aosfatos_article(slug)`. O conteúdo integral é recuperado sob demanda.

## Detalhe da matéria

- `fetch_entry(slug)` consulta `GET /entries/<slug>/` com `published=true` e a mesma chave.
- Rejeita slugs vazios, URLs, caminhos e parâmetros antes de consultar a API.
- Usa um modelo Pydantic específico: o detalhe não retorna `id` numérico.
- Trata 404 e matérias não publicadas como indisponíveis. Uma resposta com outro slug é inválida.
- Preserva somente os nomes dos autores; descarta emails e metadados irrelevantes.
- Remove scripts, estilos, elementos noscript e blocos promocionais `read-more`. O texto separa parágrafos, subtítulos, itens de listas, legendas e linhas de tabelas.
- Preserva referências editoriais e acrescenta links HTTP(S) do corpo. URLs relativas são resolvidas contra a URL canônica, sem acessar os links. Elimina URLs duplicadas e respeita exclusões explícitas das referências.

A ferramenta de detalhe retorna title, slug, date, updated_at, link canônico, source, nomes dos autores, summary (string), excerpt, content, references (name e url), stamp e format. O HTML bruto não é retornado. Cite título, data e link ao usar o conteúdo.

Os testes usam respostas sintéticas pequenas baseadas no código de origem e no exemplo de detalhe. A autenticação da busca e registros de exemplo foram verificados manualmente na API implantada. A consulta real de detalhe ainda precisa ser verificada.
