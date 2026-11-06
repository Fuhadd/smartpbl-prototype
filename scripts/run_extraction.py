"""Run LLM extraction over a dataset split and cache predictions as JSONL.

Usage:
  uv run python -m scripts.run_extraction --split dev [--model llama3.1:8b] [--prompt v1]
The test split needs --final: it is opened once, for evaluation (Step 1.9), never for tuning.
Notes are redacted before extraction, exactly as in production.
"""

import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.nlp.dataset import read_jsonl
from app.nlp.extract import ExtractionFailedError, extract
from app.nlp.llm import OllamaClient
from app.nlp.prompts import load_prompt
from app.nlp.redact import redact

DATA_DIR = Path("data/care_notes")
OUT_DIR = Path("data/predictions")


def output_path(split: str, model: str, prompt_version: str) -> Path:
    return OUT_DIR / f"{split}__{model.replace(':', '-')}__{prompt_version}.jsonl"


def main() -> None:
    settings = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--model", default=settings.llm_model)
    ap.add_argument("--prompt", default=settings.extraction_prompt_version)
    ap.add_argument("--final", action="store_true", help="required to run on the test split")
    args = ap.parse_args()
    if args.split == "test" and not args.final:
        sys.exit("Refusing to run on test without --final (test is for evaluation only).")

    client = OllamaClient(
        settings.ollama_base_url,
        args.model,
        timeout_s=settings.llm_timeout_s,
        seed=settings.llm_seed,
    )
    prompt = load_prompt("extraction", args.prompt)
    notes = read_jsonl(DATA_DIR / f"{args.split}.jsonl")
    out = output_path(args.split, args.model, args.prompt)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as f:
        for i, n in enumerate(notes, 1):
            redacted = redact(n.note.text)
            row: dict[str, object] = {"note_id": n.note.note_id, "redacted_text": redacted.text}
            try:
                r = extract(redacted, client, prompt)
                row |= {
                    "extraction": r.extraction.model_dump(mode="json"),
                    "attempts": r.attempts,
                    "latency_ms": r.latency_ms,
                    "errors": list(r.errors),
                    "overrides": list(r.overrides),
                    "model": r.model,
                    "model_digest": r.model_digest,
                    "prompt_version": r.prompt_version,
                    "prompt_sha256": r.prompt_sha256,
                }
            except ExtractionFailedError as e:
                row |= {"extraction": None, "attempts": len(e.errors), "errors": list(e.errors)}
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(f"{i}/{len(notes)} {n.note.note_id} attempts={row['attempts']}", flush=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
