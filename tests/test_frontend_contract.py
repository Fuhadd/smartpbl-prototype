"""The React client is generated from web/openapi.json: it must match the live app."""

from pathlib import Path

from scripts.export_openapi import OUT, render


def test_committed_openapi_matches_the_app() -> None:
    assert Path(OUT).read_text(encoding="utf-8") == render(), (
        "web/openapi.json is stale: run `uv run python -m scripts.export_openapi` "
        "and `npm run gen:api` in web/"
    )
