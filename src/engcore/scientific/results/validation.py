"""Validation reporting.

Three deliberate design decisions:

1. **Checks coexist; the level is derived, never asserted.** A single scalar
   "validation level" is misleading, because dimensional validity, numerical
   convergence and experimental agreement are independent claims. A report
   therefore holds a list of checks, and any attained level must be *backed
   by a passing check that declares it*.

2. **NOT_RUN is distinct from PASS.** A check that never executed can never
   contribute evidence. This is the mechanism that prevents a result from
   claiming validation that was not actually performed.

3. **A check may not claim more than its own numbers support.** Decisions 1
   and 2 between them established that a level is backed by a *passing* check
   that *compared something*. Neither of them asked whether the comparison
   succeeded, and so neither of them stopped a check from reporting PASS with
   ``residual=10.0`` beside ``tolerance=1e-6`` -- seven orders outside its own
   bound -- and carrying ``ANALYTICALLY_VERIFIED`` all the way to a SUPPORTED
   verdict. The level was derived, exactly as decision 1 promises. The *pass*
   was asserted. See :func:`comparison_met_its_bound` and
   :func:`outcome_is_earned`.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..sequences import duplicates
from ..errors import ScientificValidationError
from ..serialization import require_schema, require_schema_any, schema_string

CHECK_SCHEMA = schema_string("validation_check")

#: R-45 (re-audit 2026-09-16): `/2` because CORE-013 changed what `status` MEANS. The precedence went from
#: FAIL > WARNING > PASS > NOT_RUN to FAIL > NOT_RUN > WARNING > PASS, under an unchanged schema string, and
#: `from_dict` compares a stored status with the recomputed one -- so every report the older tree wrote with a
#: PASS and a NOT_RUN check -- the ordinary shape of a solve that verified what it could and left one
#: comparison ungathered -- was refused
#: on read as a contradiction. A version string is the only place a reader can learn that a field's meaning
#: changed, and `/1` payloads are read under the precedence they were written with.
REPORT_SCHEMA = schema_string("validation_report", 2)
LEGACY_REPORT_SCHEMA = schema_string("validation_report")


def compared_something(
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> bool:
    """Is there evidence that a comparison was performed?

    Two admissible forms, and the second is why the rule is not written as
    "must have a residual".

    **A measured quantity against a stated bound** -- ``residual`` *and*
    ``tolerance``. Both, not either: a residual with no tolerance is a number
    nobody bounded, and a tolerance with no residual is a bound with nothing
    measured against it. Neither on its own is a comparison.

    **A named reference** -- a non-empty ``evidence``. Some levels are
    established by comparing against something that yields no number at all.
    ``DIMENSIONALLY_VALID`` is the standing example: what is compared is the
    dimension of each produced metric against the ``unit_exemplar`` its
    ``ModelOutputSpec`` declares, and the outcome is a yes or a no, not a
    residual that could be small. Writing the rule as "must have a residual"
    would be narrower than the truth and would push an honest check into
    claiming a number it does not have.
    """
    if residual is not None and tolerance is not None:
        return True
    return bool(evidence)


def comparison_met_its_bound(
    residual: float | None,
    tolerance: float | None,
) -> bool | None:
    """Did the measured quantity actually meet the bound it was judged against?

    Three answers, and the third is the one that keeps this rule from
    swallowing the evidence-only form :func:`compared_something` exists to
    protect.

    ``None`` -- **there is no comparison of this shape to judge.** Either
    number absent. ``DIMENSIONALLY_VALID`` is the standing example: what it
    compares is a dimension against a ``unit_exemplar``, and the outcome is a
    yes or a no, not a number that could be small. A check in that form has
    nothing here to contradict, and this function says so rather than
    inventing a verdict about it.

    ``False`` -- the residual missed the bound, *or* either number is not
    finite. A NaN is refused for the reason :class:`RouteComparison` already
    refuses one: ``nan <= tolerance`` is ``False`` and ``nan > tolerance`` is
    also ``False``, so a rule written only as "not greater than" would read a
    NaN as compliant and let the identical defect back in wearing a different
    hat. A quantity that cannot be ordered against its bound was not compared
    to it.

    ``True`` -- both numbers are finite and ``abs(residual) <= tolerance``.

    **The DISTANCE, not the signed number** (R-46, re-audit 2026-09-16). This
    was written ``residual <= tolerance``, and a tolerance bounds how far a
    measured quantity may stand from its reference: a residual of -10 stands
    10 away. Under the signed form the bound could not be missed from below at
    all, so the defect this module's docstring describes -- a PASS seven orders
    outside its own bound, carrying a level all the way to a SUPPORTED verdict
    -- came straight back with a minus sign, and a negative tolerance that no
    magnitude can meet was accepted beside it. Every gate in this repository
    already passes an ``abs`` value in, so what changes is the rule, not the
    numbers any of them report.
    """
    if residual is None or tolerance is None:
        return None
    residual = float(residual)
    tolerance = float(tolerance)
    if not (math.isfinite(residual) and math.isfinite(tolerance)):
        return False
    return abs(residual) <= tolerance


def outcome_is_earned(
    outcome: "ValidationOutcome",
    establishes: "ValidationLevel | None",
    residual: float | None,
    tolerance: float | None,
) -> bool:
    """GUARD 21's rule, over plain fields rather than over an object.

    Fields rather than a check, for the reason :func:`level_is_earned` gives
    and for the same reason: a rule an object could answer for itself is the
    shape of the defect being closed.

    **The rule.** A check that *claims success* while carrying both a residual
    and a tolerance must have met that tolerance. ``compared_something``
    establishes that a comparison happened; this establishes that it
    succeeded. Nothing else in this module asked, which is how a PASS carrying
    ``residual=10.0`` against ``tolerance=1e-6`` reached a SUPPORTED verdict
    with its own numbers standing seven orders away, in the same record,
    disagreeing with it.

    **What counts as claiming success**, and why this is not scoped to
    ``outcome`` alone. Two claims live on a check and they are separable:

    * ``outcome is PASS`` claims *this check succeeded*. There is no reading
      of PASS under which "the number missed its bound" is consistent, so a
      PASS is held to the comparison unconditionally -- level or no level.
    * ``establishes=X`` claims *X is now backed by this check*. That claim is
      made by a WARNING too, and a WARNING is a pass with a caveat when it
      makes it, so a level-declaring WARNING is held to the same standard.

    **A WARNING that declares no level claims neither, and is left alone.**
    That is not an exemption carved for a site; it is the rule reaching only
    as far as the claims. A level-free WARNING is inert as evidence:
    ``attained_levels`` reads ``c.passed``, which is ``outcome is PASS``, so
    such a check contributes nothing for a residual to contradict. And the
    form is load-bearing rather than incidental -- ``RouteConsensus.to_check``
    builds exactly one, deliberately, for routes that share their machinery
    and disagree: the disagreement is a real finding about the implementation,
    reported with the two numbers that are the *reason* for the WARNING, while
    the level is already withheld because ``earned`` requires agreement.
    Refusing that construction would delete the platform's only way to say
    "these routes disagreed and I am not calling it a scientific failure" and
    would replace a correct scientific report with an exception.

    **FAIL and NOT_RUN claim nothing** and are not held to anything here. A
    FAIL is free to sit inside its tolerance, and one in this repository does:
    a refinement gate FAILs on a residual that is *within* bound when the
    sequence behind it never contracted, because agreement with no convergent
    sequence behind it is not verification. That construction is also why this
    is a refusal and not a derivation -- see
    :meth:`ValidationCheck.__post_init__`.
    """
    met = comparison_met_its_bound(residual, tolerance)
    if met is None or met:
        return True
    if outcome is ValidationOutcome.PASS:
        return False
    if outcome is ValidationOutcome.WARNING and establishes is not None:
        return False
    return True


def level_is_earned(
    establishes: "ValidationLevel | None",
    outcome: "ValidationOutcome",
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> bool:
    """GUARD 2's rule, over plain fields rather than over an object.

    It takes fields rather than a check for one reason: the rule has to be
    applicable to something that *claims* to be a check. A method can be
    overridden and a property can be shadowed, so a rule that could only be
    asked of an object would be a rule the object got to answer for itself --
    which is the shape of the defect this function exists to close, one level
    down. Read the fields, apply the rule, decide here.

    **The rule.** A check that PASSes and declares a level must have compared
    something. A PASS with a level and no residual, no tolerance and no
    reference is a *claimed* level: a sentence asserting that the thing it
    names is true, occupying the field a reader consults to find out whether
    anybody checked.

    **Scoped to PASS and WARNING, deliberately.** A FAIL or NOT_RUN check
    contributes no level to ``attained_levels`` whatever it declares, so
    requiring evidence from one would be demanding proof of a claim nobody is
    making. A WARNING is a pass with a caveat and is held to the same standard.
    A check that declares no level asserts nothing and needs to show nothing.
    """
    if establishes is None:
        return True
    if outcome not in (ValidationOutcome.PASS, ValidationOutcome.WARNING):
        return True
    return compared_something(residual, tolerance, evidence)


def _issuer_gap(
    establishes: "ValidationLevel | None",
    outcome: "ValidationOutcome",
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> str | None:
    """Why a check claiming one of the strongest levels names no verifiable issuer, or ``None``.

    VAL-01. ``ValidationCheck(PASS, establishes=CROSS_SOLVER_VALIDATED,
    evidence=("trust me",))`` was attained, survived ``from_dict`` and carried a
    hand-authored evidence payload to a verdict: GUARD 2 asks only that
    *something* was compared, and a sentence is something. Threshold authority
    protected the gates that award a level and never the record that carries
    one.

    So the three levels only an external issuer can grant --
    ``CROSS_SOLVER_VALIDATED``, ``BENCHMARK_VALIDATED`` and
    ``EXPERIMENTALLY_VALIDATED`` -- are held to the issuer's own record, which
    the issuer writes into ``evidence`` when it awards the level and which is
    re-verified here against registries the caller does not hold. Fields, not
    an object, for :func:`level_is_earned`'s reason. Scoped to the claims:
    PASS and WARNING only, and only those three levels.

    What this cannot do is tell an issued record from a faithful copy of one: a
    check copied from a genuine consensus onto another result carries a genuine
    record. Closing that needs the record to be bound to the result it
    qualifies, which the frozen shape of this check has no field for.
    """
    if establishes is None or outcome not in (
        ValidationOutcome.PASS,
        ValidationOutcome.WARNING,
    ):
        return None
    level = ValidationLevel(establishes)
    if level is ValidationLevel.CROSS_SOLVER_VALIDATED:
        return _consensus_issuer_gap(residual, tolerance, tuple(evidence))
    if level in (
        ValidationLevel.BENCHMARK_VALIDATED,
        ValidationLevel.EXPERIMENTALLY_VALIDATED,
    ):
        return _oracle_issuer_gap(level, residual, tolerance, tuple(evidence))
    if level is ValidationLevel.ANALYTICALLY_VERIFIED:
        # TWO legitimate issuers, which is what the audit's fix direction asks for: "a pinned oracle
        # record OR a declared threshold set". A pinned ANALYTIC_REFERENCE oracle awards this level
        # through `_LEVEL_BY_KIND`, and a domain gate awards it against a registered closed form.
        # An `oracle:` line says which rule the record is claiming, so the two cannot be mixed to
        # satisfy neither.
        if any(isinstance(line, str) and line.startswith("oracle:") for line in evidence):
            return _oracle_issuer_gap(level, residual, tolerance, tuple(evidence))
        return _analytic_issuer_gap(tuple(evidence))
    return None


#: Where the domain layer pins the closed forms it stands behind (R-04, core re-audit 2026-09-16).
#: Read by name, like the threshold and route declarations, so the core never learns what is in it.
ANALYTIC_REFERENCE_DECLARATIONS_ATTRIBUTE = "SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS"

#: How an analytic reference's issuer names it in a check's evidence: ``"<reference id>: <expression>"``.
#: The producers already wrote exactly this line; what was missing was anything that CHECKED it.
ANALYTIC_REFERENCE_EVIDENCE_SEPARATOR = ": "


def _analytic_references() -> Mapping[str, Any]:
    """The domain layer's pinned analytic references, or none if it pins none."""
    import importlib

    try:
        package = importlib.import_module(f"{__name__.split('.')[0]}.domains")
    except ImportError:  # pragma: no cover - an installation without its domains
        return {}
    table = getattr(package, ANALYTIC_REFERENCE_DECLARATIONS_ATTRIBUTE, None)
    return table if isinstance(table, Mapping) else {}


