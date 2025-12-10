import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Attempt to import psycopg2; if not installed, we'll gracefully fallback to sqlite or raise at runtime if needed
try:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore
    _HAS_PSYCOPG2 = True
except Exception:
    psycopg2 = None  # type: ignore
    _HAS_PSYCOPG2 = False


DB_URL_ENV = "DB_URL"
DB_CONN_TXT = "db_connection.txt"


@dataclass
class ParsedDBUrl:
    """Simple parsed DB URL holder."""
    scheme: str
    url: str


def _read_fallback_db_url_from_file() -> Optional[str]:
    """
    Try to read a database connection URL from db_connection.txt.

    The file often contains strings like:
      - 'psql postgresql://user:pass@host:5432/dbname'
      - 'sqlite:///path/to.db'
    We will extract the URL part if there is a leading tool prefix.
    """
    if not os.path.exists(DB_CONN_TXT):
        return None
    try:
        with open(DB_CONN_TXT, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return None

        # If content contains a URL after a known CLI token like 'psql ' or 'python ' or 'sqlite3 '
        # extract the URL (postgresql:// or sqlite://)
        url_match = re.search(r"(postgresql://[^\s]+|sqlite:(//)?[^\s]+)", content)
        if url_match:
            return url_match.group(0)

        # Otherwise if the entire content looks like a URL we return it
        if content.startswith("postgresql://") or content.startswith("sqlite:"):
            return content
        return None
    except Exception:
        return None


def _get_db_url() -> str:
    """
    Resolve DB URL from environment or db_connection.txt fallback.

    Priority:
      1) Environment variable DB_URL
      2) Parse db_connection.txt for a usable URL
    """
    env_url = os.getenv(DB_URL_ENV)
    if env_url:
        return env_url.strip()

    file_url = _read_fallback_db_url_from_file()
    if file_url:
        return file_url.strip()

    # Default to a local sqlite memory database to avoid total failure; still read-only operations only.
    return "sqlite:///:memory:"


def _parse_db_url(url: str) -> ParsedDBUrl:
    """
    Parse a DB URL and return a structured representation.

    Supports:
      - postgresql://...
      - sqlite:///<path> or sqlite:///:memory:
    """
    if url.startswith("postgresql://"):
        return ParsedDBUrl(scheme="postgresql", url=url)
    if url.startswith("sqlite:///") or url.startswith("sqlite:///:memory:") or url.startswith("sqlite://"):
        return ParsedDBUrl(scheme="sqlite", url=url)
    # Attempt to coerce common URL formats (e.g., postgres://)
    if url.startswith("postgres://"):
        # psycopg2 supports postgres scheme, but normalize to postgresql
        return ParsedDBUrl(scheme="postgresql", url="postgresql://" + url[len("postgres://"):])
    raise ValueError(f"Unsupported DB URL: {url}")


@contextmanager
def _pg_connection_ro(dsn: str):
    """
    PostgreSQL connection context manager that ensures read-only transaction.

    - Connects using psycopg2 (if available)
    - Sets default transaction to read-only
    """
    if not _HAS_PSYCOPG2:
        raise RuntimeError("psycopg2-binary is not installed, cannot connect to PostgreSQL.")
    conn = psycopg2.connect(dsn)
    try:
        # Ensure read-only on the session level
        # autocommit False -> we will manage transactions; set read-only at tx level
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        yield conn
        conn.rollback()  # Ensure no persistent changes (should be none, but rollback to clear tx)
    finally:
        conn.close()


@contextmanager
def _sqlite_connection_ro(url: str):
    """
    SQLite connection context manager that ensures read-only access.

    URL formats:
      - sqlite:///:memory:
      - sqlite:///absolute/or/relative/path.db

    For file-based SQLite, open read-only using URI with mode=ro.
    For memory DB, using read-only doesn't make sense; we still open a memory DB which is isolated per connection.
    """
    # Extract path from sqlite URL
    # sqlite:///:memory: or sqlite:///path/to.db
    path = url[len("sqlite://"):]
    # path now is like "/:memory:" or "///path.db" depending on format
    if path.startswith("///"):
        # file-based path
        db_path = path[2:]  # keep leading slash for absolute path
        # Use URI mode with read-only
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        # Treat other cases, including memory
        if ":memory:" in path:
            conn = sqlite3.connect(":memory:")
        else:
            # conservative fallback: try read-only with provided path trimming leading slashes
            trimmed = path.lstrip("/")
            uri = f"file:/{trimmed}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)

    try:
        # Make rows dict-compatible
        conn.row_factory = sqlite3.Row
        # Enforce read-only via PRAGMA when possible; SQLite read-only is enforced by mode=ro.
        yield conn
        conn.rollback()  # clear any active transaction
    finally:
        conn.close()


def _fetch_rows(cursor, description) -> List[Dict[str, Any]]:
    """Convert DB-API cursor rows to list of dicts using cursor.description for column names."""
    if description is None:
        return []
    col_names = [col[0] for col in description]
    rows: List[Dict[str, Any]] = []
    for rec in cursor.fetchall():
        if isinstance(rec, sqlite3.Row):
            # sqlite Row supports mapping
            rows.append({k: rec[k] for k in rec.keys()})
        elif isinstance(rec, dict):
            rows.append(rec)
        else:
            # tuple-like rows
            rows.append({col_names[i]: rec[i] for i in range(len(col_names))})
    return rows


def _pg_execute_ro(conn, sql: str) -> List[Dict[str, Any]]:
    """
    Execute a single SELECT statement in read-only mode on PostgreSQL and return rows as list of dicts.
    """
    # Use DictCursor for convenience
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:  # type: ignore
        # Start a read-only tx (session set earlier; ensure again at tx level)
        cur.execute("BEGIN READ ONLY")
        cur.execute(sql)
        rows = cur.fetchall()
        # Convert RealDictRow to plain dict
        return [dict(r) for r in rows]


def _sqlite_execute_ro(conn: sqlite3.Connection, sql: str) -> List[Dict[str, Any]]:
    """
    Execute a single SELECT statement in read-only mode on SQLite and return rows as list of dicts.
    """
    cur = conn.cursor()
    try:
        # SQLite auto-begins a transaction when a write occurs; our connection is opened in read-only mode
        cur.execute(sql)
        return _fetch_rows(cur, cur.description)
    finally:
        cur.close()


# PUBLIC_INTERFACE
def execute_readonly_query(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a single read-only SELECT SQL statement against the configured database.

    Resolution:
      - Read DB_URL from environment or db_connection.txt fallback.
      - Support PostgreSQL via psycopg2-binary (if installed).
      - Support SQLite via sqlite3.
      - Enforce read-only transactions.

    Parameters
    ----------
    sql : str
        The SELECT SQL statement to execute.

    Returns
    -------
    List[Dict[str, Any]]
        List of rows as dictionaries.

    Raises
    ------
    RuntimeError
        If database driver is unavailable or URL is unsupported.
    """
    db_url = _get_db_url()
    parsed = _parse_db_url(db_url)

    if parsed.scheme == "postgresql":
        with _pg_connection_ro(parsed.url) as conn:
            return _pg_execute_ro(conn, sql)

    if parsed.scheme == "sqlite":
        with _sqlite_connection_ro(parsed.url) as conn:
            return _sqlite_execute_ro(conn, sql)

    raise RuntimeError(f"Unsupported DB scheme: {parsed.scheme}")
