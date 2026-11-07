from datetime import datetime

import pytest

from app.nlp.dataset import GoldFlag, GoldLabel, LabelledNote
from app.nlp.evaluation import (
    MISSED,
    NONE,
    Prediction,
    bootstrap_ci,
    evaluate,
    paired_bootstrap,
    union_recall,
)
from app.nlp.schemas import (
    CareNote,
    Extraction,
    MedicationStatus,
    RiskCategory,
    RiskFlag,
    Severity,
)

C, S = RiskCategory, Severity
LATE = "Arrived at 10:15 for the 8:30 call, nobody had been in."
FALL = "Found on the floor by the bed."
TEXT = f"{LATE} {FALL} Ate all of breakfast."


def note(
    nid: str,
    gold: list[tuple[RiskCategory, Severity, str]],
    text: str = TEXT,
    negated: tuple[RiskCategory, ...] = (),
    tags: tuple[str, ...] = (),
) -> LabelledNote:
    return LabelledNote(
        note=CareNote(
            note_id=nid,
            client_ref="CL-0001",
            carer_ref="CR-0001",
            visit_time=datetime(2026, 1, 1, 9),
            text=text,
        ),
        gold=GoldLabel(
            risk_flags=[GoldFlag(category=c, severity=s, evidence=e) for c, s, e in gold],
            medication_status=MedicationStatus.NOT_MENTIONED,
            follow_up_required=bool(gold),
        ),
        negated=list(negated),
        pii=[],
        tags=list(tags),
    )


def pred(
    nid: str,
    flags: list[tuple[RiskCategory, Severity, str]] | None,
    text: str = TEXT,
    attempts: int = 1,
    latency_ms: float | None = 1000.0,
) -> Prediction:
    ext = None
    if flags is not None:
        ext = Extraction(
            risk_flags=[
                RiskFlag(category=c, severity=s, evidence=e, confidence=0.9) for c, s, e in flags
            ],
            medication_status=MedicationStatus.NOT_MENTIONED,
            follow_up_required=True,
            summary="Synthetic.",
        )
    return Prediction(nid, text, ext, attempts, latency_ms)


GOLD = [note("N1", [(C.MISSED_LATE_VISIT, S.MEDIUM, LATE), (C.FALLS, S.HIGH, FALL)])]


def test_failed_extraction_counts_every_gold_flag_as_missed() -> None:
    r = evaluate("x", GOLD, {"N1": pred("N1", None, attempts=2, latency_ms=None)})
    assert (r.report.micro.tp, r.report.micro.fn) == (0, 2)
    assert (r.valid_first_try, r.valid_final) == (0, 0)
    assert r.latencies_ms == []


def test_confusion_separates_mislabels_from_misses_and_false_positives() -> None:
    p = pred(
        "N1",
        [
            (C.SAFEGUARDING, S.HIGH, "nobody had been in"),  # late visit filed as safeguarding
            (C.FALLS, S.HIGH, FALL),
            (C.NUTRITION_HYDRATION, S.LOW, "Ate all of breakfast"),  # pure false positive
        ],
    )
    r = evaluate("x", GOLD, {"N1": p})
    assert r.confusion[C.FALLS.value] == {C.FALLS.value: 1}
    assert r.confusion[C.MISSED_LATE_VISIT.value] == {C.SAFEGUARDING.value: 1}
    assert r.confusion[NONE] == {C.NUTRITION_HYDRATION.value: 1}
    assert MISSED not in r.confusion[C.MISSED_LATE_VISIT.value]


def test_unmatched_gold_flag_lands_in_not_found_column() -> None:
    r = evaluate("x", GOLD, {"N1": pred("N1", [(C.FALLS, S.HIGH, FALL)])})
    assert r.confusion[C.MISSED_LATE_VISIT.value] == {MISSED: 1}


def test_severity_agreement_only_over_matched_categories() -> None:
    p = pred("N1", [(C.FALLS, S.MEDIUM, FALL), (C.MISSED_LATE_VISIT, S.MEDIUM, LATE)])
    r = evaluate("x", GOLD, {"N1": p})
    assert (r.severity_matches, r.severity_pairs) == (1, 2)


def test_negation_false_positive_counted() -> None:
    text = "No signs of falls today. Ate all of breakfast."
    gold = [note("N1", [], text=text, negated=(C.FALLS,))]
    p = pred("N1", [(C.FALLS, S.LOW, "No signs of falls today")], text=text)
    r = evaluate("x", gold, {"N1": p})
    assert (r.negated_mentions, r.negated_false_positives) == (1, 1)
    assert r.report.micro.fp == 1