def _threshold_declarations() -> Mapping[str, Any]:
    """The domain layer's pinned verification gates, read the way the thresholds module reads them."""
    from .thresholds import _declarations

    return _declarations()


def _analytic_issuer_gap(evidence: tuple[str, ...]) -> str | None:
    """Why a check claiming ANALYTICALLY_VERIFIED names no verifiable issuer, or ``None``.

    R-04 (core re-audit 2026-09-16). An issuer record was required for only the three levels above
    this one, and this one needed nothing but GUARD 2's "something was compared" -- where a sentence
    is something. ``ValidationCheck(PASS, establishes=ANALYTICALLY_VERIFIED, evidence=("trust me",))``
    was constructed, attained, survived ``from_dict`` and carried a SUPPORTED verdict, while the very
    same construction claiming BENCHMARK_VALIDATED was refused. And every SUPPORTED report either MCP
    tool can return rests on exactly this level.

    The rule is the oracle rule's shape and the consensus rule's second half, neither invented here:

    1. the check names exactly one analytic reference, as ``"<reference id>: <expression>"`` --
       which is the line all three producers already wrote;
    2. that reference is REGISTERED by the domain layer, because a reference id is a public string
       and was never proof of anything;
    3. the expression the check names is the registered expression, byte for byte -- what makes the
       level meaningful is WHICH closed form the solve was compared against;
    4. the check names exactly one threshold record, of the gate the registration says awards this
       reference's level, and that record is that gate's declared set: the level belongs to the
       domain that awards it, and a set that is not the domain's own awards nothing.

    **Why the expression and not a digest of it.** The oracle rule requires a content digest because
    an oracle's evidence is data the caller does not hold, so the digest binds the claim to something
    outside the check. An analytic reference's expression is *in the source*, and a digest of a public
    value carries no more authority than the value: anyone who can copy one can copy the other. So the
    authority here is the registry (this id is one the repository stands behind) and the declared
    threshold set (which a caller cannot forge), and the expression is compared in full rather than
    through a digest that would add a step and no strength.

    This also means no producer has to write a new evidence line, which matters: everything under
    ``src/engcore/domains/thermal/`` is SHA-256 pinned by the frozen thermal_t1/t2/t3 experiments,
    whose claim is that their measured bias is a property of *that* solver. That pin is evidence this
    work has no authority to spend, so the rule is written to the records the producers already keep.

    What this cannot do is tell an issued record from a faithful copy of one, which is
    :func:`_issuer_gap`'s own residual, verbatim: a check copied from a genuine solve onto another
    result carries a genuine record, and closing that needs the record bound to the result it
    qualifies, which the frozen shape of this check has no field for.
    """
    references = _analytic_references()
    named = [
        line.split(ANALYTIC_REFERENCE_EVIDENCE_SEPARATOR, 1)
        for line in evidence
        if isinstance(line, str) and ANALYTIC_REFERENCE_EVIDENCE_SEPARATOR in line
        and line.split(ANALYTIC_REFERENCE_EVIDENCE_SEPARATOR, 1)[0] in references
    ]
    if len(named) != 1:
        return (
            f"it names no single analytic reference this layer pins; the registry holds "
            f"{sorted(references)}"
        )
    reference_id, expression = named[0]
    declaration = references[reference_id]
    if not isinstance(declaration, Mapping):
        return f"analytic reference {reference_id!r} is not pinned by the analytic reference registry"
    if expression != declaration.get("expression"):
        return (
            f"the closed form it names for {reference_id!r} is not the registered one: the level says "
            f"a solve agreed with a specific closed form, and this is a different statement"
        )
    gate_id = declaration.get("thresholds_gate")
    records = [
        line[len("thresholds:"):]
        for line in evidence
        if isinstance(line, str) and line.startswith("thresholds:")
    ]
    if len(records) != 1:
        return (
            f"it carries no single verification threshold record; {reference_id!r}'s level is awarded "
            f"by gate {gate_id!r} and a check that does not say which numbers it was judged against "
            f"has not said the gate judged it"
        )
    # ONE comparison, against the domain layer's pin -- not an object rebuilt from the evidence, and
    # not three checks where one does the work.
    #
    # `VerificationThresholds.evidence()` writes `thresholds:<gate>@<version>#<fingerprint>`, where
    # the fingerprint is the first 16 hex of the values digest and a caller's override carries
    # `+override.<marker>` in its version. The expected string is built from the gate the REGISTRY
    # names for this reference, so a record naming another gate, another version, or other numbers
    # fails the same comparison -- which is why there is one. The first draft had three, and the
    # batch-9 mutation run showed two of them were dead: removing either left the third catching
    # every case, because all three were compared against the registry's gate rather than the
    # record's own. That is the same four steps `_verified_against_declaration` applies -- registered
    # gate, registered version, registered values digest, not an override -- read off the line.
    declared_gate = _threshold_declarations().get(gate_id)
    if not isinstance(declared_gate, Mapping):
        return f"gate {gate_id!r} is not pinned by the verification threshold registry"
    pinned = str(declared_gate.get("threshold_digest") or "")
    expected = f"{gate_id}@{declared_gate.get('version')}#{pinned[:16]}"
    if records[0] != expected:
        return (
            f"its threshold record is {records[0]!r}; the set {gate_id!r} declares is {expected!r}. A "
            f"record naming another gate, another version of it, or other numbers is a threshold "
            f"specification and not the awarding gate's own, and awards nothing"
        )
    return None


