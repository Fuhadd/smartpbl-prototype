"""Named continuity settings, as the coordinator sees them (Schedule.dc.html segmented
control: Travel / Balanced / Continuity). The weight is the travel minutes the solver will
spend to give a visit to a familiar carer (Step 2.4)."""

from enum import StrEnum


class Preset(StrEnum):
    TRAVEL = "travel"
    BALANCED = "balanced"
    CONTINUITY = "continuity"
    CUSTOM = "custom"  # a weight set through the API that matches no named preset


PRESET_WEIGHTS: dict[Preset, int] = {Preset.TRAVEL: 0, Preset.BALANCED: 15, Preset.CONTINUITY: 30}


def preset_for(continuity_weight_min: int) -> Preset:
    return next((p for p, w in PRESET_WEIGHTS.items() if w == continuity_weight_min), Preset.CUSTOM)
