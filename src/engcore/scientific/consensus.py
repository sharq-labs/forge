"""Agreement between several solve routes, and when it is evidence.

Two solvers producing the same number is the most persuasive-looking artefact
in computational science and the easiest one to manufacture. Run the same
right-hand side through two integrators and they will agree to twelve digits
about a right-hand side that is wrong. The agreement is real; what it is
evidence *of* is the shared arithmetic, not the physics.

So this module separates the two questions a consensus asks, and refuses to
let the second answer the first:

===============================  ==============================================
did the routes agree             a comparison, always performed and always
                                 reported, whatever it finds
were the routes independent      a **declaration**, made by whoever wrote the
                                 routes, never inferred from anything
===============================  ==============================================

``CROSS_SOLVER_VALIDATED`` is awarded only when both are true. Agreement
between routes that share their machinery is recorded in full — every residual,
every route, the tolerance it was judged against — and establishes nothing.

Independence is declared, never inferred
----------------------------------------
There is no analysis here that looks at two routes and decides whether they are
independent, and there will not be one. A wrong answer in that direction awards
a level nobody earned, and the wrongness is invisible: the report reads exactly
the same as one that earned it. Detection would have to be right about every
future pair of routes on the strength of an argument written before they
existed.

Instead each route declares the components it is *made of* —
:class:`SharedComponent` records naming a residual, a Jacobian, a
discretisation, a library, a linear-algebra kernel. Two routes share whatever
their declarations have in common, and that is a set intersection rather than a
judgement. A component appearing in more than one route defeats independence
for the whole consensus, and the refusal names the components by kind and by
name so a reader can see exactly what was shared.

**The default is not independent.** A route that declares no components earns
nothing, because an empty declaration intersects with everything to nothing and
would otherwise be the cheapest possible route to a level: say nothing about
what you are made of and the arithmetic says you are independent. Silence is
the one input this module reads as a refusal rather than as a permission.

What a declaration is about, and what it is not about
-----------------------------------------------------
A component is a thing that *produces or determines a number*. Two routes
solving the same problem necessarily share the problem — that is what makes
them comparable, and it is not a shared component. Two routes may also realize
the same mathematical formulation and still be independent, provided each one
implements it separately: a mistake in one implementation is then visible to
the other, which is the entire operational content of the word. What defeats
independence is shared *arithmetic* — the same function evaluated, the same
matrix factored, the same step accepted.

The grain of a declaration is therefore the grain at which arithmetic is
actually shared, and it is the declarer's to choose. Two routes that both reach
for one large numerical library share that library's name and nothing else if
one calls its integrator and the other its root finder; declaring the package
would say they share arithmetic they do not share, and would withhold a level
that was earned. Declaring a function they genuinely both call says the truth.
Both errors are possible and neither is detectable from here, which is why the
declaration travels in the record: a reader who disagrees with it can see it
and say so.

What this module does not do
-----------------------------
It does not run anything. Routes are executed by whoever owns them; this
records what they were and what their answers did. It knows no domain, no
backend and no concrete solver — only :class:`SolverIdentity`, which every
route already carries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .errors import ScientificValidationError
from .results.thresholds import VerificationThresholds
from .results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from .serialization import require_schema, schema_string
from .solvers.protocol import SolverIdentity

SHARED_COMPONENT_SCHEMA = schema_string("shared_component")
SOLVE_ROUTE_SCHEMA = schema_string("solve_route")
CONSENSUS_SCHEMA = schema_string("cross_solver_consensus")

__all__ = [
    "CONSENSUS_SCHEMA",
    "SHARED_COMPONENT_SCHEMA",
    "SOLVE_ROUTE_SCHEMA",
    "ComponentKind",
    "CrossSolverConsensus",
    "IndependenceVerdict",
    "RouteComparison",
    "SharedComponent",
    "SolveRoute",
    "relative_difference",
]


class ComponentKind(str, Enum):
    """What sort of thing a declared component is.

    The vocabulary is a reader's aid, not a rule: nothing here treats one kind
    as more disqualifying than another, because a shared anything is shared
    arithmetic, and an argument for ranking the kinds would have to be made per
    pair of routes rather than once here. The kind exists so that a refusal
    reads "these two share a Jacobian" rather than "these two share
    ``domain.thing:f``".

    ``OTHER`` is deliberately present. A route made of something this list does
    not name must still be able to say so, and an incomplete vocabulary that
    forces a declarer to pick the nearest wrong kind is worse than one that
    admits its own edge.
    """

    FORMULATION = "formulation"
    DISCRETISATION = "discretisation"
    RESIDUAL = "residual"
    JACOBIAN = "jacobian"
    STEP_CONTROL = "step_control"
    LINEAR_ALGEBRA = "linear_algebra"
    ROOT_FINDER = "root_finder"
    LIBRARY = "library"
    IMPLEMENTATION = "implementation"
    RUNTIME = "runtime"
    OTHER = "other"


@dataclass(frozen=True)
class SharedComponent:
    """One named ingredient of a solve route.

    Identity is ``(kind, name)`` and nothing else. ``detail`` is prose for a
    reader and is **excluded from equality**, deliberately: two routes that
    declare the same component and describe it in different words share it, and
    a comparison that let the prose decide would report an independence that
    came from an editorial difference. That is the failure mode this whole
    module exists to refuse, appearing one level down.
    """

    kind: ComponentKind
    name: str
    detail: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ComponentKind(self.kind))
        text = str(self.name).strip()
        if not text:
            raise ScientificValidationError(
                "a shared component requires a non-empty name; an unnamed "
                "component cannot be compared against another route's "
                "declaration and so could never be found to be shared"
            )
        object.__setattr__(self, "name", text)
        object.__setattr__(self, "detail", str(self.detail))

    @property
    def label(self) -> str:
        return f"{self.kind.value}:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SHARED_COMPONENT_SCHEMA,
            "kind": self.kind.value,
            "name": self.name,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SharedComponent":
        require_schema(payload, SHARED_COMPONENT_SCHEMA)
        return cls(
            kind=ComponentKind(payload["kind"]),
            name=payload["name"],
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class SolveRoute:
    """One way of getting an answer, and what it is made of.

    ``route_id`` names the route rather than the solver, because two routes can
    carry one solver identity and differ in the thing that matters — the same
    integrator asked for two different methods is two routes, one identity. The
    route id is what a comparison and a refusal name.
    """

    route_id: str
    solver: SolverIdentity
    components: frozenset[SharedComponent] = frozenset()
    notes: str = ""

    def __post_init__(self) -> None:
        text = str(self.route_id).strip()
        if not text:
            raise ScientificValidationError("a solve route requires a route_id")
        object.__setattr__(self, "route_id", text)
        if not isinstance(self.solver, SolverIdentity):
            raise ScientificValidationError(
                f"solve route {text!r} must carry a SolverIdentity, got "
                f"{type(self.solver).__name__}"
            )
        object.__setattr__(self, "components", frozenset(self.components))
        object.__setattr__(self, "notes", str(self.notes))

    @property
    def declares_nothing(self) -> bool:
        """Did this route say what it is made of?

        A route that did not cannot contribute to an independence claim. See
        the module docstring: an empty declaration would otherwise be the
        cheapest route to a level in the whole platform.
        """
        return not self.components

    @property
    def component_labels(self) -> tuple[str, ...]:
        return tuple(sorted(c.label for c in self.components))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOLVE_ROUTE_SCHEMA,
            "route_id": self.route_id,
            "solver": self.solver.to_dict(),
            "components": [
                c.to_dict()
                for c in sorted(self.components, key=lambda c: c.label)
            ],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolveRoute":
        require_schema(payload, SOLVE_ROUTE_SCHEMA)
        return cls(
            route_id=payload["route_id"],
            solver=SolverIdentity.from_dict(payload["solver"]),
            components=frozenset(
                SharedComponent.from_dict(c)
                for c in payload.get("components", ())
            ),
            notes=payload.get("notes", ""),
        )


class IndependenceVerdict(str, Enum):
    """Whether the declarations support an independence claim, and why not.

    Four members rather than a boolean, because "not independent" has three
    causes a reader must be able to tell apart: routes that declared shared
    machinery, routes that declared nothing at all, and a comparison that never
    had two routes to compare.
    """

    INDEPENDENT = "independent"
    SHARES_COMPONENTS = "shares_components"
    UNDECLARED = "undeclared"
    TOO_FEW_ROUTES = "too_few_routes"


def relative_difference(a: float, b: float) -> float:
    """``|a - b| / max(|a|, |b|, tiny)``.

    Symmetric, so neither route is the reference. The floor keeps a comparison
    of two zeros from dividing by zero, and is small enough that it never
    softens a real difference.
    """
    scale = max(abs(b), abs(a), 1e-300)
    return abs(a - b) / scale


@dataclass(frozen=True)
class RouteComparison:
    """What the routes' answers did, before anybody asks what it means.

    ``worst_relative_difference`` is ``None`` when there was nothing to
    compare — no common quantity, or a route that did not finish. That is not
    agreement, and :attr:`agreed` says so.
    """

    quantities: tuple[str, ...]
    worst_quantity: str
    worst_relative_difference: float | None
    tolerance: float
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantities", tuple(self.quantities))
        object.__setattr__(self, "worst_quantity", str(self.worst_quantity))
        tolerance = float(self.tolerance)
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise ScientificValidationError(
                f"consensus tolerance must be finite and non-negative, got "
                f"{self.tolerance!r}; a non-finite bound makes every "
                f"comparison against it unconditionally true or false"
            )
        object.__setattr__(self, "tolerance", tolerance)
        if self.worst_relative_difference is not None:
            worst = float(self.worst_relative_difference)
            if not math.isfinite(worst):
                raise ScientificValidationError(
                    f"consensus comparison reports a non-finite worst "
                    f"difference {self.worst_relative_difference!r}; a NaN "
                    f"satisfies every tolerance written against it, so it "
                    f"cannot be admitted and then compared. Routes that "
                    f"produced one agreed about nothing, and the honest "
                    f"record is no comparison at all"
                )
            object.__setattr__(self, "worst_relative_difference", worst)
        object.__setattr__(self, "detail", str(self.detail))

    @property
    def compared_anything(self) -> bool:
        return self.worst_relative_difference is not None

    @property
    def agreed(self) -> bool:
        """Nothing compared is not agreement."""
        if self.worst_relative_difference is None:
            return False
        return self.worst_relative_difference <= self.tolerance

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantities": list(self.quantities),
            "worst_quantity": self.worst_quantity,
            "worst_relative_difference": self.worst_relative_difference,
            "tolerance": self.tolerance,
            "agreed": self.agreed,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteComparison":
        return cls(
            quantities=tuple(payload.get("quantities", ())),
            worst_quantity=payload.get("worst_quantity", ""),
            worst_relative_difference=payload.get("worst_relative_difference"),
            tolerance=payload["tolerance"],
            detail=payload.get("detail", ""),
        )


def _compare(
    values: Mapping[str, Mapping[str, float]], tolerance: float
) -> RouteComparison:
    """The worst relative difference over every quantity every route produced.

    Only quantities **all** routes report are compared. A quantity one route
    produced and another did not is not a disagreement; it is an absence, and
    scoring it as either would be inventing a comparison nobody made. Which
    quantities were compared travels in the record, so an absence shows up as a
    shorter list rather than as a silently smaller worst case.
    """
    if len(values) < 2:
        return RouteComparison(
            quantities=(),
            worst_quantity="",
            worst_relative_difference=None,
            tolerance=tolerance,
            detail=(
                "fewer than two routes reported values; nothing was compared"
            ),
        )
    common: set[str] | None = None
    for produced in values.values():
        names = set(produced)
        common = names if common is None else (common & names)
    shared = sorted(common or ())
    if not shared:
        return RouteComparison(
            quantities=(),
            worst_quantity="",
            worst_relative_difference=None,
            tolerance=tolerance,
            detail=(
                "the routes report no quantity in common, so there is nothing "
                "to compare; this is an absence of evidence, not agreement"
            ),
        )

    # FINITENESS FIRST, BEFORE ANY COMPARISON.
    #
    # `relative_difference` returns NaN for every non-finite pairing --
    # `abs(nan - x)` is NaN, `abs(inf - inf)` is NaN, and `inf / inf` is NaN --
    # and the accumulator below advances on `difference > worst`, which is
    # False for NaN. So a non-finite reading was not merely mishandled: it was
    # SKIPPED, `worst` stayed at its initial 0.0, and the routes were recorded
    # as agreeing exactly. Two routes that both diverged to infinity, or one
    # that returned NaN against a finite partner, earned CROSS_SOLVER_VALIDATED
    # on a worst difference of zero.
    #
    # This is the same hole `solvers.admission` closes one layer out, in the
    # same direction and for the same reason: a comparison cannot detect the
    # values that defeat comparison, so the check has to run before it rather
    # than inside it.
    #
    # The refusal covers EVERY reading a route supplied, not only the shared
    # ones. A route that produced a NaN anywhere did not finish; admitting its
    # other numbers as an independent confirmation would credit a run that
    # failed with corroborating one that did not.
    offenders = sorted(
        f"{route_id}.{name}={value!r}"
        for route_id, produced in values.items()
        for name, value in produced.items()
        if not math.isfinite(float(value))
    )
    if offenders:
        return RouteComparison(
            quantities=(),
            worst_quantity="",
            worst_relative_difference=None,
            tolerance=tolerance,
            detail=(
                f"non-finite value(s) {offenders} were reported, so no "
                f"comparison was made. A NaN or an infinity satisfies every "
                f"tolerance written against it and is skipped by the worst-case "
                f"accumulator, which would record the routes as agreeing "
                f"exactly. A route that produced one did not finish, and an "
                f"unfinished route corroborates nothing"
            ),
        )
    worst = 0.0
    worst_name = shared[0]
    for name in shared:
        readings = [float(produced[name]) for produced in values.values()]
        for index, first in enumerate(readings):
            for second in readings[index + 1 :]:
                difference = relative_difference(first, second)
                if difference > worst:
                    worst = difference
                    worst_name = name
    plural = "y" if len(shared) == 1 else "ies"
    return RouteComparison(
        quantities=tuple(shared),
        worst_quantity=worst_name,
        worst_relative_difference=worst,
        tolerance=tolerance,
        detail=(
            f"{len(shared)} quantit{plural} compared across {len(values)} "
            f"routes; worst pairwise relative difference {worst:.3e} on "
            f"{worst_name!r}"
        ),
    )


@dataclass(frozen=True)
class CrossSolverConsensus:
    """Several routes on one problem, what they did, and what it establishes.

    The record is complete whatever it concludes. A consensus that refuses a
    level still carries every route, every declared component, the quantities
    compared and the worst difference found — because a reader who disagrees
    with the refusal needs the same material as one who accepts it, and because
    a refusal that hid its evidence would be as unfalsifiable as an unearned
    claim.
    """

    consensus_id: str
    routes: tuple[SolveRoute, ...]
    comparison: RouteComparison
    thresholds: VerificationThresholds
    notes: str = ""

    def __post_init__(self) -> None:
        text = str(self.consensus_id).strip()
        if not text:
            raise ScientificValidationError(
                "a consensus requires a consensus_id"
            )
        object.__setattr__(self, "consensus_id", text)
        routes = tuple(self.routes)
        identifiers = [r.route_id for r in routes]
        duplicates = sorted({r for r in identifiers if identifiers.count(r) > 1})
        if duplicates:
            raise ScientificValidationError(
                f"consensus {text!r} declares duplicate route ids "
                f"{duplicates}; two routes under one name cannot be told apart "
                f"in a comparison or named in a refusal"
            )
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "notes", str(self.notes))

    # ---- the declaration side -------------------------------------------
    @property
    def shared_components(self) -> tuple[SharedComponent, ...]:
        """Every component more than one route declared.

        A set intersection over declarations, not an analysis of anything. This
        is the whole of what "not independent" means here.
        """
        counted: dict[SharedComponent, int] = {}
        for route in self.routes:
            for component in route.components:
                counted[component] = counted.get(component, 0) + 1
        return tuple(
            sorted(
                (c for c, n in counted.items() if n > 1),
                key=lambda c: c.label,
            )
        )

    @property
    def undeclared_routes(self) -> tuple[str, ...]:
        return tuple(r.route_id for r in self.routes if r.declares_nothing)

    @property
    def independence(self) -> IndependenceVerdict:
        """Do the declarations support an independence claim?

        The order of the tests is the order a reader needs them in. Too few
        routes is not a shared-component problem and saying so would mislead; a
        route that declared nothing is reported as such rather than as
        independent, which is what the empty intersection would otherwise make
        it.
        """
        if len(self.routes) < 2:
            return IndependenceVerdict.TOO_FEW_ROUTES
        if self.undeclared_routes:
            return IndependenceVerdict.UNDECLARED
        if self.shared_components:
            return IndependenceVerdict.SHARES_COMPONENTS
        return IndependenceVerdict.INDEPENDENT

    @property
    def routes_are_independent(self) -> bool:
        return self.independence is IndependenceVerdict.INDEPENDENT

    # ---- what it establishes --------------------------------------------
    @property
    def earned(self) -> bool:
        """Independent routes **and** agreement inside the stated tolerance."""
        return self.routes_are_independent and self.comparison.agreed

    @property
    def establishes(self) -> ValidationLevel | None:
        """``CROSS_SOLVER_VALIDATED``, or nothing.

        Routed through :meth:`VerificationThresholds.award`, so a caller who
        widened the tolerance gets the whole comparison and no claim — the same
        rule every other gate in this platform obeys, for the same reason.
        """
        return self.thresholds.award(
            ValidationLevel.CROSS_SOLVER_VALIDATED, earned=self.earned
        )

    @property
    def reason(self) -> str:
        """Why the level was or was not awarded, in one sentence."""
        independence = self.independence
        if independence is IndependenceVerdict.TOO_FEW_ROUTES:
            return (
                f"{len(self.routes)} route(s) declared; a consensus needs at "
                f"least two to compare"
            )
        if independence is IndependenceVerdict.UNDECLARED:
            return (
                f"route(s) {list(self.undeclared_routes)} declare no "
                f"components, so no independence claim is available: a route "
                f"that does not say what it is made of earns nothing"
            )
        if independence is IndependenceVerdict.SHARES_COMPONENTS:
            shared = [c.label for c in self.shared_components]
            return (
                f"the routes share {shared}, so agreement between them is "
                f"evidence about the shared machinery and not about the "
                f"physics; the comparison is reported and establishes no level"
            )
        if not self.comparison.compared_anything:
            return (
                f"the routes are independent but nothing was compared "
                f"({self.comparison.detail}); an absence of comparison is not "
                f"agreement"
            )
        if not self.comparison.agreed:
            return (
                f"the routes are independent and disagree: worst relative "
                f"difference {self.comparison.worst_relative_difference:.3e} "
                f"on {self.comparison.worst_quantity!r} exceeds the declared "
                f"{self.comparison.tolerance:.3e}"
            )
        if self.establishes is None:
            return (
                f"the independent routes agree to "
                f"{self.comparison.worst_relative_difference:.3e}, but the "
                f"level is withheld because {self.thresholds.identity} is not "
                f"this gate's declared threshold set"
            )
        return (
            f"{len(self.routes)} routes sharing no declared component agree on "
            f"{len(self.comparison.quantities)} quantities to "
            f"{self.comparison.worst_relative_difference:.3e}, within the "
            f"declared {self.comparison.tolerance:.3e}"
        )

    # ---- expression in the universal vocabulary --------------------------
    def to_check(
        self, *, name: str = "cross_solver_agreement"
    ) -> ValidationCheck:
        """This consensus as one validation check.

        The outcome is about the *comparison* and the level is about the
        *declaration*, and they are allowed to disagree: routes that agree
        while sharing a Jacobian produce a PASS that establishes nothing, which
        is precisely the sentence the platform previously had no way to write.

        A disagreement between independent routes is a FAIL — two independent
        routes that differ have found something. A disagreement between routes
        that share their machinery is a WARNING: a real finding about the
        implementation, but calling it a scientific failure would hand the
        comparison an authority this same record has just denied it.
        """
        comparison = self.comparison
        if not comparison.compared_anything:
            outcome = ValidationOutcome.NOT_RUN
        elif comparison.agreed:
            outcome = ValidationOutcome.PASS
        elif self.routes_are_independent:
            outcome = ValidationOutcome.FAIL
        else:
            outcome = ValidationOutcome.WARNING
        return ValidationCheck(
            name=name,
            outcome=outcome,
            detail=f"{comparison.detail}. {self.reason}",
            establishes=self.establishes,
            residual=comparison.worst_relative_difference,
            tolerance=comparison.tolerance,
            evidence=self.evidence(),
        )

    def evidence(self) -> tuple[str, ...]:
        """What a reader would have to go and check to dispute this.

        Every route with its solver identity and its declared components, then
        the threshold set. A route's declaration is the load-bearing claim in
        the whole record, so it travels with the check rather than only in a
        consensus object that a stored result may not carry.
        """
        lines = []
        for route in sorted(self.routes, key=lambda r: r.route_id):
            declared = ", ".join(route.component_labels) or "nothing declared"
            lines.append(
                f"route {route.route_id} = {route.solver.solver_id}@"
                f"{route.solver.version} declares [{declared}]"
            )
        return (*lines, *self.thresholds.evidence())

    # ---- construction ----------------------------------------------------
    @classmethod
    def over(
        cls,
        *,
        consensus_id: str,
        routes: Iterable[SolveRoute],
        values: Mapping[str, Mapping[str, float]],
        thresholds: VerificationThresholds,
        tolerance_key: str,
        notes: str = "",
    ) -> "CrossSolverConsensus":
        """Compare what each route produced, keyed by ``route_id``.

        Every key in ``values`` must name a declared route. A reading from a
        route nobody declared has no declaration behind it, and would be
        compared with nothing known about where it came from — which is the one
        thing this record exists to prevent.
        """
        routes = tuple(routes)
        known = {r.route_id for r in routes}
        unknown = sorted(set(values) - known)
        if unknown:
            raise ScientificValidationError(
                f"consensus {consensus_id!r} was handed values for undeclared "
                f"route(s) {unknown}; a reading with no route behind it cannot "
                f"be attributed and so cannot contribute to an independence "
                f"claim. Declared routes: {sorted(known)}"
            )
        return cls(
            consensus_id=consensus_id,
            routes=routes,
            comparison=_compare(values, thresholds[tolerance_key]),
            thresholds=thresholds,
            notes=notes,
        )

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSENSUS_SCHEMA,
            "consensus_id": self.consensus_id,
            "routes": [r.to_dict() for r in self.routes],
            "comparison": self.comparison.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "notes": self.notes,
            # Derived, emitted for readers, and recomputed on the way back in.
            "independence": self.independence.value,
            "shared_components": [c.label for c in self.shared_components],
            "establishes": (
                self.establishes.value if self.establishes else None
            ),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CrossSolverConsensus":
        require_schema(payload, CONSENSUS_SCHEMA)
        record = cls(
            consensus_id=payload["consensus_id"],
            routes=tuple(
                SolveRoute.from_dict(r) for r in payload.get("routes", ())
            ),
            comparison=RouteComparison.from_dict(payload["comparison"]),
            thresholds=VerificationThresholds.from_dict(payload["thresholds"]),
            notes=payload.get("notes", ""),
        )
        # The same rule ValidationReport.from_dict applies to attained levels:
        # a derived field in a payload is advisory, and a hand-edited record
        # may not smuggle in a level its own contents do not produce.
        declared = payload.get("establishes")
        actual = record.establishes.value if record.establishes else None
        if declared != actual:
            raise ScientificValidationError(
                f"serialized consensus {record.consensus_id!r} claims to "
                f"establish {declared!r}, but its routes and comparison "
                f"establish {actual!r}; a consensus may report a level but may "
                f"not assert one"
            )
        return record
