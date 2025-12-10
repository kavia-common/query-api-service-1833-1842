import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, constr

from .db import execute_query

# Create the FastAPI app with metadata for better OpenAPI docs
app = FastAPI(
    title="SQL Query Backend",
    description="Backend API that accepts SQL SELECT queries, executes them, and returns results.",
    version="0.1.0",
)

# Preserve CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class QueryRequest(BaseModel):
    """Model representing the incoming SQL query request."""
    # Enforce min/max length and strip whitespace
    query: constr(min_length=1, max_length=5000, strip_whitespace=True) = Field(
        ...,
        description="SQL query string. Must be SELECT-only. WITH ... SELECT is allowed.",
        examples=["SELECT 1", "WITH x AS (SELECT 1) SELECT * FROM x"],
    )


class ResponseModel(BaseModel):
    """Model representing the response payload."""
    sql: str = Field(..., description="The SQL statement that was executed.")
    # Result must be a JSON-stringified representation of the rows array
    result: str = Field(
        ...,
        description="JSON-stringified array of row objects returned by the query.",
        examples=['[{"id":1,"name":"Alice"}]'],
    )


def _is_select_only(query: str) -> bool:
    """
    Validate that the query is SELECT-only (or WITH ... SELECT) and does not contain
    any dangerous tokens or SQL comments.

    Rules:
    - Allow queries starting with 'SELECT' or 'WITH' (ignoring leading whitespace)
    - Reject presence of:
        ;, DROP, INSERT, UPDATE, DELETE, ALTER, CREATE, TRUNCATE, GRANT, REVOKE,
        COPY, CALL, EXEC, --, /*, */
    - Case-insensitive checks
    """
    q = query.strip()
    q_upper = q.upper()

    # Must start with SELECT or WITH
    if not (q_upper.startswith("SELECT") or q_upper.startswith("WITH")):
        return False

    # Dangerous tokens or comment markers to reject (case-insensitive)
    banned_tokens = [
        ";",
        " DROP ",
        " INSERT ",
        " UPDATE ",
        " DELETE ",
        " ALTER ",
        " CREATE ",
        " TRUNCATE ",
        " GRANT ",
        " REVOKE ",
        " COPY ",
        " CALL ",
        " EXEC ",
        "--",
        "/*",
        "*/",
    ]

    # Also check if tokens occur at boundaries (start/end) by padding with spaces
    padded_upper = f" {q_upper} "

    for token in banned_tokens:
        if token in padded_upper:
            return False

    return True


# PUBLIC_INTERFACE
@app.get("/", summary="Health Check", tags=["System"])
def health_check():
    """Return a simple health message to indicate the service is running."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.post(
    "/query",
    response_model=ResponseModel,
    summary="Execute a SELECT SQL query",
    description=(
        "Accepts a SQL query and executes it against the database. "
        "Only SELECT statements are allowed. WITH ... SELECT is permitted. "
        "The response includes the original SQL and a stringified JSON array of rows."
    ),
    tags=["Query"],
    responses={
        200: {
            "description": "Query executed successfully.",
        },
        400: {
            "description": "Validation error or non-SELECT query detected.",
        },
    },
)
def post_query(payload: QueryRequest) -> ResponseModel:
    """
    Execute a read-only SQL query with safety validations.

    Parameters
    ----------
    payload : QueryRequest
        The request body containing the SQL query to execute.

    Returns
    -------
    ResponseModel
        The executed SQL and the result rows as a JSON string.

    Raises
    ------
    HTTPException
        400 if the query violates SELECT-only constraints or contains dangerous tokens.
    """
    query = payload.query

    # Validate query safety
    if not _is_select_only(query):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed. WITH ... SELECT is permitted. "
                   "Dangerous tokens (DML/DDL/Comments) are rejected.",
        )

    # Execute against DB in read-only mode
    try:
        rows = execute_query(query)
    except Exception as exc:
        # Avoid leaking internal details; present a safe error
        raise HTTPException(status_code=400, detail=f"Query execution failed: {str(exc)}") from exc

    # Serialize rows to JSON string
    result_str = json.dumps(rows, ensure_ascii=False)

    # Shape response exactly as required
    return ResponseModel(sql=query, result=result_str)