def test_subset_recall_by_tag() -> None:
    gold = [
        note("N1", [(C.FALLS, S.HIGH, FALL)], tags=("unseen_phrase",)),
        note("N2", [(C.FALLS, S.HIGH, FALL)], tags=("noisy",)),
    ]
    preds = {"N1": pred("N1", []), "N2": pred("N2", [(C.FALLS, S.HIGH, FALL)])}
    r = evaluate("x", gold, preds)
    assert r.subset_recall == {"noisy": (1, 1), "unseen_phrase": (0, 1)}


def test_missing_prediction_is_an_error() -> None:
    with pytest.raises(ValueError, match="no prediction"):
        evaluate("x", GOLD, {})


def test_routing_counts_baseline_safety_net() -> None:
    """LLM failed; the rules still flag the fall, so it doesn't escape."""
    r = evaluate("x", GOLD, {"N1": pred("N1", None)}, with_routing=True)
    assert r.routing is not None
    assert r.routing.notes_reviewed == 1
    assert r.routing.high_escaped == 0  # the fall is caught by the rules


def test_bootstrap_is_seeded_and_brackets_the_estimate() -> None:
    gold = [{C.FALLS}, {C.MEDICATION}, set(), {C.FALLS, C.MOOD_BEHAVIOUR}] * 5
    pred_sets = [{C.FALLS}, set(), {C.SKIN_INTEGRITY}, {C.FALLS}] * 5
    a = bootstrap_ci(gold, pred_sets, n_boot=200, seed=1)
    assert a == bootstrap_ci(gold, pred_sets, n_boot=200, seed=1)
    assert a["recall"][0] <= 0.5 <= a["recall"][1]  # point estimate: 2/4 per block
    perfect = bootstrap_ci(gold, gold, n_boot=50)
    assert perfect["f1"] == (1.0, 1.0)


def test_latency_percentiles() -> None:
    gold = [note(f"N{i}", []) for i in range(1, 21)]
    preds = {f"N{i}": pred(f"N{i}", [], latency_ms=float(i * 100)) for i in range(1, 21)}
    r = evaluate("x", gold, preds, n_boot=10)
    assert r.latency(0.5) == pytest.approx(1050.0)
    assert r.latency(0.95) == pytest.approx(1905.0)


def _two_systems():
    gold = [note(f"N{i}", [(C.FALLS, S.HIGH, FALL)]) for i in range(1, 11)]
    good = {f"N{i}": pred(f"N{i}", [(C.FALLS, S.HIGH, FALL)]) for i in range(1, 11)}
    half = {
        f"N{i}": pred(f"N{i}", [(C.FALLS, S.HIGH, FALL)] if i % 2 else []) for i in range(1, 11)
    }
    return evaluate("good", gold, good, n_boot=10), evaluate("half", gold, half, n_boot=10)


def test_paired_bootstrap_detects_a_consistent_difference() -> None:
    good, half = _two_systems()
    recall, _ = paired_bootstrap(good, half, n_boot=500)
    assert recall.diff == pytest.approx(0.5)
    # Not exactly 0: a resample can draw only the odd notes, where both systems succeed
    # (probability ~0.5**10 per round).
    assert recall.low > 0 and recall.p_not_better < 0.01
    same, _ = paired_bootstrap(good, good, n_boot=100)
    assert (same.diff, same.p_not_better) == (0.0, 1.0)  # ties count as "not better"


def test_paired_bootstrap_rejects_different_note_sets() -> None:
    good, _ = _two_systems()
    other = evaluate("x", GOLD, {"N1": pred("N1", [])}, n_boot=10)
    with pytest.raises(ValueError, match="different notes"):
        paired_bootstrap(good, other)


def test_union_recall_combines_systems() -> None:
    gold = [note("N1", [(C.FALLS, S.HIGH, FALL), (C.MISSED_LATE_VISIT, S.MEDIUM, LATE)])]
    a = evaluate("a", gold, {"N1": pred("N1", [(C.FALLS, S.HIGH, FALL)])}, n_boot=10)
    b = evaluate("b", gold, {"N1": pred("N1", [(C.MISSED_LATE_VISIT, S.LOW, LATE)])}, n_boot=10)
    assert union_recall(a, b) == 1.0
