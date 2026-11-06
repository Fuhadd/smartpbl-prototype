"""Phrase library for synthetic care notes.

Each risk phrase carries its gold label. "indirect" phrases describe a risk without the
obvious keyword (hard cases). Severity rule used throughout:
  high   = harm has occurred or is likely now (injury, safeguarding, no care delivered)
  medium = needs same-day follow-up
  low    = worth recording, no action today
All names and identifiers are deliberately and obviously fictional.
"""

from dataclasses import dataclass

from app.nlp.schemas import MedicationStatus as M
from app.nlp.schemas import RiskCategory as C
from app.nlp.schemas import Severity as S


@dataclass(frozen=True)
class RiskPhrase:
    text: str
    category: C
    severity: S
    indirect: bool = False
    med_status: M | None = None  # only for medication phrases


RISK_PHRASES: list[RiskPhrase] = [
    # Falls
    RiskPhrase(
        "Client had a fall in the kitchen this morning, says she tripped on the rug.",
        C.FALLS,
        S.HIGH,
    ),
    RiskPhrase(
        "Found on the floor by the bed when I arrived, helped up, no obvious injury.",
        C.FALLS,
        S.HIGH,
    ),
    RiskPhrase("Reports a fall overnight, bruise noted on left hip.", C.FALLS, S.HIGH),
    RiskPhrase(
        "Unsteady on her feet today, nearly fell when transferring to the commode.",
        C.FALLS,
        S.MEDIUM,
    ),
    RiskPhrase(
        "Walking frame was left out of reach and she wobbled getting to the toilet.", C.FALLS, S.LOW
    ),
    RiskPhrase(
        "Sat on the bathroom floor when I came in, couldn't get herself back up.",
        C.FALLS,
        S.HIGH,
        True,
    ),
    RiskPhrase(
        "Mentioned she went down in the hallway yesterday but didn't press her pendant.",
        C.FALLS,
        S.HIGH,
        True,
    ),
    RiskPhrase(
        "Legs gave way as we stood her up, lowered her safely into the chair.",
        C.FALLS,
        S.MEDIUM,
        True,
    ),
    # Medication
    RiskPhrase(
        "Refused evening medication, said the tablets make her feel sick.",
        C.MEDICATION,
        S.MEDIUM,
        med_status=M.REFUSED,
    ),
    RiskPhrase(
        "Declined all morning medication despite encouragement.",
        C.MEDICATION,
        S.MEDIUM,
        med_status=M.REFUSED,
    ),
    RiskPhrase(
        "Lunchtime tablets still in the blister pack from yesterday, dose appears missed.",
        C.MEDICATION,
        S.MEDIUM,
        med_status=M.MISSED,
    ),
    RiskPhrase(
        "Medication not given as the blister pack has not been delivered by the pharmacy.",
        C.MEDICATION,
        S.HIGH,
        med_status=M.MISSED,
    ),
    RiskPhrase(
        "Only took two of her four tablets and spat the rest out.",
        C.MEDICATION,
        S.LOW,
        med_status=M.PARTIAL,
    ),
    RiskPhrase(
        "Took her paracetamol but refused the laxative.", C.MEDICATION, S.LOW, med_status=M.PARTIAL
    ),
    RiskPhrase(
        "Found tablets on the carpet under the armchair, unclear when they were dropped.",
        C.MEDICATION,
        S.MEDIUM,
        True,
        M.MISSED,
    ),
    RiskPhrase(
        "Pills were hidden in a tissue in her cardigan pocket.",
        C.MEDICATION,
        S.MEDIUM,
        True,
        M.REFUSED,
    ),
    # Nutrition / hydration
    RiskPhrase("Poor appetite, only ate a few spoonfuls of soup.", C.NUTRITION_HYDRATION, S.MEDIUM),
    RiskPhrase(
        "Drank very little today, approximately 300ml, urine dark.", C.NUTRITION_HYDRATION, S.HIGH
    ),
    RiskPhrase(
        "Breakfast from the earlier visit untouched in the fridge.", C.NUTRITION_HYDRATION, S.MEDIUM
    ),
    RiskPhrase("Has not eaten anything since yesterday lunchtime.", C.NUTRITION_HYDRATION, S.HIGH),
    RiskPhrase("She is no longer finishing her meals.", C.NUTRITION_HYDRATION, S.MEDIUM),
    RiskPhrase(
        "Fridge almost empty and the milk is out of date.", C.NUTRITION_HYDRATION, S.LOW, True
    ),
    RiskPhrase(
        "Lips dry and cracked, says she isn't thirsty.", C.NUTRITION_HYDRATION, S.MEDIUM, True
    ),
    RiskPhrase(
        "Clothes looking looser and her daughter thinks she has lost weight.",
        C.NUTRITION_HYDRATION,
        S.MEDIUM,
        True,
    ),
    # Skin integrity
    RiskPhrase("Red area noted on sacrum, did not blanch when pressed.", C.SKIN_INTEGRITY, S.HIGH),
    RiskPhrase(
        "Small skin tear on right forearm, cleaned and dressed.", C.SKIN_INTEGRITY, S.MEDIUM
    ),
    RiskPhrase(
        "Heels look red, applied barrier cream and repositioned.", C.SKIN_INTEGRITY, S.MEDIUM
    ),
    RiskPhrase(
        "Pressure sore on left heel appears worse, dressing soaked.", C.SKIN_INTEGRITY, S.HIGH
    ),
    RiskPhrase(
        "Bottom looks sore and she winces when sitting down.", C.SKIN_INTEGRITY, S.MEDIUM, True
    ),
    RiskPhrase(
        "Pad was soaked through and the skin underneath very red.", C.SKIN_INTEGRITY, S.MEDIUM, True
    ),
    # Mood / behaviour change
    RiskPhrase(
        "Very low in mood today, tearful and said she can't be bothered anymore.",
        C.MOOD_BEHAVIOUR,
        S.HIGH,
    ),
    RiskPhrase(
        "More confused than usual, didn't recognise me and asked for her late husband.",
        C.MOOD_BEHAVIOUR,
        S.MEDIUM,
    ),
    RiskPhrase(
        "Agitated and shouting during personal care, which is unusual for her.",
        C.MOOD_BEHAVIOUR,
        S.MEDIUM,
    ),
    RiskPhrase(
        "Seemed a bit quieter than normal but chatted once tea was made.", C.MOOD_BEHAVIOUR, S.LOW
    ),
    RiskPhrase(
        "Curtains still closed at 2pm and she hasn't got dressed for 3 days.",
        C.MOOD_BEHAVIOUR,
        S.MEDIUM,
        True,
    ),
    RiskPhrase(
        "Kept packing a bag saying she needs to go home, but she is at home.",
        C.MOOD_BEHAVIOUR,
        S.MEDIUM,
        True,
    ),
    # Safeguarding concern
    RiskPhrase(
        "Client said her nephew takes her bank card and she doesn't get it back.",
        C.SAFEGUARDING,
        S.HIGH,
    ),
    RiskPhrase(
        "Unexplained bruising on both upper arms, client would not say how it happened.",
        C.SAFEGUARDING,
        S.HIGH,
    ),
    RiskPhrase("Neighbour has been coming in and asking client for money.", C.SAFEGUARDING, S.HIGH),
    RiskPhrase(
        "Client appeared frightened when her son arrived and went quiet.", C.SAFEGUARDING, S.MEDIUM
    ),
    RiskPhrase(
        "Pension money missing from the tin again, she thinks she must have spent it.",
        C.SAFEGUARDING,
        S.HIGH,
        True,
    ),
    RiskPhrase(
        "Front door wide open and a man I didn't know was in the lounge when I arrived.",
        C.SAFEGUARDING,
        S.HIGH,
        True,
    ),
    # Missed / late visit
    RiskPhrase(
        "Visit 50 minutes late due to previous call overrunning.", C.MISSED_LATE_VISIT, S.MEDIUM
    ),
    RiskPhrase(
        "Arrived late, client had been waiting for lunch since 12.", C.MISSED_LATE_VISIT, S.MEDIUM
    ),
    RiskPhrase(
        "Morning call was missed, no carer attended, client still in bed at 11.",
        C.MISSED_LATE_VISIT,
        S.HIGH,
    ),
    RiskPhrase(
        "Previous visit appears not to have happened, no entry in the log.",
        C.MISSED_LATE_VISIT,
        S.HIGH,
    ),
    RiskPhrase(
        "Got here at 9:40 for the 8:30 call, traffic on the ring road.",
        C.MISSED_LATE_VISIT,
        S.MEDIUM,
        True,
    ),
    RiskPhrase(
        "Teatime call cut to 10 minutes as I was running behind.", C.MISSED_LATE_VISIT, S.LOW, True
    ),
]

