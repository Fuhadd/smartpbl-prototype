from app.nlp.route import ReviewReason, decide
from app.nlp.schemas import Extraction, MedicationStatus, RiskCategory, RiskFlag, Severity

C, S = RiskCategory, Severity
NOTE = "Tea call. Heels look red, cream applied. Found on the floor by the bed. Arrived late."


def flag(category: RiskCategory, severity: Severity, evidence: str, conf: float = 0.9) -> RiskFlag:
    return RiskFlag(category=category, evidence=evidence, severity=severity, confidence=conf)


def extraction(*flags: RiskFlag) -> Extraction:
    return Extraction(
        risk_flags=list(flags),
        medication_status=MedicationStatus.NOT_MENTIONED,
        follow_up_required=any(f.severity is not S.LOW for f in flags),
        summary="Synthetic test note.",
    )


def reasons(decision, category: RiskCategory) -> set[ReviewReason]:
    return set(next(f for f in decision.flags if f.flag.category is category).reasons)


def test_grounded_medium_flag_is_auto_accepted() -> None:
    d = decide(extraction(flag(C.SKIN_INTEGRITY, S.MEDIUM, "Heels look red")), NOTE)
    assert not d.review_required
    assert [f.category for f in d.auto_accepted] == [C.SKIN_INTEGRITY]


def test_high_severity_goes_to_review() -> None:
    d = decide(extraction(flag(C.FALLS, S.HIGH, "Found on the floor by the bed")), NOTE)
    assert d.review_required
    assert reasons(d, C.FALLS) == {ReviewReason.HIGH_SEVERITY}
    assert d.auto_accepted == ()


def test_safeguarding_always_reviewed_even_at_medium() -> None:
    d = decide(extraction(flag(C.SAFEGUARDING, S.MEDIUM, "Heels look red")), NOTE)
    assert ReviewReason.SAFEGUARDING in reasons(d, C.SAFEGUARDING)


def test_ungrounded_flag_rejected_from_auto_accept_but_kept_for_review() -> None:
    d = decide(extraction(flag(C.NUTRITION_HYDRATION, S.LOW, "refused all food today")), NOTE)
    assert reasons(d, C.NUTRITION_HYDRATION) == {ReviewReason.UNGROUNDED}
    assert d.auto_accepted == ()
    assert len(d.flags) == 1  # not silently dropped


def test_fuzzy_evidence_goes_to_review() -> None:
    d = decide(extraction(flag(C.SKIN_INTEGRITY, S.MEDIUM, "Heels looks red, cream aplied")), NOTE)
    assert reasons(d, C.SKIN_INTEGRITY) == {ReviewReason.FUZZY_EVIDENCE}


def test_low_confidence_goes_to_review() -> None:
    d = decide(extraction(flag(C.SKIN_INTEGRITY, S.LOW, "Heels look red", conf=0.4)), NOTE)
    assert reasons(d, C.SKIN_INTEGRITY) == {ReviewReason.LOW_CONFIDENCE}


def test_failed_extraction_routes_note_and_keeps_baseline_flags() -> None:
    baseline = extraction(flag(C.MISSED_LATE_VISIT, S.MEDIUM, "Arrived late."))
    d = decide(None, NOTE, baseline)
    assert d.review_required
    assert d.note_reasons == (ReviewReason.EXTRACTION_FAILED,)
    assert [f.source for f in d.flags] == ["baseline"]


def test_baseline_only_category_is_surfaced_without_duplicates() -> None:
    llm = extraction(flag(C.SKIN_INTEGRITY, S.MEDIUM, "Heels look red"))
    baseline = extraction(
        flag(C.SKIN_INTEGRITY, S.MEDIUM, "Heels look red, cream applied."),  # LLM has it too
        flag(C.MISSED_LATE_VISIT, S.MEDIUM, "Arrived late."),  # LLM missed it
    )
    d = decide(llm, NOTE, baseline)
    assert [(f.source, f.flag.category) for f in d.flags] == [
        ("llm", C.SKIN_INTEGRITY),
        ("baseline", C.MISSED_LATE_VISIT),
    ]
    assert reasons(d, C.MISSED_LATE_VISIT) == {ReviewReason.BASELINE_ONLY}
    assert [f.category for f in d.auto_accepted] == [C.SKIN_INTEGRITY]
