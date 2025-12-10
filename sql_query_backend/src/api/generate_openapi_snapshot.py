"""
PUBLIC_INTERFACE
Utility script to fetch and write the current OpenAPI JSON from a running FastAPI app.

Usage:
    python -m sql_query_backend.src.api.generate_openapi_snapshot http://localhost:3001

This will write the fetched JSON to:
- query-api-service-1833-1842/interfaces/openapi.json
- query-api-service-1833-1842/sql_query_backend/interfaces/openapi.json

Note: This script expects the server to be running and accessible at the provided base URL.
"""
import json
import sys
from urllib.request import urlopen

# Paths relative to repository root for snapshots
TARGETS = [
    "query-api-service-1833-1842/interfaces/openapi.json",
    "query-api-service-1833-1842/sql_query_backend/interfaces/openapi.json",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m sql_query_backend.src.api.generate_openapi_snapshot <base_url>")
        print("Example: python -m sql_query_backend.src.api.generate_openapi_snapshot http://localhost:3001")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    openapi_url = f"{base_url}/openapi.json"

    with urlopen(openapi_url) as resp:
        data = json.load(resp)

    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    for path in TARGETS:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Wrote {path}")

    print("Done.")


if __name__ == "__main__":
    main()
