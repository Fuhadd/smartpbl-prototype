"""Write the API's OpenAPI schema to web/openapi.json, the contract the typed React
client is generated from (`npm run gen:api` in web/).

    uv run python -m scripts.export_openapi

Generated from the app object, not fetched from a server, so it works even where the
/openapi.json route is disabled (any non-local environment). A test fails if the
committed file drifts from the code, so the frontend can't silently fall out of date.
"""

import json
from pathlib import Path

from app.main import app

OUT = Path("web/openapi.json")


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
