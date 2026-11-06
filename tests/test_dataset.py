import re
from collections import Counter
from pathlib import Path

import pytest

from app.nlp.dataset import LabelledNote, read_jsonl
from app.nlp.schemas import RiskCategory, Severity
from scripts import note_templates as templates
from scripts.generate_notes import OUT_DIR, generate, held_out_phrases


@pytest.fixture(scope="module")
def splits() -> tuple[list[LabelledNote], list[LabelledNote]]:
    return generate()


def all_notes(splits: tuple[list[LabelledNote], list[LabelledNote]]) -> list[LabelledNote]:
    return splits[0] + splits[1]


def test_generation_is_deterministic(splits) -> None:
    assert generate() == splits
    assert generate(seed=7) != splits


def test_split_sizes_and_unique_ids(splits) -> None:
    dev, test = splits
    assert (len(dev), len(test)) == (80, 40)
    ids = [n.note.note_id for n in all_notes(splits)]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("seed", [1, 2, 3, 42])
def test_test_split_balanced_for_any_seed(seed: int) -> None:
    _, test = generate(seed)
    counts = Counter(f.category for n in test for f in n.gold.risk_flags)
    assert counts == dict.fromkeys(RiskCategory, 8)


def test_evidence_is_verbatim_in_note(splits) -> None:
    for n in all_notes(splits):
        for flag in n.gold.risk_flags:
            assert flag.evidence and flag.evidence in n.note.text


def test_negated_categories_carry_no_flag(splits) -> None:
    for n in all_notes(splits):
        flagged = {f.category for f in n.gold.risk_flags}
        assert not flagged & set(n.negated)


def test_follow_up_matches_severity_rule(splits) -> None:
    for n in all_notes(splits):
        expected = any(f.severity != Severity.LOW for f in n.gold.risk_flags)
        assert n.gold.follow_up_required is expected


def test_held_out_phrases_never_in_dev(splits) -> None:
    dev, test = splits
    dev_text = " ".join(n.note.text.lower() for n in dev)
    assert all(p.text.lower() not in dev_text for p in held_out_phrases())
    assert not any("unseen_phrase" in n.tags for n in dev)
    assert any("unseen_phrase" in n.tags for n in test)


_SURNAMES = "|".join(t.lower() for t in templates.SURNAMES)
_FIRSTS = "|".join(t.lower() for t in templates.FIRST_NAMES)
SYNTHETIC_PII = [
    re.compile(rf"^(mrs|ms|miss) ({_SURNAMES})$", re.I),  # client name
    re.compile(rf"^({_FIRSTS}) ({_SURNAMES})$", re.I),  # family member
    re.compile(r"^07700 900\d{3}$"),  # Ofcom drama range
    re.compile(r"^999 \d{3} \d{4}$"),  # NHS test-number range
    re.compile(r"^zz\d{1,2} \d[a-z]{2}$", re.I),  # non-existent ZZ postcode area
    re.compile(r"^\d{1,2}$"),  # house number
    re.compile(rf"^({'|'.join(templates.STREETS)})$", re.I),
]


def test_pii_is_present_and_obviously_synthetic(splits) -> None:
    for n in all_notes(splits):
        for value in n.pii:
            assert value in n.note.text
            assert any(p.match(value) for p in SYNTHETIC_PII), value


def test_committed_data_matches_generator(splits) -> None:
    """Guards against hand-edited or stale data files."""
    dev, test = splits
    assert read_jsonl(Path(OUT_DIR) / "dev.jsonl") == dev
    assert read_jsonl(Path(OUT_DIR) / "test.jsonl") == test
