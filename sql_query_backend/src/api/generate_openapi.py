"""
Utility script to generate and export the OpenAPI specification (JSON) for this FastAPI app.

This script imports the app from src/api/main.py and writes the OpenAPI JSON to
the interfaces/openapi.json file in this container.

Usage:
    python -m sql_query_backend.src.api.generate_openapi
or
    python query-api-service-1833-1842/sql_query_backend/src/api/generate_openapi.py
"""

import json
import sys
from pathlib import Path

# Ensure package imports work when running as a script
# Add repository root and container root to sys.path if needed
CURRENT_FILE = Path(__file__).resolve()
CONTAINER_ROOT = CURRENT_FILE.parents[3]  # .../query-api-service-1833-1842/sql_query_backend
REPO_ROOT = CONTAINER_ROOT.parents[1]     # .../ (workspace root)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CONTAINER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTAINER_ROOT))

# Import the FastAPI app
try:
    from sql_query_backend.src.api.main import app  # type: ignore
except Exception as exc:
    print(f"Failed to import FastAPI app: {exc}", file=sys.stderr)
    sys.exit(1)

def main() -> None:
    """
    Generate the OpenAPI spec and write it to interfaces/openapi.json.
    """
    # Build OpenAPI schema from the app
    openapi = app.openapi()

    # Determine output path (interfaces/openapi.json under container root)
    interfaces_dir = CONTAINER_ROOT / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)
    output_path = interfaces_dir / "openapi.json"

    # Write JSON with pretty formatting for readability
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi, f, indent=2, ensure_ascii=False, sort_keys=False)

    print(f"OpenAPI spec written to: {output_path}")

if __name__ == "__main__":
    main()