_BINDING_LINE = re.compile(
    r"^route (?P<route>\S+) read from result (?P<result>.+) of run (?P<run>.+) "
    r"by .+; numbers sha256:[0-9a-f]{64}$"
)


def _consensus_issuer_gap(
    residual: float | None, tolerance: float | None, evidence: tuple[str, ...]
) -> str | None:
    """The record ``CrossSolverConsensus.to_check`` writes, re-verified."""
    from ..consensus import (
        CONSENSUS_THRESHOLDS_EVIDENCE_PREFIX,
        INDEPENDENCE_BASES,
        INDEPENDENCE_BASIS_EVIDENCE_PREFIX,
        _route_declarations,
    )
    from .thresholds import VerificationThresholds

    records = [
        line[len(CONSENSUS_THRESHOLDS_EVIDENCE_PREFIX):]
        for line in evidence
        if isinstance(line, str) and line.startswith(CONSENSUS_THRESHOLDS_EVIDENCE_PREFIX)
    ]
    if len(records) != 1:
        return "it carries no single consensus threshold record"
    # R-21 (I-12 part B): WHICH independence the level rests on. The level was awarded on declared
    # independence and on byte-verified artifact independence alike, and a reader could not tell the two
    # apart -- the gate that requires the bytes had no caller. Exactly one of the two enumerated bases, so a
    # check can neither omit the statement nor claim both.
    bases = [
        line[len(INDEPENDENCE_BASIS_EVIDENCE_PREFIX):]
        for line in evidence
        if isinstance(line, str) and line.startswith(INDEPENDENCE_BASIS_EVIDENCE_PREFIX)
    ]
    if len(bases) != 1 or bases[0] not in INDEPENDENCE_BASES:
        return (
            f"it names no single independence basis out of {list(INDEPENDENCE_BASES)}: a level earned from "
            f"declarations the domain layer pins and a level earned from the artifacts' own bytes are not "
            f"the same claim, and a reader cannot tell them apart from the level alone"
        )
    try:
        record = json.loads(records[0])
        thresholds = VerificationThresholds(
            gate_id=record["gate_id"],
            version=record["version"],
            values=dict(record["values"]),
        )
        key = str(record["tolerance_key"])
    except (ValueError, KeyError, TypeError, ScientificValidationError):
        return "its consensus threshold record cannot be read"
    if not thresholds.is_declared:
        return f"its threshold record {thresholds.identity} is not a declared set"
    if key not in thresholds:
        return f"its threshold record names no {key!r}"
    if residual is None or tolerance is None or float(tolerance) != thresholds[key]:
        return (
            f"its tolerance {tolerance!r} is not {key!r} of {thresholds.identity}"
        )
    bindings: dict[str, tuple[str, str]] = {}
    for line in evidence:
        match = _BINDING_LINE.match(line) if isinstance(line, str) else None
        if match:
            bindings[match.group("route")] = (match.group("result"), match.group("run"))
    if len(bindings) < 2:
        return "it is bound to fewer than two executed routes"
    results = [result for result, _ in bindings.values()]
    runs = [run for _, run in bindings.values()]
    if len(set(results)) != len(results) or len(set(runs)) != len(runs):
        return "its routes are not bound to distinct results and runs"
    pins = _route_declarations()
    verified = "dependencies verified against the domain layer's pin"
    for route_id in sorted(bindings):
        pin = pins.get(route_id)
        if not isinstance(pin, Mapping) or (
            pin.get("threshold_gate_id"), pin.get("tolerance_key")
        ) != (thresholds.gate_id, key):
            return (
                f"route {route_id!r} is not declared for comparison under "
                f"{thresholds.gate_id!r} at {key!r}"
            )
        if not any(
            isinstance(line, str)
            and line.startswith(f"route {route_id} = ")
            and line.endswith(verified)
            for line in evidence
        ):
            return f"route {route_id!r} carries no verified dependency declaration"
    return None


