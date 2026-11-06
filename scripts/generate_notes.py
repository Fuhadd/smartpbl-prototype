"""Generate the synthetic, gold-labelled care-notes dataset.

Usage: uv run python -m scripts.generate_notes
Writes data/care_notes/{dev,test}.jsonl. Deterministic for a given seed.
"""

import random
import re
from collections import Counter
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

from app.nlp.dataset import GoldFlag, GoldLabel, LabelledNote, write_jsonl
from app.nlp.schemas import CareNote, RiskCategory, Severity
from app.nlp.schemas import MedicationStatus as M
from scripts import note_templates as templates
from scripts.note_templates import RiskPhrase

SEED = 42
# Number of risks per note -> how many notes, per split (same proportions; 80 + 40 = 120).
DEV_MIX = {0: 14, 1: 33, 2: 23, 3: 10}
TEST_MIX = {0: 6, 1: 17, 2: 12, 3: 5}
OUT_DIR = Path("data/care_notes")
BASE_TIME = datetime(2026, 1, 5, 7, 0)


def _abbreviate(text: str) -> str:
    for pattern, short in templates.ABBREVIATIONS.items():
        text = re.sub(pattern, short, text, flags=re.IGNORECASE)
    return text


def _typo(text: str, rng: random.Random) -> str:
    """Swap two adjacent inner letters of one longer word, e.g. 'tablets' -> 'talbets'."""
    words = text.split(" ")
    candidates = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not candidates:
        return text
    i = rng.choice(candidates)
    w = words[i]
    j = rng.randrange(1, len(w) - 2)
    words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2 :]
    return " ".join(words)


def _pii_opening(rng: random.Random) -> tuple[str, list[str]]:
    title, surname = rng.choice(templates.TITLES), rng.choice(templates.SURNAMES)
    values = {
        "title": title,
        "surname": surname,
        "first": f"{rng.choice(templates.FIRST_NAMES)} {surname}",
        "house": str(rng.randint(1, 99)),
        "street": rng.choice(templates.STREETS),
        # "ZZ" is not a real UK postcode area, so this can never match a real address.
        "postcode": f"ZZ{rng.randint(1, 99)} {rng.randint(1, 9)}"
        f"{rng.choice('ABDEFGHJ')}{rng.choice('LNPQRSTU')}",
        "phone": f"07700 900{rng.randint(0, 999):03d}",  # Ofcom drama/fiction range
        "nhs": f"999 {rng.randint(0, 999):03d} {rng.randint(0, 9999):04d}",  # NHS test range
    }
    template = rng.choice(templates.OPENINGS_PII)
    keys = re.findall(r"{(\w+)}", template)
    pii = [f"{values['title']} {values['surname']}"]
    pii += [values[k] for k in keys if k not in {"title", "surname"}]
    return template.format(**values), pii


@cache
def held_out_phrases() -> set[RiskPhrase]:
    """Last phrase of each (category, indirect) group is test-only, to avoid phrase leakage."""
    groups: dict[tuple[RiskCategory, bool], RiskPhrase] = {}
    for p in templates.RISK_PHRASES:
        groups[(p.category, p.indirect)] = p
    return set(groups.values())


