"""INF-06 and INF-07: the split's duplicate guard and the held-out/posterior identity.

INF-06  ``observation_content_digest`` put the unit string in the digest and
        converted only the sigma, over bit-exact values: the same reading written
        in milliohm, or nudged by one ulp, was different "content" and crossed the
        split unseen. ``ObservationSplit`` also accepted one ``condition_id`` in
        both halves, the within-condition split ``partition`` exists to rule out.
INF-07  ``assess_predictive_observation`` accepted a ``heldout_dataset_id`` equal to
        the posterior's own dataset id -- a score on the fitting data, recorded as
        held-out evidence.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.adequacy import ModelAdequacyError, assess_predictive_observation
from engcore.inference import AdmittedForwardTable, PosteriorGrid
from engcore.inference.grid import GaussianObservation, ObservationSet
from engcore.inference.split import DataLeakageError, ObservationSplit, observation_content_digest
from engcore.scientific import ModelReference, Quantity, TwinReference
from engcore.uq import PredictiveObservableSpec

TWIN = TwinReference("audit-inference-split", "1")
SIG = Quantity(0.002, "ohm")


def _obs(condition, value, unit="ohm", sigma=SIG, observable="R"):
    return GaussianObservation(condition, observable, Quantity(value, unit), sigma, "s")


def _split(cal, held):
    return ObservationSplit(ObservationSet(tuple(cal), "cal"), ObservationSet(tuple(held), "held"), TWIN, "src")


# ---- INF-06 -----------------------------------------------------------------

def test_the_same_reading_in_another_unit_is_the_same_content():
    a = _obs("c1", 1.2345)
    b = _obs("c9", 1234.5, unit="milliohm")
    assert observation_content_digest(a) == observation_content_digest(b)
    with pytest.raises(DataLeakageError, match="under different labels"):
        _split([a], [b])


def test_a_one_ulp_nudge_is_still_the_same_content():
    a = _obs("c1", 1.2345)
    b = _obs("c9", float(np.nextafter(1.2345, 2.0)))
    assert observation_content_digest(a) == observation_content_digest(b)
    with pytest.raises(DataLeakageError, match="under different labels"):
        _split([a], [b])


def test_a_genuinely_different_reading_is_different_content():
    assert observation_content_digest(_obs("c1", 1.2345)) != observation_content_digest(_obs("c9", 1.2346))


def test_one_condition_in_both_halves_is_refused():
    voltage = GaussianObservation("c1", "voltage", Quantity(1.0, "volt"), Quantity(0.01, "volt"), "s")
    current = GaussianObservation("c1", "current", Quantity(2.0, "ampere"), Quantity(0.01, "ampere"), "s")
    with pytest.raises(DataLeakageError, match="condition"):
        _split([voltage], [current])


def test_declared_exact_replicates_do_not_permit_a_shared_condition():
    voltage = GaussianObservation("c1", "voltage", Quantity(1.0, "volt"), Quantity(0.01, "volt"), "s")
    current = GaussianObservation("c1", "current", Quantity(2.0, "ampere"), Quantity(0.01, "ampere"), "s")
    with pytest.raises(DataLeakageError, match="condition"):
        ObservationSplit(ObservationSet((voltage,), "cal"), ObservationSet((current,), "held"), TWIN, "src",
                         exact_replicates_allowed=True)


# ---- INF-07 -----------------------------------------------------------------

def _posterior(dataset_id):
    w = np.asarray([0.25, 0.375, 0.375])
    return PosteriorGrid(("p",), np.asarray([[0.0], [1.0], [2.0]]), w, np.log(w), np.ones(3, dtype=bool), dataset_id)


def _table():
    return AdmittedForwardTable(("p",), ("H:y",), np.asarray([[0.0], [1.0], [2.0]]), np.asarray([[10.0], [14.0], [14.0]]),
                                np.ones(3, dtype=bool), (("a",), ("b",), ("c",)), ("", "", ""))


def _assess(posterior_id, heldout_id):
    return assess_predictive_observation(
        _posterior(posterior_id), _table(), PredictiveObservableSpec("H:y", "kelvin", Quantity(2.0, "kelvin")),
        Quantity(12.0, "kelvin"), twin=TWIN, model=ModelReference("m", "1"), source_ref="audit",
        heldout_dataset_id=heldout_id,
    )


def test_scoring_against_the_posteriors_own_dataset_is_refused():
    with pytest.raises(ModelAdequacyError, match="fitting data"):
        _assess("fit", "fit")
    with pytest.raises(ModelAdequacyError, match="fitting data"):
        _assess("fit", "  fit ")


def test_scoring_against_a_distinct_held_out_dataset_is_accepted():
    assert _assess("fit", "held").evidence.heldout_dataset_id == "held"
