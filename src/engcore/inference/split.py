"""Calibration data and held-out data as two distinct pieces of evidence.

The claim a held-out score makes
--------------------------------
"The model predicts data it was not fitted to." That sentence is worth exactly
as much as the guarantee behind the words *was not fitted to*, and before this
module there was no guarantee at all.

``ObservationSet`` already carries a ``dataset_id`` and already refuses
duplicate observation keys *within* one set. What nothing checked is the
relationship *between* two sets. ``ObservationSet.subset`` will happily produce
two sets that share observations, give them different ``dataset_id`` strings,
and every consumer downstream -- the posterior, the predictive UQ, the
adequacy score -- will treat them as independent evidence because their labels
differ.

Labels are not evidence. So a split is a type, it is built once from one
source, and it is the only supported way to obtain a calibration set and a
held-out set that claim to be disjoint.

What counts as leakage
----------------------
Two separate failures, and the second is the one a label-based check misses:

1. **The same observation key in both sides.** A condition measured during
   calibration and scored as held-out. Caught by key.

2. **The same observation under another label.** The same measured value, with
   the same declared sigma, for the same observable, relabelled with a
   different ``condition_id`` and put in the other side. The keys differ, so
   nothing based on keys objects, and the model is scored on a number it was
   fitted to.

The second is caught by a content digest over what the observation *is* --
observable, value and sigma, in canonical units -- and deliberately not over
``source_ref``, which names who produced a row rather than what it says.

Two genuinely distinct measurements of a continuous quantity producing
bit-identical value AND bit-identical sigma is not a coincidence that happens;
it is a copy. A study that really does have exact replicates at different
conditions can say so by declaring them through :func:`allow_exact_replicates`,
which makes the decision visible instead of silent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..scientific.serialization import require_schema, schema_string
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity, base_unit
from .grid import GaussianObservation, InferenceProblemError, ObservationSet

OBSERVATION_SPLIT_SCHEMA = schema_string("calibration_observation_split")


class DataLeakageError(InferenceProblemError):
    """Calibration and held-out evidence that are not actually distinct.

    A subclass of :class:`InferenceProblemError` so that existing handlers
    still catch it, and its own type so that a leakage refusal can be
    distinguished from an ill-posed problem -- they call for different
    responses, and Phase 19 asks for the distinction to be explicit.
    """


def _canonical_number(value: float) -> str:
    """Twelve significant digits, with -0 folded into 0, as the digest's text."""
    text = f"{float(value) + 0.0:.12g}"
    return "0" if text in ("-0", "0") else text