def _make_note(
    idx: int, categories: list[RiskCategory], pool: list[RiskPhrase], rng: random.Random
) -> LabelledNote:
    n_risks = len(categories)
    risks = [
        rng.choice([p for p in pool if p.category == c and p.indirect == hard])
        for c in categories
        for hard in [rng.random() < 0.35]
    ]

    # Negation distractor for a category that is NOT a real risk in this note.
    negated: list[RiskCategory] = []
    free = [c for c in RiskCategory if c not in categories]
    if rng.random() < 0.4:
        negated.append(rng.choice(free))

    med_risk = next((r for r in risks if r.category == RiskCategory.MEDICATION), None)
    if med_risk:
        med_status = med_risk.med_status
    elif RiskCategory.MEDICATION in negated:
        med_status = M.TAKEN  # negation phrases state meds were taken
    else:
        med_status = M.TAKEN if rng.random() < 0.6 else M.NOT_MENTIONED
    assert med_status is not None

    body: list[tuple[str, GoldFlag | None]] = [
        (r.text, GoldFlag(category=r.category, severity=r.severity, evidence="")) for r in risks
    ]
    body += [(rng.choice(templates.NEGATIONS[c]), None) for c in negated]
    if med_status == M.TAKEN and RiskCategory.MEDICATION not in negated:
        body.append((rng.choice(templates.MED_TAKEN), None))
    body += [(f, None) for f in rng.sample(templates.FILLERS, rng.randint(1, 3))]
    rng.shuffle(body)

    # Messiness, applied per note; evidence is taken from the *transformed* sentence.
    abbreviate, noisy = rng.random() < 0.4, rng.random() < 0.5
    lowercase, no_stops = rng.random() < 0.15, rng.random() < 0.2

    def style(s: str, allow_noise: bool = True) -> str:
        if abbreviate and allow_noise:
            s = _abbreviate(s)
        if noisy and allow_noise and rng.random() < 0.3:
            s = _typo(s, rng)
        if lowercase:
            s = s.lower()
        return s.rstrip(".") if no_stops else s

    pii: list[str] = []
    if rng.random() < 0.6:
        opening, pii = _pii_opening(rng)
    else:
        opening = rng.choice(templates.OPENINGS_PLAIN)
    sentences = [style(opening, allow_noise=False)]  # keep identifiers intact for redaction tests
    pii = [p.lower() if lowercase else p for p in pii]

    flags: list[GoldFlag] = []
    for text, flag in body:
        styled = style(text)
        sentences.append(styled)
        if flag:
            flags.append(flag.model_copy(update={"evidence": styled}))
    if rng.random() < 0.5:
        sentences.append(style(rng.choice(templates.CLOSINGS), allow_noise=False))

    tags = ["no_risk" if n_risks == 0 else "single" if n_risks == 1 else "multi"]
    tags += [
        t
        for t, on in [
            ("hard", any(r.indirect for r in risks)),
            ("negation", bool(negated)),
            ("noisy", abbreviate or noisy),
            ("lowercase", lowercase),
            ("pii", bool(pii)),
            ("unseen_phrase", any(r in held_out_phrases() for r in risks)),
        ]
        if on
    ]

    note = CareNote(
        note_id=f"N-{idx:04d}",
        client_ref=f"CL-{rng.randint(1, 25):04d}",
        carer_ref=f"CR-{rng.randint(1, 12):04d}",
        visit_time=BASE_TIME + timedelta(days=rng.randint(0, 27), minutes=30 * rng.randint(0, 28)),
        text=" ".join(sentences),
    )
    gold = GoldLabel(
        risk_flags=flags,
        medication_status=med_status,
        follow_up_required=any(f.severity in {Severity.MEDIUM, Severity.HIGH} for f in flags),
    )
    return LabelledNote(note=note, gold=gold, negated=negated, pii=pii, tags=tags)


def _generate_split(
    mix: dict[int, int], pool: list[RiskPhrase], first_id: int, rng: random.Random
) -> list[LabelledNote]:
    schedule = [k for k, n in mix.items() for _ in range(n)]
    rng.shuffle(schedule)
    # Balanced assignment: each note takes the least-used categories so far (random
    # tie-break), so per-category coverage holds by construction rather than by seed luck.
    usage: Counter[RiskCategory] = Counter({c: 0 for c in RiskCategory})
    notes = []
    for i, k in enumerate(schedule):
        tiebreak = {c: rng.random() for c in RiskCategory}
        categories = sorted(RiskCategory, key=lambda c: (usage[c], tiebreak[c]))[:k]
        usage.update(categories)
        notes.append(_make_note(first_id + i, categories, pool, rng))
    return notes


def generate(seed: int = SEED) -> tuple[list[LabelledNote], list[LabelledNote]]:
    """Return (dev, test). Dev never sees held-out phrases; test may use any phrase."""
    rng = random.Random(seed)
    held_out = held_out_phrases()
    dev_pool = [p for p in templates.RISK_PHRASES if p not in held_out]
    dev = _generate_split(DEV_MIX, dev_pool, 1, rng)
    test = _generate_split(TEST_MIX, templates.RISK_PHRASES, len(dev) + 1, rng)
    return dev, test


def category_counts(notes: list[LabelledNote]) -> Counter[str]:
    return Counter(f.category.value for n in notes for f in n.gold.risk_flags)


def main() -> None:
    dev, test = generate()
    write_jsonl(OUT_DIR / "dev.jsonl", dev)
    write_jsonl(OUT_DIR / "test.jsonl", test)
    print(f"seed={SEED} dev={len(dev)} test={len(test)}")
    for name, part in [("dev", dev), ("test", test)]:
        print(name, dict(sorted(category_counts(part).items())))
        print(name, "tags", dict(sorted(Counter(t for n in part for t in n.tags).items())))
        print(name, "med", dict(Counter(n.gold.medication_status.value for n in part)))


if __name__ == "__main__":
    main()