# Negation distractors: mention a risk keyword without the risk being present.
NEGATIONS: dict[C, list[str]] = {
    C.FALLS: [
        "No falls reported since last visit.",
        "Mobilised well with frame, no trips or falls.",
        "Denies any falls.",
    ],
    C.MEDICATION: ["All medication taken, no refusals.", "Meds given as per MAR, no missed doses."],
    C.NUTRITION_HYDRATION: [
        "Ate a full breakfast, no concerns with appetite.",
        "Good fluid intake, no signs of dehydration.",
    ],
    C.SKIN_INTEGRITY: ["Skin checked and intact, no redness or sores.", "No pressure areas noted."],
    C.MOOD_BEHAVIOUR: [
        "In good spirits, no signs of low mood.",
        "Settled and calm, no confusion today.",
    ],
    C.SAFEGUARDING: [
        "No safeguarding concerns.",
        "Finances managed by daughter, no concerns raised.",
    ],
    C.MISSED_LATE_VISIT: ["Visit on time, no delays.", "Arrived on time for the call."],
}

MED_TAKEN = [
    "Meds given as per MAR.",
    "Morning tablets taken with water.",
    "Prompted with medication, taken.",
]

FILLERS = [
    "Assisted with washing and dressing.",
    "Made a cup of tea and a sandwich.",
    "Emptied commode and tidied the kitchen.",
    "Chatted about the football.",
    "Helped into bed, call bell within reach.",
    "Put a wash on and hung it out.",
    "Watched TV together while she had her tea.",
    "Daughter visiting later this afternoon.",
    "Put the bins out as requested.",
]

OPENINGS_PLAIN = ["AM call.", "Lunch visit.", "Tea call.", "Bed call.", "Visit completed."]
CLOSINGS = ["Left client comfortable.", "All doors locked on leaving.", "Key safe locked."]

# Obviously synthetic identifiers.
TITLES = ["Mrs", "Ms", "Miss"]
SURNAMES = ["Sampleton", "Testperson", "Fakename", "Placeholder", "Dummyford", "Exampleby"]
FIRST_NAMES = ["Alpha", "Bravo", "Delta", "Echo"]  # family members
STREETS = ["Example Street", "Sample Road", "Fictional Avenue", "Testing Lane"]
OPENINGS_PII = [
    "Visited {title} {surname} at {house} {street}, {postcode}.",
    "Call to {title} {surname} (NHS no {nhs}).",
    "{title} {surname}'s daughter {first} rang on {phone} before the visit.",
]

ABBREVIATIONS: dict[str, str] = {
    r"\bmedication\b": "meds",
    r"\bapproximately\b": "approx",
    r"\bminutes\b": "mins",
    r"\bbreakfast\b": "bfast",
    r"\bwith\b": "w/",
    r"\band\b": "&",
    r"\bclient\b": "cl",
}