def observation_content_digest(observation: GaussianObservation) -> str:
    """What the observation SAYS, independent of what it is called.

    Over the observable name, the value and the sigma -- the sigma converted
    into the value's own unit so that ``0.1 ohm`` and ``100 milliohm`` are one
    content, not two.

    Deliberately NOT over ``condition_id``: the whole point is to catch the
    same reading relabelled. Deliberately NOT over ``source_ref``: that names
    who produced a row, and the same reading imported twice from two files is
    still the same reading.
    """
    if not isinstance(observation, GaussianObservation):
        raise InferenceProblemError(
            f"a content digest is taken of a GaussianObservation, got "
            f"{type(observation).__name__}"
        )
    # INF-06: canonical content, not a spelling of it. The value used to be
    # digested in whatever unit it was written in, beside that unit string, and
    # bit-exact: 1.2345 ohm and 1234.5 milliohm -- or 1.2345 nudged by one ulp --
    # were different "content" and crossed the split unseen. Value and sigma are
    # now expressed in the dimension's base unit and rounded to twelve significant
    # digits: two distinct measurements of a continuous quantity agreeing to
    # twelve digits in value AND sigma are a copy, exactly as the module says of
    # bit-identical ones. Sigma is converted as a DIFFERENCE, so an offset unit
    # does not add its zero to it.
    unit = base_unit(observation.value.units)
    value = observation.value.magnitude_in(unit)
    sigma_in_value_unit = observation.sigma.magnitude_in(observation.value.units)
    upper = Quantity(observation.value.magnitude + sigma_in_value_unit, observation.value.units)
    sigma = abs(upper.magnitude_in(unit) - value)
    payload = {
        "observable_name": observation.observable_name,
        "unit": unit,
        "value": _canonical_number(value),
        "sigma": _canonical_number(sigma),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ObservationSplit:
    """One body of evidence, partitioned once, into two named halves.

    Built through :meth:`partition` rather than by assembling two sets by hand.
    The constructor still checks everything, because a type whose invariant
    lives only in its factory is a convention -- the same reasoning
    ``AdmittedForwardRow`` records for itself.

    ``twin`` is the system both halves describe. A split whose halves describe
    different twins is not a split; it is two studies, and scoring one against
    the other's posterior is the mistake ``PredictiveEvidenceIdentity`` already
    refuses one layer further down. Refusing it here means the refusal arrives
    before the fit rather than after it.
    """

    calibration: ObservationSet
    held_out: ObservationSet
    twin: TwinReference
    source_dataset_id: str
    exact_replicates_allowed: bool = False

    def __post_init__(self) -> None:
        for label in ("calibration", "held_out"):
            value = getattr(self, label)
            if not isinstance(value, ObservationSet):
                raise InferenceProblemError(
                    f"split {label} must be an ObservationSet, got "
                    f"{type(value).__name__}"
                )
        if not isinstance(self.twin, TwinReference):
            raise InferenceProblemError("a split requires a TwinReference")
        source = str(self.source_dataset_id).strip()
        if not source:
            raise InferenceProblemError("a split requires a source_dataset_id")
        object.__setattr__(self, "source_dataset_id", source)

        if self.calibration.dataset_id == self.held_out.dataset_id:
            raise DataLeakageError(
                f"calibration and held-out sets share the dataset id "
                f"{self.calibration.dataset_id!r}. Two halves of one split are "
                f"two pieces of evidence and must be nameable apart; a "
                f"posterior and a held-out score that cite the same id cannot "
                f"be told from a score computed on the fitting data"
            )

        shared_keys = sorted(set(self.calibration.keys) & set(self.held_out.keys))
        if shared_keys:
            raise DataLeakageError(
                f"{len(shared_keys)} observation(s) appear in both the "
                f"calibration and held-out sets: {shared_keys[:5]!r}"
                f"{'…' if len(shared_keys) > 5 else ''}. A held-out score over "
                f"these is a score on the fitting data"
            )

        # INF-06: one experimental condition belongs to one side. Splitting within
        # a condition -- fitting the voltage and holding out the current of the
        # same run -- leaks through the physics with no key shared, and
        # `partition` documents that split as unavailable; the constructor now
        # makes it so. Not waived by exact_replicates_allowed, which is about
        # repeated values at DIFFERENT conditions.
        shared_conditions = sorted(
            {item.condition_id for item in self.calibration.observations}
            & {item.condition_id for item in self.held_out.observations}
        )
        if shared_conditions:
            raise DataLeakageError(
                f"{len(shared_conditions)} experimental condition(s) appear in both "
                f"the calibration and held-out sets: {shared_conditions[:5]!r}. Every "
                f"observable measured at one condition belongs to the same side; a "
                f"held-out observable from a calibrated run is not unseen data"
            )

        if not self.exact_replicates_allowed:
            by_content: dict[str, list[str]] = {}
            for side, observations in (
                ("calibration", self.calibration.observations),
                ("held_out", self.held_out.observations),
            ):
                for item in observations:
                    by_content.setdefault(observation_content_digest(item), []).append(
                        f"{side}:{item.key}"
                    )
            collisions = {
                digest: where
                for digest, where in by_content.items()
                if len({entry.split(":", 1)[0] for entry in where}) > 1
            }
            if collisions:
                examples = sorted(
                    tuple(sorted(where)) for where in collisions.values()
                )[:3]
                raise DataLeakageError(
                    f"{len(collisions)} observation(s) appear on both sides of "
                    f"the split under different labels: {examples!r}. Same "
                    f"observable, same value, same sigma, different "
                    f"condition_id -- for a continuous quantity that is a copy, "
                    f"not a coincidence. If this study really does carry exact "
                    f"replicates, declare it with allow_exact_replicates() so "
                    f"the decision is visible"
                )

    @property
    def calibration_dataset_id(self) -> str:
        return self.calibration.dataset_id

    @property
    def heldout_dataset_id(self) -> str:
        return self.held_out.dataset_id

    @property
    def digest(self) -> str:
        payload = {
            "source_dataset_id": self.source_dataset_id,
            "twin": self.twin.to_dict(),
            "calibration_dataset_id": self.calibration.dataset_id,
            "heldout_dataset_id": self.held_out.dataset_id,
            "calibration_keys": list(self.calibration.keys),
            "heldout_keys": list(self.held_out.keys),
            "exact_replicates_allowed": self.exact_replicates_allowed,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def require_posterior_was_fitted_here(self, posterior_dataset_id: str) -> None:
        """Refuse a posterior that was not conditioned on the calibration half.

        Phase 17's "posterior built from held-out dataset", and the more
        ordinary case of a posterior from some third dataset entirely. The
        held-out id is named separately in the message because that is the
        failure that silently inflates a score rather than merely invalidating
        it.
        """
        given = str(posterior_dataset_id).strip()
        if given == self.calibration.dataset_id:
            return
        if given == self.held_out.dataset_id:
            raise DataLeakageError(
                f"the posterior was conditioned on {given!r}, which is this "
                f"split's HELD-OUT set. Scoring it against the same data "
                f"reports how well the model fits what it was fitted to, and "
                f"reports it as predictive performance"
            )
        raise DataLeakageError(
            f"the posterior was conditioned on {given!r}, which is neither half "
            f"of this split (calibration {self.calibration.dataset_id!r}, "
            f"held-out {self.held_out.dataset_id!r}). A held-out score is a "
            f"statement about one posterior and one dataset"
        )

    def require_scored_against_held_out(self, heldout_dataset_id: str) -> None:
        """Refuse a held-out result compared against the wrong dataset."""
        given = str(heldout_dataset_id).strip()
        if given != self.held_out.dataset_id:
            raise DataLeakageError(
                f"held-out evidence cites {given!r} but this split's held-out "
                f"set is {self.held_out.dataset_id!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBSERVATION_SPLIT_SCHEMA,
            "source_dataset_id": self.source_dataset_id,
            "twin": self.twin.to_dict(),
            "calibration": self.calibration.to_dict(),
            "held_out": self.held_out.to_dict(),
            "exact_replicates_allowed": self.exact_replicates_allowed,
            "digest": self.digest,
        }

    @classmethod
    def partition(
        cls,
        source: ObservationSet,
        *,
        held_out_condition_ids: Sequence[str],
        twin: TwinReference,
        calibration_dataset_id: str,
        heldout_dataset_id: str,
        exact_replicates_allowed: bool = False,
    ) -> "ObservationSplit":
        """Split one set by condition, so the two halves cannot overlap by construction.

        Partitioning by ``condition_id`` rather than by observation key is
        deliberate: every observable measured at one experimental condition
        belongs to the same side. Splitting *within* a condition -- fitting the
        voltage and holding out the current from the same run -- leaks through
        the physics even when no key is shared, and this signature makes that
        split unavailable rather than merely discouraged.
        """
        if not isinstance(source, ObservationSet):
            raise InferenceProblemError(
                f"a split is partitioned from an ObservationSet, got "
                f"{type(source).__name__}"
            )
        wanted = {str(value).strip() for value in held_out_condition_ids}
        if not wanted:
            raise InferenceProblemError(
                "a split must hold out at least one condition; an empty "
                "held-out set cannot validate anything"
            )
        available = {item.condition_id for item in source.observations}
        unknown = sorted(wanted - available)
        if unknown:
            raise InferenceProblemError(
                f"cannot hold out condition(s) {unknown!r}: not present in "
                f"{source.dataset_id!r}. Available: {sorted(available)!r}"
            )
        if wanted == available:
            raise InferenceProblemError(
                "holding out every condition leaves nothing to calibrate on"
            )
        calibration = ObservationSet(
            observations=tuple(
                item for item in source.observations if item.condition_id not in wanted
            ),
            dataset_id=calibration_dataset_id,
        )
        held_out = ObservationSet(
            observations=tuple(
                item for item in source.observations if item.condition_id in wanted
            ),
            dataset_id=heldout_dataset_id,
        )
        return cls(
            calibration=calibration,
            held_out=held_out,
            twin=twin,
            source_dataset_id=source.dataset_id,
            exact_replicates_allowed=exact_replicates_allowed,
        )


#: How closely a posterior's stored log-likelihood must reproduce the likelihood
#: of a split's calibration half, recomputed from an admitted forward table over
#: the posterior's own points. Both sides are the same float64 arithmetic over
#: the same admitted values, so an honest posterior agrees to roundoff; a
#: posterior conditioned on even one extra observation moves every node by that
#: observation's squared standardized residual.
_LIKELIHOOD_BINDING_RTOL = 1.0e-9
_LIKELIHOOD_BINDING_ATOL = 1.0e-9


def _require_posterior_conditioned_on_calibration(
    split: ObservationSplit,
    posterior: Any,
    calibration_table: Any,
) -> None:
    """Refuse a posterior whose CONTENT is not the calibration half's likelihood (INF-03).

    :meth:`ObservationSplit.require_posterior_was_fitted_here` compares a
    ``dataset_id`` string, and a posterior's ``dataset_id`` is whatever its
    builder was told. An :class:`ObservationSet` of every row -- held-out rows
    included -- labelled with the calibration id passed it, and the model was
    scored on data it had been fitted to.

    So the label check runs first (it names the held-out case precisely) and the
    content check after it: the grid log-likelihood is recomputed from
    ``calibration_table`` -- an admitted forward table over the posterior's own
    points, evaluated at the calibration half's conditions -- and the split's
    calibration observations, and must equal the one the posterior carries.
    ``PosteriorGrid`` already binds its weights to that log-likelihood, so this
    binds the whole posterior to the calibration evidence by content.
    """
    from .grid import AdmittedForwardTable, PosteriorGrid, gaussian_grid_posterior

    require_split(split)
    if not isinstance(posterior, PosteriorGrid):
        raise InferenceProblemError(
            f"a held-out statement is made about a PosteriorGrid, got {type(posterior).__name__}"
        )
    split.require_posterior_was_fitted_here(posterior.dataset_id)
    if not isinstance(calibration_table, AdmittedForwardTable):
        raise InferenceProblemError(
            "binding a posterior to its calibration half needs the admitted forward "
            "table over the posterior's points at the calibration conditions"
        )
    if (
        calibration_table.parameter_names != posterior.parameter_names
        or calibration_table.points.shape != posterior.points.shape
        or not np.array_equal(calibration_table.points, posterior.points)
    ):
        raise DataLeakageError(
            "the calibration forward table is not over the posterior's parameter "
            "support, so it cannot show which evidence the posterior was conditioned on"
        )
    recomputed = gaussian_grid_posterior(calibration_table, split.calibration).log_likelihood
    stored = posterior.log_likelihood
    same_support = np.array_equal(np.isfinite(stored), np.isfinite(recomputed))
    finite = np.isfinite(stored)
    if not same_support or not np.allclose(
        stored[finite], recomputed[finite],
        rtol=_LIKELIHOOD_BINDING_RTOL, atol=_LIKELIHOOD_BINDING_ATOL,
    ):
        worst = (
            float(np.max(np.abs(stored[finite] - recomputed[finite])))
            if same_support and np.any(finite) else float("inf")
        )
        raise DataLeakageError(
            f"the posterior labelled {posterior.dataset_id!r} is not conditioned on "
            f"this split's calibration half: its log-likelihood differs from the "
            f"likelihood of the calibration observations by up to {worst:.3g} nats. "
            f"A matching dataset id is a label; a posterior fitted to other evidence "
            f"-- the held-out rows included -- cannot be scored as held-out validation"
        )


def allow_exact_replicates(split_kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Declare that a study genuinely carries bit-identical replicates.

    A function rather than a bare ``True`` so that the declaration reads as a
    decision at the call site, and so that grepping for it finds every study
    that made it.
    """
    payload = dict(split_kwargs)
    payload["exact_replicates_allowed"] = True
    return payload


def require_split(value: object) -> ObservationSplit:
    if not isinstance(value, ObservationSplit):
        raise InferenceProblemError(
            f"held-out validation operates on an ObservationSplit, got "
            f"{type(value).__name__}; two ObservationSets passed side by side "
            f"are what this type exists to replace"
        )
    return value
