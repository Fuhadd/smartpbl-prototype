import pytest

from app.nlp.metrics import PRF, category_report
from app.nlp.schemas import RiskCategory

C = RiskCategory


def test_prf_values() -> None:
    m = PRF(tp=3, fp=1, fn=2)
    assert m.precision == pytest.approx(0.75)
    assert m.recall == pytest.approx(0.6)
    assert m.f1 == pytest.approx(2 * 0.75 * 0.6 / 1.35)


def test_prf_zero_division_is_zero() -> None:
    assert PRF(0, 0, 0).f1 == 0.0


def test_category_report_micro_vs_macro() -> None:
    gold = [{C.FALLS}, {C.FALLS}, {C.FALLS}, {C.SAFEGUARDING}]
    pred = [{C.FALLS}, {C.FALLS}, {C.FALLS}, set()]
    report = category_report(gold, pred)
    assert report.per_category[C.FALLS] == PRF(3, 0, 0)
    assert report.per_category[C.SAFEGUARDING] == PRF(0, 0, 1)
    assert report.micro == PRF(3, 0, 1)
    assert report.micro.recall == pytest.approx(0.75)  # pooled: frequent category dominates
    # Macro averages all 7 categories equally; absent categories (no gold, no pred) score 0.
    assert report.macro_f1 == pytest.approx(1 / 7)


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        category_report([{C.FALLS}], [])