def _oracle_issuer_gap(
    level: "ValidationLevel",
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> str | None:
    """The record ``OracleEvidenceSet.compare`` writes, re-verified against the pin."""
    from .. import oracles

    def one(prefix: str) -> str | None:
        found = [
            line[len(prefix):]
            for line in evidence
            if isinstance(line, str) and line.startswith(prefix)
        ]
        return found[0] if len(found) == 1 else None

    identity = one("oracle:")
    digest = one("sha256:")
    reference = one("reference:")
    if identity is None or digest is None or reference is None:
        return "it carries no single oracle identity, content digest and reference"
    if "oracle-authority:repository-pinned" not in evidence:
        return "its oracle record does not say it was repository-pinned"
    oracle_id, _, version = identity.rpartition("@")
    declaration = oracles._TRUSTED_ORACLE_DECLARATIONS.get((oracle_id, version))
    if not isinstance(declaration, Mapping):
        return f"oracle {identity!r} is not pinned by the trusted oracle registry"
    try:
        kind = oracles.OracleKind(declaration.get("kind"))
    except ValueError:
        return f"the trusted declaration of {identity!r} names no oracle kind"
    if oracles._LEVEL_BY_KIND.get(kind) is not level:
        return f"oracle {identity!r} is pinned as {kind.value}, which does not award {level.value}"
    if declaration.get("evidence_digest") != digest or declaration.get("reference") != reference:
        return f"oracle {identity!r} does not match its trusted declaration"
    if residual is None or tolerance is None or float(tolerance) != 1.0:
        return "its oracle comparison carries no normalised residual against 1.0"
    return None


class ValidationOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_RUN = "not_run"
    #: R-45: there was no way to say "there was nothing here to check". NOT_RUN means the evidence was not
    #: gathered, which is why CORE-013 put it above PASS -- a report must not pass on the strength of a check
    #: nobody performed. "This circuit has no voltage source" is a different statement: there is no evidence
    #: to gather and no claim left unbacked by its absence. Collapsing the two made every report holding one
    #: permanently NOT_RUN, which is what made SRIA report that validation was never run about a report in
    #: which everything applicable ran and passed. Appended: the member order is frozen.
    NOT_APPLICABLE = "not_applicable"


class ValidationLevel(str, Enum):
    """What has been established, in increasing evidentiary strength.

    These are *claims about evidence*, not a quality score. A result may
    attain several independently (dimensional validity and numerical
    convergence say different things).

    ``UNVERIFIED`` is the odd one out and is **not a level a check may
    establish** — see :attr:`ValidationCheck.establishes`, which refuses it. It
    is the sentinel for the *absence* of verification, kept as a member because
    it names that state for a reader and for :func:`unverified_report`, and
    kept out of every attained-level computation by being unable to reach one.
    """

    UNVERIFIED = "unverified"
    DIMENSIONALLY_VALID = "dimensionally_valid"
    NUMERICALLY_CONVERGED = "numerically_converged"
    ANALYTICALLY_VERIFIED = "analytically_verified"
    BENCHMARK_VALIDATED = "benchmark_validated"
    CROSS_SOLVER_VALIDATED = "cross_solver_validated"
    EXPERIMENTALLY_VALIDATED = "experimentally_validated"


#: CORE-008: the levels that compare a result with something outside the model that produced it.
#:
#: R-39 (re-audit 2026-09-16, I-12 part A): CROSS_SOLVER_VALIDATED is NOT one of them, and used to be.
#: Agreement between two solvers of ONE declared model compares two implementations, not the model with
#: anything outside itself -- and the classification contradicted three statements this tree already makes
#: about itself. `evidence_basis` below defines these levels as the ones that "compare it with something
#: outside itself". `scientific/consensus.py` says two routes may "realize the same mathematical
#: formulation" and still count as independent, because only shared ARITHMETIC is excluded:
#: `SOLVER_INDEPENDENCE_DIMENSIONS` leaves the PROBLEM DECLARATION out, and that module's own docstring says
#: a declaration error "is invisible to every route that reads it". Each pinned pair of routes shares its
#: declaration, and the consensus record itself lists that declaration as a SHARED dependency; each pair
#: solves the same declared relations, which the declaring layer states are SELF_CONSISTENT and neither
#: benchmark- nor experimentally validated. So a result whose only other levels were dimensional validity
#: and numerical convergence moved from VERIFICATION_ONLY to VALIDATED the moment a cross-solver check was
#: attached -- and a model declared with a wrong parameter value read VALIDATED, because both solvers agree
#: about the wrong model. The level itself is unchanged and still says exactly what it said; what changed is
#: the KIND of evidence it is counted as. The instances are named in
#: `docs/audits/CORE_REAUDIT_2026-09-16.md`, which is where this core is allowed to know about them.
VALIDATION_LEVELS = frozenset({
    ValidationLevel.BENCHMARK_VALIDATED,
    ValidationLevel.EXPERIMENTALLY_VALIDATED,
})

#: The other kind: levels that say the DECLARED MODEL was solved correctly. Named rather than left as
#: "everything else" (R-39) because that is how a level ended up in the wrong group -- one kind was a set and
#: the other was the remainder, so a member added later was silently verification and nobody had to decide.
VERIFICATION_LEVELS = frozenset({
    ValidationLevel.DIMENSIONALLY_VALID,
    ValidationLevel.NUMERICALLY_CONVERGED,
    ValidationLevel.ANALYTICALLY_VERIFIED,
    ValidationLevel.CROSS_SOLVER_VALIDATED,
})


def _require_every_level_is_classified() -> None:
    """Refuse to import while any level is in both kinds, in neither, or both at once (R-39).

    The same discipline ``mcp/server.py::_audit_tables`` applies to the verdict tables, for the same reason:
    a member nobody classified reaches a reader as one kind by default, and the default was wrong once
    already. UNVERIFIED is the sentinel and is in neither set -- ``ValidationCheck`` refuses it, so no check
    can establish it and no attained-level computation can see it.
    """
    overlap = VALIDATION_LEVELS & VERIFICATION_LEVELS
    if overlap:
        raise ScientificValidationError(
            f"levels {sorted(level.value for level in overlap)} are both validation and verification"
        )
    classified = VALIDATION_LEVELS | VERIFICATION_LEVELS
    if ValidationLevel.UNVERIFIED in classified:
        raise ScientificValidationError(
            "UNVERIFIED is the absence of verification and is neither kind of evidence"
        )
    unclassified = {
        level for level in ValidationLevel if level is not ValidationLevel.UNVERIFIED
    } - classified
    if unclassified:
        raise ScientificValidationError(
            f"levels {sorted(level.value for level in unclassified)} are neither validation nor "
            f"verification: a level nobody classified reaches a reader as one of them by default, and "
            f"`evidence_basis` would say which kind of evidence a report holds without anybody having "
            f"decided"
        )


_require_every_level_is_classified()


@dataclass(frozen=True)
class ValidationCheck:
    """One executed (or deliberately skipped) verification step."""

    name: str
    outcome: ValidationOutcome
    detail: str = ""
    establishes: ValidationLevel | None = None
    residual: float | None = None
    tolerance: float | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ScientificValidationError("validation check requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "outcome", ValidationOutcome(self.outcome))
        if self.establishes is not None:
            establishes = ValidationLevel(self.establishes)
            # The sentinel is the absence of verification, so a check that
            # established it would be claiming to have established an absence.
            #
            # Refused **here**, at the one site where the claim is made, rather
            # than filtered at each site that reads it. Those sites are
            # `attained_levels`, `claims`, `require_level` and every consumer's
            # own `required_levels`, and the review found the last of them
            # disagreeing with the first: a passing check declaring UNVERIFIED
            # satisfied a caller's demand for it and produced a SUPPORTED
            # verdict — nothing verified, saying so, read as evidence. A rule
            # enforced at four reading sites is a rule that will be missed at
            # the fifth; a value that cannot exist cannot be read
            # inconsistently.
            #
            # Every outcome, not only PASS. A NOT_RUN check that "established
            # unverified" is the same category error in a humbler voice, and
            # allowing it would leave a payload shape whose meaning depends on
            # a field that is supposed to be inert.
            #
            # The way to say a check earned nothing is unchanged and is the one
            # the platform means: leave `establishes` as None. The lumped
            # residual check and the resistance admissibility bound already do,
            # and `unverified_report` builds a NOT_RUN check with no level at
            # all.
            # R-45: and neither can a check that did not apply. The level would be backed by the absence
            # of anything to check, which is the same category error as establishing UNVERIFIED, one field
            # over. Refused here for the same reason: a value that cannot be built cannot be read
            # inconsistently.
            if ValidationOutcome(self.outcome) is ValidationOutcome.NOT_APPLICABLE and establishes is not None:
                raise ScientificValidationError(
                    f"validation check {str(self.name).strip()!r} reports NOT_APPLICABLE and declares "
                    f"establishes={establishes.value}. A check that did not apply established nothing: there "
                    f"was no evidence to gather, so there is nothing for a level to rest on. Leave establishes "
                    f"unset, which is how a check says it earned nothing"
                )
            if establishes is ValidationLevel.UNVERIFIED:
                raise ScientificValidationError(
                    f"validation check {str(self.name).strip()!r} declares "
                    f"establishes=UNVERIFIED. That is the sentinel for the "
                    f"absence of verification, not a level: a check cannot "
                    f"establish that nothing was established. Leave "
                    f"establishes unset to say a check earned no level"
                )
            object.__setattr__(self, "establishes", establishes)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        # GUARD 2, enforced. A PASS or WARNING declaring a level must carry
        # evidence that it compared something -- see `earns_its_level`, which
        # states the rule and is what this refuses on.
        #
        # This was a checked invariant in `tests/test_core_guards.py` rather
        # than a refusal, and the only reason was one construction inside a
        # byte-pinned file that could not be edited. The thermal re-freeze
        # fixed it, so the rule moves here, beside the `establishes=UNVERIFIED`
        # refusal it belongs next to and for the identical reason: a rule
        # enforced at the four sites that read levels is a rule that will be
        # missed at the fifth, and a value that cannot be constructed cannot be
        # read inconsistently.
        #
        # No exception, deliberately. An enforced guard with one exception is
        # an opt-in guard with extra words, and the hole would be the shape of
        # the next domain's mistake.
        if not self.earns_its_level:
            raise ScientificValidationError(
                f"validation check {self.name!r} reports "
                f"{self.outcome.value.upper()} and declares "
                f"establishes={self.establishes.value}, but carries no "
                f"evidence that anything was compared: no residual with a "
                f"tolerance, and no reference in `evidence`. A level with "
                f"nothing behind it is a claim occupying the field a reader "
                f"consults to find out whether anybody checked. Record what "
                f"was compared -- a residual and its bound, or the reference "
                f"the comparison was made against -- or leave establishes "
                f"unset, which is how a check says it earned nothing"
            )
        if self.residual is not None:
            object.__setattr__(self, "residual", float(self.residual))
        if self.tolerance is not None:
            object.__setattr__(self, "tolerance", float(self.tolerance))
            # R-46, every outcome. No magnitude can be at most a negative
            # number, so a negative tolerance is a bound nothing satisfies and
            # the comparison it belongs to has no content. Refused for a FAIL
            # and a NOT_RUN as well as for the outcomes that claim something:
            # a FAIL against a bound that cannot be met is not a finding about
            # the model, and the field is read by consumers -- the threshold
            # pins, the SRIA budgets -- that never look at the outcome. Refused
            # here for the reason stated three times above: a value that cannot
            # be built cannot be read inconsistently.
            if self.tolerance < 0.0:
                raise ScientificValidationError(
                    f"validation check {self.name!r} carries tolerance="
                    f"{self.tolerance!r}. A tolerance bounds how far a measured "
                    f"quantity may stand from its reference, and no distance is "
                    f"at most a negative number: this is a bound nothing can "
                    f"meet, so the comparison it belongs to says nothing either "
                    f"way. Record the bound as the magnitude it is"
                )
        # GUARD 21, enforced. Last, because it reads the two numbers and wants
        # them coerced to float first.
        #
        # REFUSED, NOT DERIVED, and the choice is decided by a construction in
        # this repository rather than by taste. Deriving `outcome` from the two
        # numbers is the stronger-looking move and matches the platform's own
        # principle that a derivable fact should be derived -- but that
        # principle applies only where the fact really is derivable from what
        # is at hand, and `outcome` is not. `residual <= tolerance` is
        # NECESSARY for a PASS and it is not SUFFICIENT: the outcome is a
        # conjunction over evidence the check does not carry.
        #
        # A refinement-gate check in this repository proves it, and the FAST
        # suite exercises the branch. It FAILs while the residual it reports
        # sits INSIDE its own tolerance, because the outcome is a conjunction:
        # the sequence must also have contracted. A single refinement can land
        # close by luck while the sequence never contracts, and agreement with
        # no convergent sequence behind it is not verification, it is a
        # coincidence. A derivation would read those two numbers, see
        # agreement, and promote that FAIL to a PASS carrying a level. It
        # would not close this defect; it would open its mirror image, and the
        # mirror image is the worse one, because it manufactures a level
        # nobody claimed.
        #
        # So the implication is kept in the one direction the numbers support:
        # PASS implies the bound was met, never the converse. What deriving
        # would have cost, beyond that FAIL: the two WARNING forms below, and
        # a change to the meaning of `outcome` at every one of the sixty-odd
        # construction sites across five domains that pass it in today.
        if not self.outcome_is_earned:
            raise ScientificValidationError(
                f"validation check {self.name!r} reports "
                f"{self.outcome.value.upper()}"
                + (
                    f" and declares establishes={self.establishes.value}"
                    if self.establishes is not None
                    else ""
                )
                + f", but its own numbers say the comparison did not succeed: "
                f"residual={self.residual!r} against tolerance="
                f"{self.tolerance!r}. A check that reports success while the "
                f"quantity it measured stands outside the bound it was judged "
                f"against contradicts itself in the same record, and the "
                f"contradiction is invisible to every reader who consults the "
                f"outcome. Report the outcome the comparison actually had, or "
                f"-- if the outcome turns on something these two numbers do "
                f"not decide -- do not report it as a success"
            )
        # VAL-01, last: it reads the coerced numbers and the evidence.
        issuer_gap = _issuer_gap(
            self.establishes, self.outcome, self.residual, self.tolerance, self.evidence
        )
        if issuer_gap is not None:
            raise ScientificValidationError(
                f"validation check {self.name!r} reports "
                f"{self.outcome.value.upper()} and declares "
                f"establishes={self.establishes.value}, and that level has no "
                f"verifiable issuer: {issuer_gap}. The strongest levels are "
                f"granted by a pinned consensus or a pinned oracle, which write "
                f"their record into the check's evidence; a check built by hand "
                f"cannot carry one"
            )

    @property
    def passed(self) -> bool:
        return self.outcome is ValidationOutcome.PASS

    @property
    def compared_something(self) -> bool:
        """Does this check carry evidence that a comparison was performed?

        The rule itself is :func:`compared_something`; this is the way to ask
        it about this check.
        """
        return compared_something(self.residual, self.tolerance, self.evidence)

    @property
    def earns_its_level(self) -> bool:
        """Is this check's declared level backed by an actual comparison?

        The rule itself is :func:`level_is_earned`, which reads fields rather
        than objects. This is the way to ask it about this check, and it is
        deliberately not the only way: ``ValidationReport`` asks the same
        function about whatever it has been handed, because a report that
        asked the object would be letting the object answer for itself.

        **Enforced in ``__post_init__``.** The constructor refuses anything
        that fails it, so a claimed level is a value that cannot be built
        rather than one a sweep looks for. It was a checked invariant until the
        thermal re-freeze: exactly one construction failed the rule and lived
        inside a byte-pinned file, and exempting it would have been a guard
        with a hole in it.
        """
        return level_is_earned(
            self.establishes,
            self.outcome,
            self.residual,
            self.tolerance,
            self.evidence,
        )

    @property
    def comparison_met_its_bound(self) -> bool | None:
        """Did this check's residual meet its tolerance? ``None`` if no such pair.

        The rule itself is :func:`comparison_met_its_bound`; this is the way to
        ask it about this check.
        """
        return comparison_met_its_bound(self.residual, self.tolerance)

    @property
    def outcome_is_earned(self) -> bool:
        """Is this check's claim of success consistent with its own numbers?

        The rule itself is :func:`outcome_is_earned`, which reads fields rather
        than objects. This is the way to ask it about this check, and -- as
        with :attr:`earns_its_level` -- it is deliberately not the only way:
        ``ValidationReport`` asks the same function about whatever it has been
        handed, because a report that asked the object would be letting the
        object answer for itself.

        **Enforced in ``__post_init__``.** A PASS whose residual exceeds its
        tolerance is a value that cannot be built, not one a sweep looks for.
        """
        return outcome_is_earned(
            self.outcome,
            self.establishes,
            self.residual,
            self.tolerance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHECK_SCHEMA,
            "name": self.name,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "establishes": self.establishes.value if self.establishes else None,
            "residual": self.residual,
            "tolerance": self.tolerance,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationCheck":
        require_schema(payload, CHECK_SCHEMA)
        establishes = payload.get("establishes")
        return cls(
            name=payload["name"],
            outcome=ValidationOutcome(payload["outcome"]),
            detail=payload.get("detail", ""),
            establishes=ValidationLevel(establishes) if establishes else None,
            residual=payload.get("residual"),
            tolerance=payload.get("tolerance"),
            evidence=tuple(payload.get("evidence", ())),
        )


@dataclass(frozen=True)
class ValidationReport:
    """The set of checks performed on one result, and what they establish.

    THE SECOND AXIS OF GUARD 2
    ---------------------------
    ``ValidationCheck.__post_init__`` closed the *construction* axis: a check
    claiming a level it did not check for cannot be built. It said nothing
    about the *containment* axis, and this record read whatever it was handed.
    An object that was not a ``ValidationCheck`` at all -- anything with a
    ``passed`` and an ``establishes`` -- placed straight into ``checks``
    reached :attr:`attained_levels`, satisfied :meth:`claims` and passed
    :meth:`require_level`. The constructor rule was never consulted, because
    the constructor was never called.

    That is the third time this shape has appeared here: a guard complete on
    one axis, read as complete. So this record now applies the rule itself, to
    whatever it is given, at both the moment it is given it and every time a
    level is read off it -- and it applies it through :func:`level_is_earned`,
    over fields, so an object that overrides ``earns_its_level`` cannot answer
    the question about itself.
    """

    checks: tuple[ValidationCheck, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        for index, check in enumerate(self.checks):
            if not isinstance(check, ValidationCheck):
                raise ScientificValidationError(
                    f"validation report entry {index} is a "
                    f"{type(check).__name__}, not a ValidationCheck. A record "
                    f"that reads `passed` and `establishes` off whatever it "
                    f"was handed is a record in which the constructor rule was "
                    f"never consulted, because the constructor was never called"
                )
        self._require_every_level_earned()
        self._require_no_check_contradicts_its_numbers()
        self._require_every_strong_level_issued()
        names = [c.name for c in self.checks]
        duplicated = duplicates(names)
        if duplicated:
            raise ScientificValidationError(
                f"duplicate validation check names: {duplicated}"
            )

    def _require_every_level_earned(self) -> None:
        """Apply GUARD 2's rule to the fields of every check held here.

        Redundant with ``ValidationCheck.__post_init__`` for a check that was
        constructed and never touched again, and deliberately so. A frozen
        dataclass refuses ``check.evidence = ()``; it does not refuse
        ``object.__setattr__(check, "evidence", ())``, which is available for
        every frozen record in this repository and cannot be closed on the
        record itself. What *can* be closed is the place where a level stops
        being a field and becomes a claim, and that place is here.
        """
        for check in self.checks:
            if not level_is_earned(
                check.establishes,
                check.outcome,
                check.residual,
                check.tolerance,
                check.evidence,
            ):
                raise ScientificValidationError(
                    f"validation check {check.name!r} in this report reports "
                    f"{ValidationOutcome(check.outcome).value.upper()} and "
                    f"declares establishes="
                    f"{ValidationLevel(check.establishes).value}, but carries "
                    f"no evidence that anything was compared. The constructor "
                    f"refuses this, so a check that reaches a report in this "
                    f"state was altered after it was built or never went "
                    f"through the constructor at all -- either way the level "
                    f"is a claim and not a finding"
                )

    def _require_no_check_contradicts_its_numbers(self) -> None:
        """Apply GUARD 21's rule to the fields of every check held here.

        Redundant with ``ValidationCheck.__post_init__`` for a check that was
        constructed and never touched again, and deliberately so -- the
        argument is :meth:`_require_every_level_earned`'s, verbatim and for the
        same reason. A frozen dataclass refuses ``check.residual = 10.0``; it
        does not refuse ``object.__setattr__(check, "residual", 10.0)``, which
        is available for every frozen record in this repository and cannot be
        closed on the record itself. What *can* be closed is the place where an
        outcome stops being a field and becomes a claim a reader acts on, and
        that place is here.
        """
        for check in self.checks:
            if not outcome_is_earned(
                check.outcome,
                check.establishes,
                check.residual,
                check.tolerance,
            ):
                raise ScientificValidationError(
                    f"validation check {check.name!r} in this report reports "
                    f"{ValidationOutcome(check.outcome).value.upper()} while "
                    f"its own residual {check.residual!r} stands outside its "
                    f"own tolerance {check.tolerance!r}. The constructor "
                    f"refuses this, so a check that reaches a report in this "
                    f"state was altered after it was built or never went "
                    f"through the constructor at all -- either way the success "
                    f"is a claim and not a finding"
                )

    def _require_every_strong_level_issued(self) -> None:
        """Apply VAL-01's rule to the fields of every check held here, now.

        Redundant with the constructor for a check nobody touched, and
        re-applied for the reason the two guards above are -- and for one more:
        an issuer's authority lives in registries that can change, so a level
        is re-verified at the moment it is read as a claim.
        """
        for check in self.checks:
            gap = _issuer_gap(
                check.establishes,
                check.outcome,
                check.residual,
                check.tolerance,
                check.evidence,
            )
            if gap is not None:
                raise ScientificValidationError(
                    f"validation check {check.name!r} in this report declares "
                    f"{ValidationLevel(check.establishes).value}, and that level "
                    f"has no verifiable issuer: {gap}"
                )

    # ---- derived state --------------------------------------------------
    @property
    def status(self) -> ValidationOutcome:
        """Aggregate outcome. FAIL dominates, then NOT_RUN; an empty report is NOT_RUN.

        The comparison rule is re-applied here for the reason it is re-applied
        on :attr:`attained_levels`, one field over. GUARD 2 is about levels, so
        it is re-read where a level becomes a claim; GUARD 21 is about
        *outcomes*, and this is where an outcome becomes one.

        CORE-013 (scientific core audit 2026-09-16): a check that never ran
        outranks a warning and a pass. The order used to be FAIL > WARNING >
        PASS > NOT_RUN, so one passing mesh-convergence check reported PASS
        over an experimental comparison that was never made. ``is_usable``
        reads only "not FAIL" and is unchanged.
        """
        self._require_no_check_contradicts_its_numbers()
        # R-45: a check that did not apply is not part of the precedence at all. It gathers no evidence and
        # leaves no claim unbacked, so it can neither lower the status nor raise it. A report of nothing but
        # inapplicable checks established nothing, which is the empty report's own answer: NOT_RUN.
        outcomes = {c.outcome for c in self.checks} - {ValidationOutcome.NOT_APPLICABLE}
        if ValidationOutcome.FAIL in outcomes:
            return ValidationOutcome.FAIL
        if ValidationOutcome.NOT_RUN in outcomes or not outcomes:
            return ValidationOutcome.NOT_RUN
        if ValidationOutcome.WARNING in outcomes:
            return ValidationOutcome.WARNING
        return ValidationOutcome.PASS

    @property
    def evidence_basis(self) -> str:
        """``VALIDATED``, ``VERIFICATION_ONLY`` or ``NONE``: what kind of evidence the attained levels are (CORE-008).

        Dimensional validity, numerical convergence, analytic verification and agreement between two solvers of
        the same declared model say the declared model was solved correctly. Benchmark and experimental
        validation compare it with something outside itself. A verdict resting on the first kind alone is a
        statement about the solution, not about the world, and this says which kind a report holds so no reader
        has to infer it from level names.

        R-39 (re-audit 2026-09-16): cross-solver agreement moved from the second group to the first. See
        :data:`VALIDATION_LEVELS` for why, in this tree's own words.
        """
        attained = self.attained_levels
        if attained & VALIDATION_LEVELS:
            return "VALIDATED"
        if attained:
            return "VERIFICATION_ONLY"
        return "NONE"

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        """Levels backed by a *passing* check. Never asserted directly.

        ``UNVERIFIED`` can never appear here, and needs no filter to keep it
        out: ``ValidationCheck`` refuses the value, so no check carries it.
        That is why this property, :meth:`claims` and every consumer's
        ``required_levels`` cannot disagree about the sentinel — there is
        nothing for them to disagree about.
        """
        # Re-applied on the read, not only on construction. A check can be
        # altered after the report holding it was built, and the level only
        # matters at the moment it is read as a claim -- so the rule is applied
        # at that moment, over fields, whatever the object says about itself.
        self._require_every_level_earned()
        self._require_no_check_contradicts_its_numbers()
        self._require_every_strong_level_issued()
        return frozenset(
            c.establishes
            for c in self.checks
            if c.passed and c.establishes is not None
        )

    def claims(self, level: ValidationLevel) -> bool:
        return ValidationLevel(level) in self.attained_levels

    @property
    def failures(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.FAIL)

    @property
    def warnings(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.WARNING)

    @property
    def not_run(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.NOT_RUN)

    @property
    def not_applicable(self) -> tuple[ValidationCheck, ...]:
        """The checks that had nothing to check (R-45), which `not_run` deliberately does not name."""
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.NOT_APPLICABLE)

    def with_check(self, check: ValidationCheck) -> "ValidationReport":
        return ValidationReport(checks=(*self.checks, check), notes=self.notes)

    def require_level(self, level: ValidationLevel) -> None:
        """Raise unless the level was actually established."""
        if not self.claims(level):
            raise ScientificValidationError(
                f"validation level {ValidationLevel(level).value!r} was not "
                f"established by any passing check"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "checks": [c.to_dict() for c in self.checks],
            "status": self.status.value,
            "attained_levels": sorted(l.value for l in self.attained_levels),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationReport":
        version = require_schema_any(payload, (REPORT_SCHEMA, LEGACY_REPORT_SCHEMA))
        report = cls(
            checks=tuple(
                ValidationCheck.from_dict(c) for c in payload.get("checks", ())
            ),
            notes=payload.get("notes", ""),
        )
        # Derived fields in the payload are advisory; recompute and verify so a
        # hand-edited record cannot smuggle in an unearned validation claim.
        #
        # RES-08: compared whenever the key is PRESENT. The list used to be
        # compared only when non-empty, so `[]` stood over a report that attains
        # a level -- a record denying its own evidence -- and `status` was never
        # compared at all, so PASS could be written over a FAIL. A payload
        # without the keys is read as written; one that states them must state
        # what its checks produce.
        # R-45: a `/1` record's status is resolved against the precedence its version names, BEFORE the
        # comparison below, which is left exactly as it was for every record written since the bump.
        if version == LEGACY_REPORT_SCHEMA:
            payload = _legacy_status_read(payload, report)
        if "attained_levels" in payload:
            declared = set(payload.get("attained_levels") or ())
            recomputed = {l.value for l in report.attained_levels}
            if declared != recomputed:
                raise ScientificValidationError(
                    f"serialized attained_levels {sorted(declared)} do not match "
                    f"the levels established by its checks {sorted(recomputed)}"
                )
        if "status" in payload and payload.get("status") != report.status.value:
            raise ScientificValidationError(
                f"serialized status {payload.get('status')!r} does not match the "
                f"status its checks produce ({report.status.value!r})"
            )
        return report


def _legacy_status(checks) -> ValidationOutcome:
    """The pre-CORE-013 precedence: FAIL > WARNING > PASS > NOT_RUN, and an empty report is NOT_RUN.

    Kept as executable code rather than as a sentence in a changelog, because it is what a stored
    `validation_report/1` status MEANS: a record is honest if it says what its writer's rule said, and the
    version names the writer's rule. Nothing in the current tree computes a status this way.
    """
    outcomes = {ValidationOutcome(c.outcome) for c in checks}
    if ValidationOutcome.FAIL in outcomes:
        return ValidationOutcome.FAIL
    if ValidationOutcome.WARNING in outcomes:
        return ValidationOutcome.WARNING
    if ValidationOutcome.PASS in outcomes:
        return ValidationOutcome.PASS
    return ValidationOutcome.NOT_RUN


def _legacy_status_read(payload: Mapping[str, Any], report: "ValidationReport") -> Mapping[str, Any]:
    """A `/1` payload, with its stored status resolved against the precedence it was written under (R-45).

    Three cases. It agrees with the CURRENT rule: nothing to do, and the comparison below will pass. It
    agrees with the precedence its own version names: the record is accepted and the status DROPPED, so the
    reader reports what the current rule gives -- the stored word is explained, not believed. It agrees with
    neither: refused, and the message says that two precedences exist and this is neither, rather than
    reporting a contradiction whose cause it knows.
    """
    if "status" not in payload:
        return payload
    stored = payload.get("status")
    if stored == report.status.value:
        return payload
    legacy = _legacy_status(report.checks).value
    if stored == legacy:
        kept = dict(payload)
        kept.pop("status")
        return kept
    raise ScientificValidationError(
        f"serialized status {stored!r} in a {LEGACY_REPORT_SCHEMA} record is neither of the two precedences "
        f"this reader knows: the precedence that version was written under gives {legacy!r}, and the current "
        f"one gives {report.status.value!r}. A record whose status matches no rule that ever computed one "
        f"cannot be read as the report it claims to be"
    )


def unverified_report(reason: str = "no validation performed") -> ValidationReport:
    """An explicit 'nothing was checked' report — better than an empty one."""
    return ValidationReport(
        checks=(
            ValidationCheck(
                name="validation_performed",
                outcome=ValidationOutcome.NOT_RUN,
                detail=reason,
            ),
        )
    )
