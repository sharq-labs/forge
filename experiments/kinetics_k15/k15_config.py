"""Frozen K1.5 experiment configuration.

The scientific predictions live in the preregistration commit referenced below.
This module merely turns those declarations into executable objects; it does not
retune any K1 threshold after seeing K1.5 outcomes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from experiments.kinetics_k1.k1_config import REGIMES

from . import K15_VERSION, PREREG_COMMIT, PREREG_PATH

EXPERIMENT_ID = "K1.5"
EXPERIMENT_NAME = "kinetics_inference_admissibility_boundary"


def _k1_regime(regime_id: str):
    for spec in REGIMES:
        if spec.regime_id == regime_id:
            return spec
    raise RuntimeError(f"frozen K1 regime {regime_id!r} is unavailable")


#: Confirmatory point frozen in the preregistration: exactly one physical
#: change from K1 R1, coolant 290 K -> 295 K.  No threshold changes.
HOLDOUT = replace(
    _k1_regime("R1"),
    regime_id="H1",
    name="K1.5 unseen benign cooled holdout",
    category="k15_confirmatory_holdout",
    rationale=(
        "Confirmatory inference-admission point not used to choose the K1 "
        "verification thresholds. It is exactly frozen R1 except coolant "
        "temperature is 295 K rather than 290 K."
    ),
    coolant_temperature_k=295.0,
    measure_stiffness=False,
    stiffness_ratio_band=None,
    prediction_note=(
        "preregistered prediction: source solve remains usable and the frozen "
        "K1 tolerance sequence establishes numerical convergence"
    ),
)

#: Negative control: K1 established a usable single solve but no verification
#: level for the oscillatory regime.
USABLE_BUT_SEQUENCE_INVALID = _k1_regime("R7")

#: Negative control: integration can complete but domain admissibility fails.
UNUSABLE_ENVELOPE_EXIT = _k1_regime("R8")

ACCEPTANCE_CRITERIA = (
    "A1 H1 is admitted without changing any K1 verification threshold",
    "A2 H1 admitted observables remain Quantity values with CSTR domain units and source provenance",
    "A3 H1 admission records NUMERICALLY_CONVERGED from the sequence-level report",
    "A4 R7 is rejected even though its ordinary source ScientificResult is usable",
    "A5 R8 is rejected because its ordinary source ScientificResult is unusable",
    "A6 shared guard rejects NumPy arrays, float mappings and a bare ScientificResult",
    "A7 a numerical prediction without NUMERICALLY_CONVERGED sequence evidence is rejected",
    "A8 admission is bound to the source reactor physics fingerprint",
    "A9 no universal Core result/validation contract and no frozen K1 artifact is modified",
    "A10 existing tests plus the new K1.5 tests pass",
)

FALSIFICATION_CRITERIA = (
    "F1 do not retune K1 thresholds if H1 fails",
    "F2 admitting R7 from is_usable alone makes the boundary unsound",
    "F3 admitting R8 after domain validation failure makes the boundary unsound",
    "F4 accepting a bare array/mapping/ScientificResult means the shared boundary is not enforced",
    "F5 allowing verification evidence to bind to different reactor physics makes the adapter unsound",
    "F6 changing frozen K1 artifacts or widening universal Core contracts is architecture creep",
)


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "version": K15_VERSION,
        "preregistration": {
            "path": PREREG_PATH,
            "commit": PREREG_COMMIT,
        },
        "holdout": HOLDOUT.to_dict(),
        "negative_controls": {
            "usable_but_sequence_invalid": USABLE_BUT_SEQUENCE_INVALID.regime_id,
            "unusable_envelope_exit": UNUSABLE_ENVELOPE_EXIT.regime_id,
        },
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "falsification_criteria": list(FALSIFICATION_CRITERIA),
        "threshold_policy": (
            "all CSTR verification thresholds are imported unchanged from the "
            "existing domain gate; K1.5 defines no replacement threshold"
        ),
    }


def config_digest() -> str:
    canonical = json.dumps(
        config_payload(), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
