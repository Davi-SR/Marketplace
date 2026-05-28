# Marketplace — AIBI Odontogroup

API FastAPI + DuckDB para dashboards de inteligência competitiva odontológica, com agente Agno/OpenAI para perguntas em linguagem natural e front-end HTML estático.

## Estrutura Docker

O projeto agora possui três ambientes via Docker Compose:

- `dev`: API com reload, código fonte montado e front em Nginx.
- `homolog`: imagens próprias de API e front, um worker e portas separadas.
- `prod`: imagens imutáveis de API e front, API sem porta pública direta e Nginx com proxy `/api`.

Arquivos principais:

```text
Dockerfile                    # multi-stage: target api e target frontend
docker-compose.yml
docker-compose.dev.yml
docker-compose.homolog.yml
docker-compose.prod.yml
nginx/default.conf
env/*.env.example
data/
runtime/
```

## Preparação

Crie o arquivo de variáveis do ambiente desejado a partir dos exemplos:

```powershell
Copy-Item env/dev.env.example env/dev.env
Copy-Item env/homolog.env.example env/homolog.env
Copy-Item env/prod.env.example env/prod.env
```

Edite o arquivo criado e preencha `OPENAI_API_KEY`. Em produção, ajuste também `CORS_ALLOW_ORIGINS` para o domínio real.

Para Docker, configure o caminho do DuckDB no arquivo de ambiente pelo `HOST_DUCKDB_PATH`. No seu ambiente local, por exemplo:

```env
HOST_DUCKDB_PATH=C:/Users/davi.ramos.ODONTOGROUP/Documents/ANS-DB/ANS.db
```

O Compose monta esse arquivo em `/database/ANS.db` dentro do container e a API usa `DB_URL=duckdb:////database/ANS.db`.

Os arquivos `prompts/knowledge.JSON` e `prompts/prompt.md` precisam existir. O histórico do agente será persistido em:

```text
runtime/aibi_storage.db
```

O DuckDB não sobe como serviço separado, porque ele é um banco embarcado baseado em arquivo. No Docker, ele fica disponível para a API via bind mount do arquivo configurado em `HOST_DUCKDB_PATH`.

## Subir Dev

```powershell
docker-compose --env-file env/dev.env -f docker-compose.dev.yml up --build
```

Acessos:

```text
Front: http://localhost:8080
API:   http://localhost:8000
Docs:  http://localhost:8000/docs
```

## Subir Homologação

```powershell
docker-compose --env-file env/homolog.env -f docker-compose.homolog.yml up -d --build
```

Acessos padrão:

```text
Front: http://localhost:8081
API:   http://localhost:8001
Docs:  http://localhost:8001/docs
```

## Subir Produção

```powershell
docker-compose --env-file env/prod.env -f docker-compose.prod.yml up -d --build
```

Acesso padrão:

```text
Front: http://localhost
API:   http://localhost/api
```

Em produção, a API não é exposta diretamente por porta própria. O Nginx do serviço `frontend` encaminha chamadas `/api/*` para o serviço interno `api`.

## Comandos Úteis

Ver logs:

```powershell
docker-compose -f docker-compose.dev.yml logs -f
```

Verificar saúde:

```powershell
curl http://localhost:8000/api/health
```

Se o campo `gold_marketplace_odontogroup_rows` voltar `0`, o Docker está lendo um banco vazio. Confirme se `HOST_DUCKDB_PATH` aponta para o DuckDB populado:

```env
HOST_DUCKDB_PATH=C:/Users/davi.ramos.ODONTOGROUP/Documents/ANS-DB/ANS.db
```

Depois reinicie a API para recarregar o snapshot em memória:

```powershell
docker-compose -f docker-compose.dev.yml restart api
```

Parar ambiente:

```powershell
docker-compose -f docker-compose.dev.yml down
```

Rebuild limpo:

```powershell
docker-compose --env-file env/dev.env -f docker-compose.dev.yml build --no-cache
```

## Observações Operacionais

- `data/` e `runtime/` ficam fora da imagem e não devem ser versionados.
- O banco usado pelo Docker é o arquivo apontado em `HOST_DUCKDB_PATH`; dentro do container ele aparece como `/database/ANS.db`.
- Se o DBeaver estiver conectado ao DuckDB em modo que bloqueia escrita/leitura, a API pode falhar ao abrir o arquivo. Desconecte/feche o DBeaver ou rode o container contra uma cópia do `.db`.
- O front usa `/api` quando servido pelo Nginx, mas mantém fallback para `http://127.0.0.1:8000` quando aberto diretamente via arquivo local.
- O dashboard usa snapshot em memória no startup; após trocar o DuckDB, reinicie os containers.
- O endpoint `/api/chat` depende de `OPENAI_API_KEY`.
