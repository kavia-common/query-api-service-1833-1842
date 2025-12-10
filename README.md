# query-api-service-1833-1842

FastAPI service exposing:
- GET / — Health check
- POST /query — Execute read-only SQL (SELECT or WITH...SELECT)

Configuration:
- The service reads database connection from environment variable `DB_URL`.
- If `DB_URL` is not set, it falls back to parsing `db_connection.txt` in the container root (e.g., containing `psql postgresql://user:pass@host:5432/db` or `sqlite:///path/to.db`).
- Supported schemes:
  - PostgreSQL via `postgresql://...` (requires psycopg2-binary to be installed).
  - SQLite via `sqlite:///<path>` or `sqlite:///:memory:`.

Security:
- Only SELECT queries are allowed (WITH...SELECT permitted).
- Read-only transactions are enforced for both PostgreSQL and SQLite connections.

Environment:
- Set `DB_URL` for your environment or provide a `db_connection.txt` file.
- Optional dependency for PostgreSQL:
  - Uncomment `psycopg2-binary` in `requirements.txt` or install it separately if PostgreSQL connectivity is required.

Response format:
```
{
  "sql": "<original SQL>",
  "result": { "rows": [ { /* row */ }, ... ] }
}
```