# query-api-service-1833-1842

FastAPI service exposing:
- GET / — Health check
- POST /query — Execute read-only SQL (SELECT or WITH...SELECT)

Configuration:
- The service reads database connection from environment variable `DB_URL`.
- If `DB_URL` is not set, it falls back to parsing `db_connection.txt` in the container root (e.g., containing a line like `psql postgresql://user:pass@host:5432/db` or `sqlite:///path/to.db`). The URL is extracted automatically.
- When neither is provided, the service defaults to `sqlite:///:memory:` for safety and convenience (still read-only).
- Supported schemes:
  - PostgreSQL via `postgresql://...` (requires psycopg2-binary to be installed at runtime).
  - SQLite via `sqlite:///<path>` or `sqlite:///:memory:`.

Environment variables:
- DB_URL: Database connection URL (see examples below).
- APP_PORT: Port for running the FastAPI app locally (e.g., 3001). Note: uvicorn can also be given an explicit --port flag.
- DB_STATEMENT_TIMEOUT_MS (optional, PostgreSQL only): If set to an integer value (milliseconds), applies a per-transaction `statement_timeout` to avoid long-running queries.

db_connection.txt fallback:
- Place a file named `db_connection.txt` at the container root: `query-api-service-1833-1842/db_connection.txt`
- Contents can be one of:
  - A bare URL:
    - `postgresql://user:pass@host:5432/database`
    - `sqlite:////absolute/path/to/app.db`
  - Or a typical CLI-prefixed command from your environment:
    - `psql postgresql://user:pass@host:5432/database`
    - `sqlite:///relative/or/absolute/path.db`
- The service will parse and extract the first matching `postgresql://...` or `sqlite://...` URL.

PostgreSQL example:
- .env
  - `DB_URL=postgresql://app_user:secret@localhost:5432/app_db`
  - Optionally: `DB_STATEMENT_TIMEOUT_MS=5000`
- Requirements
  - Uncomment `psycopg2-binary` in `sql_query_backend/requirements.txt` or install it in your environment.
- Run (choose one)
  - `uvicorn sql_query_backend.src.api.main:app --host 0.0.0.0 --port ${APP_PORT:-3001}`
  - or set APP_PORT in .env and use a process manager that reads it.

SQLite examples:
- File database
  - `.env`:
    - `DB_URL=sqlite:////absolute/path/to/app.db`
- In-memory database (ephemeral per process)
  - `.env`:
    - `DB_URL=sqlite:///:memory:`

Security:
- Only SELECT queries are allowed (WITH...SELECT permitted).
- Read-only transactions are enforced for both PostgreSQL and SQLite connections.
  - PostgreSQL: Session set to READ ONLY; each query runs in `BEGIN READ ONLY` with optional per-request `statement_timeout`.
  - SQLite: File-based databases are opened with `mode=ro` (read-only), and in-memory is isolated per connection.

Install & Run:
1) Install dependencies (prefer virtualenv/venv)
   - `pip install -r sql_query_backend/requirements.txt`
   - For PostgreSQL: ensure `psycopg2-binary` is installed (uncomment it in requirements or `pip install psycopg2-binary`)
2) Configure environment
   - Copy `.env.example` to `.env` and update values, or create `db_connection.txt` with a compatible URL as described above.
3) Start the server
   - From repository root:
     ```
     uvicorn sql_query_backend.src.api.main:app --host 0.0.0.0 --port ${APP_PORT:-3001}
     ```
4) Test the endpoints
   - Health check:
     ```
     curl http://localhost:3001/
     ```
   - Execute a query:
     ```
     curl -X POST http://localhost:3001/query \
       -H 'Content-Type: application/json' \
       -d '{"query": "SELECT 1 AS one"}'
     ```

Response format:
```
{
  "sql": "<original SQL>",
  "result": { "rows": [ { /* row */ }, ... ] }
}
```

Developer note:
- Import `execute_query` from `src/api/db.py` for read-only execution. It enforces the same safety constraints as `execute_readonly_query`.