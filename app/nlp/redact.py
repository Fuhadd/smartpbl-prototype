"""PII redaction for care notes, run before any text reaches an LLM.

Presidio + spaCy NER (en_core_web_lg) plus custom UK pattern recognisers.
Design rules:
  - Recall over precision: a leaked identifier costs more than an over-masked word.
  - Allowlisted entity types only: Presidio's DATE_TIME and US-specific recognisers
    are excluded, because times ("9:40 for the 8:30 call") are clinical evidence.
  - Output is a `RedactedText`. Downstream LLM code accepts only this type.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

SPACY_MODEL = "en_core_web_lg"
SCORE_THRESHOLD = 0.35

ENTITIES: tuple[str, ...] = (
    "PERSON",
    "LOCATION",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "UK_NHS",
    "UK_POSTCODE",
    "UK_STREET_ADDRESS",
)

_STREET_TYPES = (
    "street|st|road|rd|avenue|ave|lane|ln|close|drive|way|crescent|grove|place|court|"
    "gardens|terrace|walk|row|hill"
)


class KinshipNameRecognizer(EntityRecognizer):
    """Capitalised name directly after a relationship word: 'daughter Delta Fakename'.

    Catches names that are also common words, which NER misses ('Hope', 'Delta').
    The name group is case-sensitive on purpose: '(?i)' would mask 'her nephew *takes her*
    bank card' and destroy safeguarding evidence. Only the name is masked, not the relation.
    """

    _RELATIONS = (
        "daughter|son|husband|wife|partner|brother|sister|niece|nephew|grandson|"
        "granddaughter|neighbour|friend|carer|cousin|aunt|uncle"
    )
    _PATTERN = re.compile(rf"\b(?i:{_RELATIONS})(?:'s)?\s+([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?)")
    SCORE = 0.7

    def __init__(self) -> None:
        super().__init__(supported_entities=["PERSON"], name="KinshipNameRecognizer")

    def load(self) -> None:
        """No model to load."""

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        return [
            RecognizerResult("PERSON", m.start(1), m.end(1), self.SCORE)
            for m in self._PATTERN.finditer(text)
        ]


def _uk_recognizers() -> list[EntityRecognizer]:
    return [
        PatternRecognizer(
            supported_entity="UK_POSTCODE",
            name="UkPostcodeRecognizer",
            # Outward code (A9, A99, A9A, AA9, AA99, AA9A) + inward code (9AA).
            patterns=[Pattern("uk_postcode", r"(?i)\b[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}\b", 0.6)],
            context=["postcode", "address"],
        ),
        PatternRecognizer(
            supported_entity="UK_NHS",
            name="UkNhsLikeRecognizer",
            # Deliberately no checksum: a mistyped NHS number is still an identifier.
            patterns=[Pattern("nhs_like", r"\b\d{3}[\s-]?\d{3}[\s-]?\d{4}\b", 0.5)],
            context=["nhs", "number", "no"],
        ),
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            name="UkPhoneRecognizer",
            # +44 or leading 0, then 9-10 digits in common UK groupings.
            patterns=[
                Pattern("uk_phone", r"(?:\+44\s?|\b0)\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}\b", 0.6)
            ],
            context=["phone", "rang", "call", "tel", "mobile", "number"],
        ),
        PatternRecognizer(
            supported_entity="UK_STREET_ADDRESS",
            name="UkStreetAddressRecognizer",
            patterns=[
                Pattern(
                    "house_and_street",
                    rf"(?i)\b\d{{1,4}}[a-z]?,?\s+(?:[a-z][a-z'-]+\s+){{1,3}}(?:{_STREET_TYPES})\b",
                    0.6,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="PERSON",
            name="TitledNameRecognizer",
            # Catches lowercase notes ("ms dummyford") where statistical NER fails.
            patterns=[
                Pattern("title_name", r"(?i)\b(?:mr|mrs|ms|miss|dr)\.?\s+[a-z][a-z'-]+", 0.6)
            ],
        ),
        KinshipNameRecognizer(),
    ]


@lru_cache
def get_analyzer() -> AnalyzerEngine:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
        }
    )
    analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    for recognizer in _uk_recognizers():
        analyzer.registry.add_recognizer(recognizer)
    return analyzer


@lru_cache
def _anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


@dataclass(frozen=True)
class RedactedSpan:
    """Where something was masked. Holds no original values, only type, position and score."""

    entity_type: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class RedactedText:
    text: str
    spans: tuple[RedactedSpan, ...]


def detect(text: str, known_names: tuple[str, ...] = ()) -> list[RecognizerResult]:
    """`known_names`: names already held for this client (care record, next of kin).

    A per-request deny-list catches what generic recognisers can't, e.g. lowercase names
    that are also common words. In production these come from the client registry.
    """
    ad_hoc = (
        [PatternRecognizer(supported_entity="PERSON", deny_list=list(known_names))]
        if known_names
        else None
    )
    return get_analyzer().analyze(
        text=text,
        language="en",
        entities=list(ENTITIES),
        score_threshold=SCORE_THRESHOLD,
        ad_hoc_recognizers=ad_hoc,
    )


def redact(text: str, known_names: tuple[str, ...] = ()) -> RedactedText:
    """Replace detected identifiers with typed placeholders, e.g. '<PERSON>'."""
    results = detect(text, known_names)
    anonymized = _anonymizer().anonymize(text=text, analyzer_results=results)
    spans = tuple(
        RedactedSpan(r.entity_type, r.start, r.end, round(r.score, 2))
        for r in sorted(results, key=lambda r: r.start)
    )
    return RedactedText(text=anonymized.text, spans=spans)
