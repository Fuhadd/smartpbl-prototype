"""Versioned prompt templates loaded from prompts/<name>/<version>/{system,user}.txt.

The SHA-256 of the template content goes into the audit trail with the version label,
so a prompt edited without a version bump shows up as a hash mismatch.
"""

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
NOTE_SLOT = "{{note}}"


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    user: str
    sha256: str

    def render_user(self, note_text: str) -> str:
        return self.user.replace(NOTE_SLOT, note_text)


@cache
def load_prompt(name: str, version: str) -> PromptTemplate:
    folder = PROMPTS_DIR / name / version
    system = (folder / "system.txt").read_text(encoding="utf-8")
    user = (folder / "user.txt").read_text(encoding="utf-8")
    if NOTE_SLOT not in user:
        raise ValueError(f"{folder}/user.txt has no {NOTE_SLOT} slot")
    digest = hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()
    return PromptTemplate(name=name, version=version, system=system, user=user, sha256=digest)
