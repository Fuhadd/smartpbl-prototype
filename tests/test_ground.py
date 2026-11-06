import pytest

from app.nlp.ground import FUZZY_THRESHOLD, GroundingStatus, ground

SRC = (
    "Lunch visit. Found tablets on the floor under the chair. Ate well. "
    "<PERSON> rang on <PHONE_NUMBER>."
)


def span(g) -> str:
    return SRC[g.start : g.end]


def test_exact_match_returns_source_span() -> None:
    g = ground("tablets on the floor", SRC)
    assert g.status is GroundingStatus.EXACT
    assert span(g) == "tablets on the floor"


def test_normalised_match_maps_offsets_back_to_original() -> None:
    g = ground("FOUND  tablets on the floor", SRC)
    assert g.status is GroundingStatus.NORMALISED
    assert span(g) == "Found tablets on the floor"


def test_typo_corrected_evidence_is_fuzzy_grounded() -> None:
    g = ground("found tablets on the flor under the chair", SRC)
    assert g.status is GroundingStatus.FUZZY
    assert g.score >= FUZZY_THRESHOLD
    assert span(g).startswith("Found tablets on the floor")


def test_placeholders_ground_against_redacted_text() -> None:
    assert ground("<PERSON> rang on <PHONE_NUMBER>", SRC).status is GroundingStatus.EXACT


@pytest.mark.parametrize(
    "fabricated",
    [
        "She fell in the kitchen",  # invented event
        "found on the floor by the bed",  # near-miss: shares words, different meaning
        "refused her tablets",
        "ate well, no concerns",  # real fragment + invented continuation
    ],
)
def test_fabricated_evidence_is_ungrounded(fabricated: str) -> None:
    g = ground(fabricated, SRC)
    assert g.status is GroundingStatus.UNGROUNDED
    assert g.start is None
    assert g.score < FUZZY_THRESHOLD


def test_short_evidence_never_fuzzy_matches() -> None:
    # "the flor" scores highly against "the floor", but two words is too short to trust.
    assert ground("the flor", SRC).status is GroundingStatus.UNGROUNDED


def test_threshold_is_respected() -> None:
    ev = "found tablets on the flor under the chair"
    assert ground(ev, SRC, threshold=99.0).status is GroundingStatus.UNGROUNDED


def test_empty_evidence_is_ungrounded() -> None:
    assert ground("   ", SRC).status is GroundingStatus.UNGROUNDED


def test_limitation_grounding_checks_presence_not_meaning() -> None:
    """A quote lifted out of a negated sentence is still 'grounded'. Negation and category
    correctness are left to human review and evaluation, not to grounding."""
    assert ground("falls", "No falls reported.").status is GroundingStatus.EXACT


def test_fuzzy_span_is_snapped_to_whole_words() -> None:
    g = ground("found tablets on the flor under the chair", SRC)
    assert g.start == 0 or SRC[g.start - 1].isspace()
    assert g.end == len(SRC) or SRC[g.end].isspace()
    assert span(g) == "Found tablets on the floor under the chair."  # raw alignment: "ound…"
