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
were the routes independent      a **declaration** the domain layer pins and
                                 the core verifies; never a caller's labels
did each route answer the        a **declaration** too: the required outputs,
whole question                   named up front and checked against what each
                                 route actually reported
===============================  ==============================================

``CROSS_SOLVER_VALIDATED`` is awarded only when all three are true. Agreement
between routes that share their machinery is recorded in full — every residual,
every route, the tolerance it was judged against — and establishes nothing. So
is agreement between routes that answered different fractions of the question.

Completeness is declared for the same reason independence is
------------------------------------------------------------
The comparison used to run over the INTERSECTION of what the routes reported.
A route producing three quantities and a route producing one were compared on
the one they shared, and agreement there earned the level for the whole
consensus. The record was honest about which quantities it compared; nothing
said which ones it *should* have, so nothing could tell a complete confirmation
from a partial one — and the partial one is the cheaper to produce.

So a consensus names its ``required_outputs``, and an empty set is a refusal
rather than a wildcard, exactly as an empty component declaration is. Extra
quantities the routes happen to share are compared too, which can only make
agreement harder to reach: two routes that agree on the contract and differ
wildly outside it have still found something, and hiding that to protect a
claim is the failure this module exists to refuse.

Independence is declared by the domain layer, and verified by the core
----------------------------------------------------------------------
There is no analysis here that looks at two routes and decides whether they are
independent, and there will not be one. A wrong answer in that direction awards
a level nobody earned, and the wrongness is invisible: the report reads exactly
the same as one that earned it.

Independence used to be read from :class:`SharedComponent` records attached to
each route by whoever built it: two routes shared whatever their labels had in
common, and nothing checked the labels against anything. One solver identity
under two route names and two labels, one function spelled two ways, one
numerical backend behind two wrappers -- and the DC domain's own entry point,
handed one result under one solver twice -- all earned
``CROSS_SOLVER_VALIDATED``. A label is data a caller supplies; authority is not.

So independence is read from :class:`RouteDependencies`: what a route is made
of, per :class:`IndependenceDimension` -- the problem declaration, the
preprocessing that builds the computed system from it, the numerical method,
the implementation and the backend -- in canonical identities
(:func:`canonical_component_identity`), so one function reached through two
import paths is one identity. A route's dependencies count only when they are
the declaration the domain layer pins for that route id, under
:data:`ROUTE_DECLARATIONS_ATTRIBUTE` in the domain package: the pin binds the
route id to the solver that must have run and to the SHA-256 of the canonical
dependencies. A route the core cannot verify earns nothing, whatever it says
about itself. Threshold authority follows the same rule: the data travels with
the record, and the core checks it against a pin the caller does not hold.

Independence has dimensions
---------------------------
Routes are **fully** independent when they share nothing in any dimension,
**partially** independent when they share something but not the
implementation, and **not** independent when they share the implementation.
``CROSS_SOLVER_VALIDATED`` requires independence in every one of
:data:`SOLVER_INDEPENDENCE_DIMENSIONS`: preprocessing, numerical method,
implementation and backend. The problem declaration is not among them -- two
solvers asked the same question necessarily share the question, and that is
what makes their answers comparable -- and it is still reported, as partial
independence, because an error in the declaration is invisible to every route
that reads it.

A route's descriptive ``components`` stay in the record in its author's words,
and :attr:`CrossSolverConsensus.shared_components` still reports their
intersection. Nothing decides on it.

**The default is not independent.** A route that declares no dependencies earns
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

What independence does NOT establish, stated so nobody has to discover it
-------------------------------------------------------------------------
A verified declaration is the domain layer's statement about its own routes,
checked for integrity and not against the world: a pin that declares two routes
disjoint when they are not is wrong in the pin, where a reviewer can read it.
And the core attributes numbers to routes as they are handed over. A domain
entry point is where a result's provenance can be checked against the route it
is presented under, and the DC domain does so.

What this module does not do
-----------------------------
It does not run anything. Routes are executed by whoever owns them; this
records what they were and what their answers did. It knows no domain, no
backend and no concrete solver — only :class:`SolverIdentity`, which every
route already carries.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from collections.abc import Mapping as _RuntimeMapping
from typing import Any, Iterable, Mapping
#: ``typing.Mapping`` and ``collections.abc.Mapping`` are the SAME CLASS
#: (``typing.Mapping.__origin__`` IS that class), but an ``isinstance``
#: against the typing alias routes through ``typing.__subclasscheck__`` and
#: measures 2.56x slower here. Annotations keep ``Mapping``; runtime checks
#: use ``_RuntimeMapping``. Same check, same answer, same refusals.


from .errors import ScientificValidationError
from .results.thresholds import VerificationThresholds
from .results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from .results.immutable import freeze
from .serialization import (
    require_schema,
    require_schema_any,
    schema_string,
)
from .sequences import duplicates as duplicate_entries
from .solvers.protocol import SolverIdentity
from .units.quantity import base_unit, is_ratio_scale

SHARED_COMPONENT_SCHEMA = schema_string("shared_component")
SOLVE_ROUTE_SCHEMA = schema_string("solve_route")
ROUTE_DEPENDENCIES_SCHEMA = schema_string("route_dependencies")

#: The attribute the domain layer pins route declarations under, and the package
#: it is read from. Read by name, as threshold authority is: the core knows where
#: declarations are pinned and never what any of them says.
ROUTE_DECLARATIONS_ATTRIBUTE = "SCIENTIFIC_ROUTE_DECLARATIONS"
_DECLARING_PACKAGE = f"{__name__.split('.')[0]}.domains"

#: Bumped for ``reported_values`` and ``tolerance_key``. A /2 record carries a
#: comparison's conclusion -- the worst difference and the tolerance it met --
#: but neither the numbers it was computed from nor the threshold that
#: tolerance was read from, so its constructor could not tell a comparison from
#: a claim of one: a stated worst difference of 0.0 for routes 23 % apart, or a
#: tolerance of 1.0 under a declared set whose number is 1e-9, established the
#: level. ``from_dict`` reads /2 only where it claims no level.
#:
#: /2 was the bump for ``required_outputs``. A /1 record has no field naming the
#: quantities the routes were obliged to produce, so a level it claims was
#: awarded under a rule that could not tell a complete confirmation from a
#: partial one. The missing declaration cannot be defaulted -- an empty set
#: means "nothing was required", which is precisely the state this version
#: refuses to award on -- so ``from_dict`` accepts /1 only where it claims no
#: level. Same shape, and same reason, as ``validity_assessment/1``.
CONSENSUS_SCHEMA = schema_string("cross_solver_consensus", 3)
CONSENSUS_SCHEMA_V2 = schema_string("cross_solver_consensus", 2)
CONSENSUS_SCHEMA_V1 = schema_string("cross_solver_consensus", 1)

__all__ = [
    "CONSENSUS_SCHEMA",
    "CONSENSUS_SCHEMA_V1",
    "CONSENSUS_SCHEMA_V2",
    "ROUTE_DECLARATIONS_ATTRIBUTE",
    "ROUTE_DEPENDENCIES_SCHEMA",
    "SHARED_COMPONENT_SCHEMA",
    "SOLVER_INDEPENDENCE_DIMENSIONS",
    "SOLVE_ROUTE_SCHEMA",
    "ComponentKind",
    "CrossSolverConsensus",
    "IndependenceDimension",
    "IndependenceVerdict",
    "OutputCompleteness",
    "RouteComparison",
    "RouteDependencies",
    "SharedComponent",
    "SolveRoute",
    "canonical_component_identity",
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


class IndependenceDimension(str, Enum):
    """A respect in which two routes can share, or not share, their arithmetic.

    Kept apart rather than collapsed into one boolean, because the answer differs
    by dimension and a reader needs to see which: two different solvers on one
    problem declaration are independent in how they compute and not in what they
    were told.
    """

    PROBLEM_DECLARATION = "problem_declaration"
    PREPROCESSING = "preprocessing"
    NUMERICAL_METHOD = "numerical_method"
    IMPLEMENTATION = "implementation"
    BACKEND = "backend"


#: The dimensions ``CROSS_SOLVER_VALIDATED`` requires routes to be independent in.
#: The problem declaration is not one of them: every cross-solver comparison asks
#: two solvers one question, and a shared declaration is what makes the answers
#: comparable. It is still reported, as partial independence.
SOLVER_INDEPENDENCE_DIMENSIONS = (
    IndependenceDimension.PREPROCESSING,
    IndependenceDimension.NUMERICAL_METHOD,
    IndependenceDimension.IMPLEMENTATION,
    IndependenceDimension.BACKEND,
)


@lru_cache(maxsize=1024)
def canonical_component_identity(declared: str) -> str:
    """The canonical spelling of one dependency identity.

    ``py:<module>:<qualname>`` is resolved to the object it names and respelled
    as that object's defining module and qualified name, so one function reached
    through a re-export, an alias or a package path is one identity.
    ``ext:<name>`` names something outside the interpreter -- an external
    program, a native library routine -- and is normalised, not resolved.
    Anything else is refused: an identity with no way to canonicalise it is a
    name, and a name is what independence is no longer read from.
    """
    text = str(declared).strip()
    scheme, _, rest = text.partition(":")
    if scheme == "py":
        module_name, _, qualname = rest.partition(":")
        module_name, qualname = module_name.strip(), qualname.strip()
        if not module_name or not qualname:
            raise ScientificValidationError(
                f"component identity {text!r} must read 'py:<module>:<qualname>'"
            )
        try:
            target: Any = importlib.import_module(module_name)
        except ImportError as exc:
            raise ScientificValidationError(
                f"component identity {text!r} names module {module_name!r}, which "
                f"cannot be imported"
            ) from exc
        for part in qualname.split("."):
            try:
                target = getattr(target, part)
            except AttributeError:
                raise ScientificValidationError(
                    f"component identity {text!r} names {qualname!r}, which "
                    f"{module_name!r} does not define"
                ) from None
        module = getattr(target, "__module__", None)
        name = getattr(target, "__qualname__", None)
        if not isinstance(module, str) or not isinstance(name, str):
            raise ScientificValidationError(
                f"component identity {text!r} resolves to an object with no "
                f"defining module and qualified name"
            )
        return f"py:{module}:{name}"
    if scheme == "ext":
        name = " ".join(rest.split()).lower()
        if not name:
            raise ScientificValidationError(f"component identity {text!r} names nothing")
        return f"ext:{name}"
    raise ScientificValidationError(
        f"component identity {text!r} has no recognised scheme; a dependency is "
        f"named 'py:<module>:<qualname>', resolved to the object it names, or "
        f"'ext:<name>'"
    )


@dataclass(frozen=True)
class RouteDependencies:
    """What a route is made of, per :class:`IndependenceDimension`.

    Every dimension must name at least one identity. A dimension left out would
    intersect with everything to nothing and read as independent, which is the
    undeclared-route hole one level down. Identities are kept as declared and
    compared, and hashed, in canonical form.
    """

    identities: Mapping[IndependenceDimension, frozenset[str]]

    def __post_init__(self) -> None:
        normalised: dict[IndependenceDimension, frozenset[str]] = {}
        for key, names in dict(self.identities).items():
            try:
                dimension = IndependenceDimension(key)
            except ValueError:
                raise ScientificValidationError(
                    f"route dependencies name {key!r}, which is not an independence "
                    f"dimension; the dimensions are "
                    f"{[d.value for d in IndependenceDimension]}"
                ) from None
            if isinstance(names, str):
                raise ScientificValidationError(
                    f"route dependencies for {dimension.value!r} must be a collection "
                    f"of identities, not the single string {names!r}"
                )
            texts = frozenset(str(name).strip() for name in names)
            if not texts or "" in texts:
                raise ScientificValidationError(
                    f"route dependencies for {dimension.value!r} name no identity"
                )
            normalised[dimension] = texts
        missing = [d.value for d in IndependenceDimension if d not in normalised]
        if missing:
            raise ScientificValidationError(
                f"route dependencies declare no identity for {missing}; a dimension "
                f"a route does not declare cannot be compared, and would read as "
                f"independent"
            )
        object.__setattr__(
            self,
            "identities",
            freeze({d: normalised[d] for d in IndependenceDimension}),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RouteDependencies):
            return NotImplemented
        return dict(self.identities) == dict(other.identities)

    def __hash__(self) -> int:
        return hash(tuple((d.value, tuple(sorted(n))) for d, n in self.identities.items()))

    def canonical(self) -> dict[IndependenceDimension, frozenset[str]]:
        """Every identity in canonical form. Raises when one cannot be resolved."""
        return {
            dimension: frozenset(canonical_component_identity(name) for name in names)
            for dimension, names in self.identities.items()
        }

    @property
    def digest(self) -> str:
        """SHA-256 over the canonical identities -- the number a domain pins."""
        blob = json.dumps(
            {d.value: sorted(names) for d, names in self.canonical().items()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTE_DEPENDENCIES_SCHEMA,
            "identities": {d.value: sorted(names) for d, names in self.identities.items()},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteDependencies":
        require_schema(payload, ROUTE_DEPENDENCIES_SCHEMA)
        return cls(
            identities={
                key: frozenset(names)
                for key, names in dict(payload.get("identities") or {}).items()
            }
        )


def _route_declarations() -> Mapping[str, Any]:
    """The domain layer's pinned route declarations, or none if it states none."""
    try:
        package = importlib.import_module(_DECLARING_PACKAGE)
    except ImportError:  # pragma: no cover - an installation without its domains
        return {}
    table = getattr(package, ROUTE_DECLARATIONS_ATTRIBUTE, None)
    return table if isinstance(table, _RuntimeMapping) else {}


def _pinned_identities(pin: Mapping[str, Any]) -> dict[str, frozenset[str]] | None:
    """The identities a route pin lists, by dimension value, or ``None`` if it lists none."""
    table = pin.get("identities")
    if not isinstance(table, _RuntimeMapping) or not table:
        return None
    listed: dict[str, frozenset[str]] = {}
    for dimension, names in table.items():
        if isinstance(names, str):
            return None
        listed[str(getattr(dimension, "value", dimension))] = frozenset(
            str(name).strip() for name in names
        )
    return listed


def _verify_route(route: "SolveRoute") -> str | None:
    """``None`` when ``route`` is a declaration the domain layer pins; otherwise why not.

    Every step reads the pin and nothing the route asserts about itself:

    1. the route must declare dependencies at all;
    2. its route id must be one the domain layer declares;
    3. the solver that ran must be the implementation the declaration is for;
    4. its identities, as declared, must be the ones the pin lists -- compared
       before anything is resolved, so a record never chooses an import;
    5. its dependencies must resolve, and hash to the pinned digest.
    """
    if route.dependencies is None:
        return "declares no dependencies"
    pin = _route_declarations().get(route.route_id)
    if not isinstance(pin, _RuntimeMapping):
        return f"is not a route the domain layer declares"
    if route.solver.solver_id != pin.get("solver_id"):
        return (
            f"carries solver {route.solver.solver_id!r}, and the declaration of "
            f"{route.route_id!r} is for {pin.get('solver_id')!r}"
        )
    if "backend" in pin and route.solver.backend != pin["backend"]:
        return (
            f"carries backend {route.solver.backend!r}, and the declaration of "
            f"{route.route_id!r} is for {pin['backend']!r}"
        )
    # BEFORE ANY RESOLUTION (IND-05). Hashing canonicalises every `py:`
    # identity by importing the module it names, and this runs inside the
    # constructor -- so inside `from_dict`. A payload naming `py:this:s` as a
    # backend imported `this` on the reader before the digest could disagree
    # with anything: a record chose code to run. The identities a route
    # declares are compared, as declared, against the identities the pin lists,
    # and only a declaration the pin lists verbatim is ever resolved.
    listed = _pinned_identities(pin)
    if listed is None:
        return (
            "is declared by a pin that lists no identities, so its dependencies "
            "cannot be compared before they are resolved"
        )
    if {d.value: frozenset(n) for d, n in route.dependencies.identities.items()} != listed:
        return (
            f"declares dependency identities that are not the ones the domain "
            f"layer's pin for {route.route_id!r} lists; nothing was resolved"
        )
    try:
        digest = route.dependencies.digest
    except ScientificValidationError as exc:
        return f"declares a dependency that cannot be resolved ({exc})"
    if digest != pin.get("dependency_digest"):
        return (
            f"declares dependencies hashing to {digest[:12]}…, not the "
            f"{str(pin.get('dependency_digest'))[:12]}… the domain layer pins"
        )
    return None


def _threshold_authority_gap(
    routes: tuple["SolveRoute", ...],
    thresholds: VerificationThresholds,
    tolerance_key: str,
) -> str | None:
    """``None`` when every route's pin names the gate and key this comparison was judged under.

    A declared threshold set is declared FOR ONE GATE. ``award`` verifies that a
    set is some gate's own declaration and never asked whether it is the gate
    this comparison belongs to, so two routes 40 % apart judged against another
    domain's declared refinement contraction (1.5) earned
    ``CROSS_SOLVER_VALIDATED``. The comparison's gate and tolerance key are
    therefore part of what the domain layer pins for each route, beside the
    solver and the dependencies, and read from there: every route must name
    ``thresholds.gate_id`` and ``tolerance_key``. A pin that names neither,
    or routes whose pins name different gates, fail closed.
    """
    gaps: list[str] = []
    for route in routes:
        pin = _route_declarations().get(route.route_id)
        if not isinstance(pin, _RuntimeMapping):
            gaps.append(f"route {route.route_id!r} has no pinned declaration")
            continue
        gate = pin.get("threshold_gate_id")
        key = pin.get("tolerance_key")
        if not isinstance(gate, str) or not isinstance(key, str):
            gaps.append(
                f"the declaration of route {route.route_id!r} names no threshold "
                f"gate and tolerance key for its comparison"
            )
            continue
        if gate != thresholds.gate_id or key != tolerance_key:
            gaps.append(
                f"route {route.route_id!r} is declared for comparison under "
                f"{gate!r} at {key!r}, and this consensus reads "
                f"{thresholds.gate_id!r} at {tolerance_key!r}"
            )
    if not gaps:
        return None
    return "; ".join(gaps)


@dataclass(frozen=True)
class SolveRoute:
    """One way of getting an answer, and what it is made of.

    ``route_id`` names the route rather than the solver, because two routes can
    carry one solver identity and differ in the thing that matters — the same
    integrator asked for two different methods is two routes, one identity. The
    route id is what a comparison and a refusal name.

    ``components`` describe the route in its author's words and decide
    nothing. ``dependencies`` is what independence is read from, and only
    when it is the declaration the domain layer pins for ``route_id``.
    """

    route_id: str
    solver: SolverIdentity
    components: frozenset[SharedComponent] = frozenset()
    notes: str = ""
    dependencies: RouteDependencies | None = None

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
        if self.dependencies is not None and not isinstance(
            self.dependencies, RouteDependencies
        ):
            raise ScientificValidationError(
                f"solve route {text!r} carries a "
                f"{type(self.dependencies).__name__} as its dependencies, not "
                f"RouteDependencies"
            )

    @property
    def declares_nothing(self) -> bool:
        """Did this route declare what it is made of?

        A route without dependencies cannot contribute to an independence
        claim, whatever its descriptive components say. See the module
        docstring: an empty declaration would otherwise be the cheapest route to
        a level in the whole platform.
        """
        return self.dependencies is None

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
            "dependencies": (
                self.dependencies.to_dict() if self.dependencies is not None else None
            ),
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
            dependencies=(
                RouteDependencies.from_dict(payload["dependencies"])
                if payload.get("dependencies") is not None
                else None
            ),
        )


class IndependenceVerdict(str, Enum):
    """How independent the routes are, as their verified declarations show.

    ``FULLY_INDEPENDENT`` routes share nothing in any dimension;
    ``PARTIALLY_INDEPENDENT`` routes share something, but not the
    implementation; ``NOT_INDEPENDENT`` routes share the implementation. The
    other three say why no such statement is available: a route declared no
    dependencies, a route's declaration is not the one the domain layer pins,
    or there were not two routes to compare.
    """

    FULLY_INDEPENDENT = "fully_independent"
    PARTIALLY_INDEPENDENT = "partially_independent"
    NOT_INDEPENDENT = "not_independent"
    UNVERIFIED = "unverified"
    UNDECLARED = "undeclared"
    TOO_FEW_ROUTES = "too_few_routes"


class OutputCompleteness(str, Enum):
    """Did every route answer the whole question, or only part of it?

    The second question a consensus has to ask and previously did not.
    ``_compare`` took the INTERSECTION of what the routes reported, so a route
    that produced one quantity and a route that produced three were compared on
    the one they shared -- and agreement on that one earned
    ``CROSS_SOLVER_VALIDATED`` for the whole comparison. The record said which
    quantities were compared, honestly; nothing said which ones *should* have
    been, so nothing could tell a complete confirmation from a partial one.

    ``UNDECLARED`` is a refusal, exactly as it is for independence. An
    undeclared required set intersects with everything to nothing and would
    otherwise be the cheapest possible route to a level: say nothing about what
    the routes owed and the arithmetic says they delivered it.
    """

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNDECLARED = "undeclared"


def relative_difference(a: float, b: float) -> float:
    """``|a - b| / max(|a|, |b|, tiny)``.

    Symmetric, so neither route is the reference. The floor keeps a comparison
    of two zeros from dividing by zero, and is small enough that it never
    softens a real difference.
    """
    scale = max(abs(b), abs(a), 1e-300)
    return abs(a - b) / scale


#: How a threshold set declares an absolute floor for one kind of quantity:
#: ``<tolerance_key>.floor.<kind>``, where ``kind`` is the part of a quantity's
#: name before its first ``:`` (``flux`` for ``flux:inlet``). The floor is read in the CANONICAL unit of that
#: kind's dimension -- the coherent SI base unit the compared magnitudes are
#: expressed in (I-22, R-52; it used to be "the unit the routes report that kind
#: in", which was the unit of whichever route was declared first, so the same
#: 1e-15 was worth 1e-15 A in one order and 1e-9 A in the other). It is the
#: domain's declaration, travelling in the threshold set and in its digest -- so
#: a record recomputes the same comparison from itself.
_FLOOR_KEY_SEPARATOR = ".floor."


def _declared_floors(
    thresholds: VerificationThresholds, tolerance_key: str
) -> dict[str, float]:
    """The absolute floors ``thresholds`` declares for ``tolerance_key``, by quantity kind."""
    prefix = f"{tolerance_key}{_FLOOR_KEY_SEPARATOR}"
    return {
        name[len(prefix):]: float(value)
        for name, value in thresholds.values.items()
        if name.startswith(prefix) and len(name) > len(prefix)
    }


def _floored_difference(a: float, b: float, tolerance: float, floor: float) -> float:
    """The relative difference, with a declared absolute floor on its scale (NUM-03).

    ``relative_difference(1.2e-17, 0.0)`` is 1.0: two routes that agree on a
    bridge current to round-off were recorded as disagreeing completely,
    because a relative measure of two numbers near zero measures nothing but
    the noise. With a floor ``f`` declared for the quantity the scale becomes
    ``max(|a|, |b|, f / tolerance)``, so the comparison passes exactly when
    ``|a - b| <= max(tolerance * max(|a|, |b|), f)`` -- the familiar
    relative-plus-absolute rule, expressed so the record keeps one relative
    number judged against one tolerance. No floor declared, or a zero
    tolerance, and it is :func:`relative_difference` unchanged: never an
    undeclared number.
    """
    if floor <= 0.0 or tolerance <= 0.0:
        return relative_difference(a, b)
    scale = max(abs(a), abs(b), floor / tolerance)
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
    values: Mapping[str, Mapping[str, float]],
    tolerance: float,
    required: tuple[str, ...] = (),
    floors: Mapping[str, float] | None = None,
) -> RouteComparison:
    """The worst relative difference over the quantities that must agree.

    ``floors`` are the absolute floors the threshold set declares, by quantity
    kind (see :func:`_floored_difference`); a quantity with none is compared by
    :func:`relative_difference` exactly as before.

    **What is compared** is the declared ``required`` set together with every
    quantity all routes happen to report. The union, and each half earns its
    place:

    * the *required* half is the contract. It is checked for presence by
      :attr:`CrossSolverConsensus.missing_outputs`, so a route that skipped one
      cannot be compared into agreement on the rest.
    * the *common* half is every additional quantity the routes both produced.
      Including it means an extra output can only make agreement HARDER to
      reach, never easier -- two routes that agree on the contract and differ
      wildly on a quantity outside it have still found something, and a
      comparison that ignored it would be hiding a real disagreement to protect
      a claim.

    A quantity one route produced and another did not is still not a
    disagreement; it is an absence, and scoring it as either would invent a
    comparison nobody made. Which quantities were compared travels in the
    record, so an absence shows up as a shorter list rather than as a silently
    smaller worst case.
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
    # Only required names EVERY route actually reported can be compared; a
    # missing one is refused by `missing_outputs` rather than silently dropped
    # here, and including it in this list would index a value that is not there.
    present_everywhere = common or set()
    shared = sorted(present_everywhere | (set(required) & present_everywhere))
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
        f"{route_id}.{name}={produced[name]!r}"
        for route_id, produced in values.items()
        for name in shared
        if name in produced and not math.isfinite(float(produced[name]))
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
    declared_floors = dict(floors or {})
    floored: list[str] = []
    for name in shared:
        floor = declared_floors.get(name.partition(":")[0], 0.0)
        if floor > 0.0:
            floored.append(name)
        readings = [float(produced[name]) for produced in values.values()]
        for index, first in enumerate(readings):
            for second in readings[index + 1 :]:
                difference = _floored_difference(first, second, tolerance, floor)
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
            + (
                f"; {len(floored)} compared with the absolute floor the "
                f"threshold set declares for its kind"
                if floored
                else ""
            )
        ),
    )


#: Where a consensus built by :meth:`CrossSolverConsensus.from_results` keeps the
#: execution each route's numbers were read from. An attribute and not a
#: dataclass field ON PURPOSE: the field list of this record is frozen API, and
#: the binding is the one thing a level now needs that the frozen shape has no
#: place for. It is never an argument -- the constructor and ``over`` cannot set
#: it -- and it is written once, by ``from_results`` or by ``from_dict`` after
#: its structure is checked. See the FROZEN-API decision recorded for IND-02:
#: the next freeze should make it a real field.
_EXECUTION_BINDINGS = "_execution_bindings"

#: The evidence line a consensus check carries its exact threshold record under.
#: Read by ``results.validation`` when it re-verifies a check that declares
#: ``CROSS_SOLVER_VALIDATED`` (VAL-01). Not exported.
CONSENSUS_THRESHOLDS_EVIDENCE_PREFIX = "consensus-thresholds:"

#: R-21 (re-audit 2026-09-16, I-12 part B): the line every check carrying CROSS_SOLVER_VALIDATED must carry,
#: saying WHICH independence the level rests on. ``results.validation`` refuses the level without exactly
#: one of them (VAL-01's rule, extended). Two values and no others:
#:
#: * ``declared`` -- independence read from declarations the DOMAIN LAYER PINS and this module verifies
#:   against the pinned identities. A route nothing pins earns nothing at all, so this is not a caller's
#:   word; it is weaker than the bytes because it says the declarations agree, not that the two programs
#:   were read and found to share no code.
#: * ``artifact-verified`` -- the same declarations PLUS the bytes of the named artifacts, digested and
#:   compared. Written only by ``execution.consensus.TrustedConsensusGate`` when
#:   ``assess_independence_evidence`` reports ``strongly_independent``.
#:
#: The basis is ADDITIVE, which is what the improvement's brief asks for: removing the declared basis would
#: delete the only basis any route in this tree can currently reach and make the level unreachable rather
#: than better founded. What R-21 is about is that a reader could not tell the two apart.
INDEPENDENCE_BASIS_EVIDENCE_PREFIX = "independence basis:"
INDEPENDENCE_BASIS_DECLARED = "declared"
INDEPENDENCE_BASIS_ARTIFACT_VERIFIED = "artifact-verified"
INDEPENDENCE_BASES = (INDEPENDENCE_BASIS_DECLARED, INDEPENDENCE_BASIS_ARTIFACT_VERIFIED)


def _values_digest(produced: Mapping[str, float]) -> str:
    """SHA-256 over one route's numbers exactly as the record carries them."""
    blob = json.dumps(
        {str(name): float(value) for name, value in produced.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _checked_binding(route_id: str, entry: Any) -> dict[str, Any]:
    """One serialized execution binding, structurally checked, or a refusal."""
    if not isinstance(entry, _RuntimeMapping):
        raise ScientificValidationError(
            f"execution binding for route {route_id!r} is not a mapping"
        )
    solver = entry.get("solver")
    if not isinstance(solver, _RuntimeMapping):
        raise ScientificValidationError(
            f"execution binding for route {route_id!r} names no solver"
        )
    texts = {
        "result_id": entry.get("result_id"),
        "run_id": entry.get("run_id"),
        "values_digest": entry.get("values_digest"),
        "solver_id": solver.get("solver_id"),
        "version": solver.get("version"),
    }
    for label, text in texts.items():
        if not isinstance(text, str) or not text.strip():
            raise ScientificValidationError(
                f"execution binding for route {route_id!r} carries no {label}"
            )
    backend = solver.get("backend")
    if backend is not None and not isinstance(backend, str):
        raise ScientificValidationError(
            f"execution binding for route {route_id!r} carries a non-string backend"
        )
    return {
        "result_id": texts["result_id"],
        "run_id": texts["run_id"],
        "solver": {
            "solver_id": texts["solver_id"],
            "version": texts["version"],
            "backend": backend,
        },
        "values_digest": texts["values_digest"],
    }


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
    #: The quantities every route was obliged to produce for this consensus to
    #: mean anything. **Declared, never inferred** -- the same rule the
    #: components follow, for the same reason. Empty is a refusal, not a
    #: wildcard: see :class:`OutputCompleteness`.
    required_outputs: tuple[str, ...] = ()
    #: What each route actually reported, by route id. Kept so
    #: :attr:`missing_outputs` can name the route AND the quantity rather than
    #: only reporting that something was short. A declared route with no entry
    #: here reported nothing, and is charged for every required output: the
    #: absence of a report is not a report of everything. Empty for a /1
    #: payload, which also declares no required outputs and so claims nothing.
    reported_outputs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    notes: str = ""
    #: The key in ``thresholds`` the comparison's tolerance was read from.
    tolerance_key: str = ""
    #: The numbers each route reported, by route id: what the comparison was
    #: computed from. Kept so the comparison is RECOMPUTED at construction
    #: rather than believed -- a record that carries them has exactly the
    #: comparison they produce at the threshold set's own tolerance, or it is
    #: refused. A record without them can carry a comparison and cannot
    #: establish a level; see :attr:`comparison_is_derived`.
    reported_values: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    #: Each route's standing against the domain layer's pins, decided once at
    #: construction: ``None`` for a verified route, otherwise why not. Not an
    #: argument, and not read from a payload.
    _route_findings: Mapping[str, str | None] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        text = str(self.consensus_id).strip()
        if not text:
            raise ScientificValidationError(
                "a consensus requires a consensus_id"
            )
        object.__setattr__(self, "consensus_id", text)
        object.__setattr__(
            self, "required_outputs", tuple(sorted(set(self.required_outputs)))
        )
        object.__setattr__(
            self,
            "reported_outputs",
            freeze({
                str(route_id): tuple(sorted(set(names)))
                for route_id, names in dict(self.reported_outputs).items()
            }),
        )
        routes = tuple(self.routes)
        # Typed evidence, for the reason `ValidationReport` types its checks: a
        # record that reads `agreed`, `components` or `award` off whatever it
        # was handed never consulted the rules those types enforce.
        for index, route in enumerate(routes):
            if not isinstance(route, SolveRoute):
                raise ScientificValidationError(
                    f"consensus {text!r} route {index} is a "
                    f"{type(route).__name__}, not a SolveRoute"
                )
        if not isinstance(self.comparison, RouteComparison):
            raise ScientificValidationError(
                f"consensus {text!r} carries a {type(self.comparison).__name__} "
                f"as its comparison, not a RouteComparison"
            )
        if not isinstance(self.thresholds, VerificationThresholds):
            raise ScientificValidationError(
                f"consensus {text!r} carries a {type(self.thresholds).__name__} "
                f"as its thresholds, not VerificationThresholds"
            )
        identifiers = [r.route_id for r in routes]
        duplicate_ids = duplicate_entries(identifiers)
        if duplicate_ids:
            raise ScientificValidationError(
                f"consensus {text!r} declares duplicate route ids "
                f"{duplicate_ids}; two routes under one name cannot be told apart "
                f"in a comparison or named in a refusal"
            )
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "notes", str(self.notes))
        object.__setattr__(self, "tolerance_key", str(self.tolerance_key).strip())
        object.__setattr__(
            self,
            "reported_values",
            freeze({
                str(route_id): {
                    str(name): float(value)
                    for name, value in dict(produced).items()
                }
                for route_id, produced in dict(self.reported_values).items()
            }),
        )
        self._require_coherent_evidence()
        object.__setattr__(
            self,
            "_route_findings",
            freeze({route.route_id: _verify_route(route) for route in routes}),
        )

    def _require_coherent_evidence(self) -> None:
        """Refuse reports and comparisons that cannot have happened.

        The constructor is a public construction path, and so is ``from_dict``
        through it, so they must enforce what :meth:`over` guarantees by
        construction. Three states ``over`` never produces, each of which let
        a record describe more evidence than it had:

        * a report under a name that is no declared route -- unattributable;
        * a compared quantity that a route which DID report something did not
          report -- a comparison over a number that route never produced. A
          route with no report at all sat outside the comparison, which
          ``over`` produces legitimately and ``missing_outputs`` charges;
        * every route reporting every required output, a comparison that
          compared something, and a required output left out of it --
          agreement on part of the requirement standing for all of it.
        """
        declared = {route.route_id for route in self.routes}
        strangers = sorted(
            (set(self.reported_outputs) | set(self.reported_values)) - declared
        )
        if strangers:
            raise ScientificValidationError(
                f"consensus {self.consensus_id!r} records reported outputs "
                f"under {strangers}, and a report under a name that is not a "
                f"declared route cannot be attributed to any declaration. "
                f"Declared routes: {sorted(declared)}"
            )
        if self.reported_values:
            self._require_the_comparison_follows_from_its_numbers()
        compared = set(self.comparison.quantities)
        for route_id, names in sorted(self.reported_outputs.items()):
            unreported = sorted(compared - set(names)) if names else []
            if unreported:
                raise ScientificValidationError(
                    f"consensus {self.consensus_id!r} compares {unreported}, "
                    f"which route {route_id!r} did not report; a comparison "
                    f"over a number a route never produced is not a comparison "
                    f"of that route"
                )
        if (
            self.required_outputs
            and self.routes
            and self.comparison.compared_anything
            and not self.missing_outputs
        ):
            uncompared = sorted(set(self.required_outputs) - compared)
            if uncompared:
                raise ScientificValidationError(
                    f"consensus {self.consensus_id!r}: required output(s) "
                    f"{uncompared} reported by every route was not compared. "
                    f"Agreement on the rest is agreement about less than was "
                    f"asked, and cannot stand for the whole requirement"
                )

    def _require_the_comparison_follows_from_its_numbers(self) -> None:
        """A comparison is computed, not declared.

        Run only for a record that carries ``reported_values``. The numbers
        must be finite (a record carries only what it can write down), must be
        numbers for exactly the outputs recorded per route, must name a
        threshold of the set, and must reproduce ``comparison`` exactly when
        compared at that threshold. That is what :meth:`over` does, so every
        record it builds passes, and a record built any other way passes only
        by carrying the numbers that produce the comparison it states.
        """
        non_finite = sorted(
            f"{route_id}.{name}={value!r}"
            for route_id, produced in self.reported_values.items()
            for name, value in produced.items()
            if not math.isfinite(value)
        )
        if non_finite:
            raise ScientificValidationError(
                f"consensus {self.consensus_id!r} records non-finite "
                f"number(s) {non_finite}; a record carries only numbers it can "
                f"write down, and a route that returned one did not finish"
            )
        for route in self.routes:
            outputs = set(self.reported_outputs.get(route.route_id, ()))
            numbers = set(self.reported_values.get(route.route_id, {}))
            if outputs != numbers:
                raise ScientificValidationError(
                    f"consensus {self.consensus_id!r} records route "
                    f"{route.route_id!r} as reporting {sorted(outputs)} but "
                    f"carries numbers for {sorted(numbers)}"
                )
        if self.tolerance_key not in self.thresholds:
            raise ScientificValidationError(
                f"consensus {self.consensus_id!r} reads its tolerance from "
                f"{self.tolerance_key!r}, which is not a threshold of "
                f"{self.thresholds.identity}"
            )
        expected = _compare(
            self.reported_values,
            self.thresholds[self.tolerance_key],
            self.required_outputs,
            _declared_floors(self.thresholds, self.tolerance_key),
        )
        if self.comparison != expected:
            raise ScientificValidationError(
                f"consensus {self.consensus_id!r} carries a comparison that "
                f"does not follow from the numbers it records: it states worst "
                f"difference {self.comparison.worst_relative_difference!r} on "
                f"{list(self.comparison.quantities)} at tolerance "
                f"{self.comparison.tolerance!r}, and those numbers give "
                f"{expected.worst_relative_difference!r} on "
                f"{list(expected.quantities)} at {self.tolerance_key}="
                f"{expected.tolerance!r}"
            )

    # ---- the declaration side -------------------------------------------
    @property
    def shared_components(self) -> tuple[SharedComponent, ...]:
        """Every descriptive component more than one route names. **Reported, not judged.**

        ``components`` are a route's author's words, and they once decided
        independence -- one solver under two labels read as independent. The
        intersection stays for a reader; independence is read from verified
        dependencies.
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
    def unverified_routes(self) -> tuple[tuple[str, str], ...]:
        """``(route_id, why)`` for every declared route the core could not verify.

        Decided at construction against the domain layer's pins. A route with no
        dependencies is undeclared rather than unverified.
        """
        return tuple(
            sorted(
                (route.route_id, str(self._route_findings.get(route.route_id)))
                for route in self.routes
                if not route.declares_nothing
                and self._route_findings.get(route.route_id) is not None
            )
        )

    @property
    def shared_solver_identities(self) -> tuple[str, ...]:
        """Solver identities that appear on more than one route. **Reported.**

        Whether two routes share an implementation is decided by their verified
        dependencies, where it is a canonical identity rather than a label. The
        identity string is still listed, so a reader sees a repeated program
        whatever the declarations say.
        """
        counted: dict[str, int] = {}
        for route in self.routes:
            label = (
                f"{route.solver.solver_id}@{route.solver.version}"
                + (f"[{route.solver.backend}]" if route.solver.backend else "")
            )
            counted[label] = counted.get(label, 0) + 1
        return tuple(sorted(label for label, n in counted.items() if n > 1))

    def _verified_dependencies(self) -> tuple[dict[IndependenceDimension, frozenset[str]], ...]:
        return tuple(
            route.dependencies.canonical()
            for route in self.routes
            if route.dependencies is not None
            and self._route_findings.get(route.route_id, "unverified") is None
        )

    @property
    def shared_dependencies(self) -> tuple[tuple[IndependenceDimension, str], ...]:
        """``(dimension, canonical identity)`` for everything verified routes share."""
        counted: dict[tuple[IndependenceDimension, str], int] = {}
        for identities in self._verified_dependencies():
            for dimension, names in identities.items():
                for name in names:
                    counted[(dimension, name)] = counted.get((dimension, name), 0) + 1
        return tuple(
            sorted(
                (key for key, n in counted.items() if n > 1),
                key=lambda key: (key[0].value, key[1]),
            )
        )

    @property
    def shared_dimensions(self) -> tuple[IndependenceDimension, ...]:
        shared = {dimension for dimension, _ in self.shared_dependencies}
        return tuple(d for d in IndependenceDimension if d in shared)

    @property
    def independence(self) -> IndependenceVerdict:
        """How independent the routes are, as their verified declarations show.

        The order of the tests is the order a reader needs them in. Too few
        routes, a route that declared nothing and a route whose declaration is
        not the pinned one are each a reason no statement is available, and
        reporting "shares" or "independent" instead would mislead.
        """
        if len(self.routes) < 2:
            return IndependenceVerdict.TOO_FEW_ROUTES
        if self.undeclared_routes:
            return IndependenceVerdict.UNDECLARED
        if self.unverified_routes:
            return IndependenceVerdict.UNVERIFIED
        shared = self.shared_dimensions
        if IndependenceDimension.IMPLEMENTATION in shared:
            return IndependenceVerdict.NOT_INDEPENDENT
        if shared:
            return IndependenceVerdict.PARTIALLY_INDEPENDENT
        return IndependenceVerdict.FULLY_INDEPENDENT

    @property
    def routes_are_independent(self) -> bool:
        """Independent in every dimension ``CROSS_SOLVER_VALIDATED`` requires.

        Fully independent routes are. Partially independent routes are when
        nothing they share lies in :data:`SOLVER_INDEPENDENCE_DIMENSIONS` -- in
        practice, when what they share is the problem declaration.
        """
        if self.independence not in (
            IndependenceVerdict.FULLY_INDEPENDENT,
            IndependenceVerdict.PARTIALLY_INDEPENDENT,
        ):
            return False
        return not any(
            dimension in SOLVER_INDEPENDENCE_DIMENSIONS
            for dimension in self.shared_dimensions
        )

    # ---- the completeness side ------------------------------------------
    @property
    def missing_outputs(self) -> tuple[tuple[str, str], ...]:
        """``(route_id, quantity)`` for every required output a route did not report.

        Sorted, so a refusal reads the same on every run.
        """
        if not self.required_outputs:
            return ()
        # Over the ROUTES, not over `reported_outputs`. It used to run over the
        # reports and to return nothing when there were none, so a record built
        # through the constructor with required outputs and no reports had
        # nothing missing, read COMPLETE, and established CROSS_SOLVER_VALIDATED
        # for quantities no route was recorded as producing. `over` writes an
        # entry for every route and never showed it. A declared route with no
        # entry reported nothing, and is charged for all of it.
        #
        # `reported` is a TUPLE, so `name not in reported` was a linear scan --
        # once per required output, per route, making this O(routes x Q^2)
        # while the whole consensus that produced it is O(routes^2 x Q).
        # Measured: 7.5 ms at 1,000 required outputs and 675 ms at 10,000,
        # against 20 ms to build the entire consensus at that size.
        #
        # Each route's reported names are hashed ONCE, outside the inner loop.
        # Building the set inside it would be the same quadratic with a worse
        # constant, which is the obvious wrong version of this fix.
        return tuple(
            sorted(
                (route.route_id, name)
                for route in self.routes
                for reported_set in (
                    frozenset(self.reported_outputs.get(route.route_id, ())),
                )
                for name in self.required_outputs
                if name not in reported_set
            )
        )

    @property
    def output_completeness(self) -> OutputCompleteness:
        """Did every route answer the whole question?"""
        if not self.required_outputs:
            return OutputCompleteness.UNDECLARED
        # No route answered, so no route answered the whole question. The
        # per-route search has nothing to find missing among zero routes, and
        # an empty search is not a complete answer.
        if not self.routes or self.missing_outputs:
            return OutputCompleteness.INCOMPLETE
        return OutputCompleteness.COMPLETE

    @property
    def outputs_are_complete(self) -> bool:
        return self.output_completeness is OutputCompleteness.COMPLETE

    # ---- what it establishes --------------------------------------------
    @property
    def comparison_is_derived(self) -> bool:
        """Was the comparison recomputed from numbers this record carries?

        Construction refuses a comparison that does not follow from the
        recorded numbers at the threshold set's own tolerance, so a record that
        carries them has exactly the comparison they produce. Without them -- a
        /1 or /2 payload, or a record built by hand around a comparison -- the
        worst difference and the tolerance are a conclusion nobody can
        recompute, and a conclusion is not evidence.
        """
        return bool(self.reported_values)

    @property
    def threshold_authority_gap(self) -> str | None:
        """Why the threshold set is not the one these routes' declarations name, or ``None``.

        Read against the domain layer's route pins on every call, as
        ``award`` reads the threshold pins: see :func:`_threshold_authority_gap`.
        """
        return _threshold_authority_gap(self.routes, self.thresholds, self.tolerance_key)

    @property
    def execution_binding_gap(self) -> str | None:
        """Why the compared numbers are not bound to distinct executions, or ``None``.

        IND-02. Routes were labels and numbers were a mapping: identical
        fabricated numbers under the two production DC route ids earned the
        level, and so did one route's result wrapped as the other's. A level now
        needs every route's numbers to have been READ from an executed result
        by :meth:`from_results`, which records, per route, the result id, the
        run id, the solver identity (id, version and backend) and a digest of
        the numbers. This re-verifies that binding against the record on every
        read -- the route's solver, the numbers it carries, and that no two
        routes share a result or a run.

        What it cannot do is prove a result was not fabricated before it was
        handed over: a ``ScientificResult`` is public to construct. It closes
        the mapping-of-numbers and the duck-typed-result holes, binds the solver
        version into what is verified, and makes one execution presented twice
        visible and refused.
        """
        bindings = getattr(self, _EXECUTION_BINDINGS, None)
        if bindings is None:
            return (
                "the numbers were handed over as a mapping rather than read from "
                "executed results, so nothing binds them to a solve; only "
                "CrossSolverConsensus.from_results can bind them"
            )
        gaps: list[str] = []
        declared = {r.route_id for r in self.routes}
        unbound = sorted(declared - set(bindings))
        if unbound:
            gaps.append(f"route(s) {unbound} carry no execution binding")
        strangers = sorted(set(bindings) - declared)
        if strangers:
            gaps.append(f"execution bindings under undeclared route(s) {strangers}")
        for route in self.routes:
            binding = bindings.get(route.route_id)
            if binding is None:
                continue
            solver = binding["solver"]
            if (solver["solver_id"], solver["version"], solver["backend"]) != (
                route.solver.solver_id, route.solver.version, route.solver.backend
            ):
                gaps.append(
                    f"route {route.route_id!r} is bound to a result from "
                    f"{solver['solver_id']}@{solver['version']}[{solver['backend']}], "
                    f"not the route's {route.solver.solver_id}@"
                    f"{route.solver.version}[{route.solver.backend}]"
                )
            produced = self.reported_values.get(route.route_id)
            if produced is None or _values_digest(produced) != binding["values_digest"]:
                gaps.append(
                    f"the numbers recorded for route {route.route_id!r} are not "
                    f"the numbers its bound result produced"
                )
        for label, kind in (("result_id", "result"), ("run_id", "run")):
            seen: dict[str, list[str]] = {}
            for route_id, binding in sorted(bindings.items()):
                seen.setdefault(binding[label], []).append(route_id)
            shared = {key: ids for key, ids in seen.items() if len(ids) > 1}
            if shared:
                gaps.append(
                    f"routes {sorted(i for ids in shared.values() for i in ids)} "
                    f"are bound to one {kind} ({sorted(shared)}); agreement between "
                    f"an execution and itself is not agreement between distinct "
                    f"executions"
                )
        return "; ".join(gaps) if gaps else None

    @property
    def earned(self) -> bool:
        """Four conditions, and all of them.

        Independent routes, a **complete** answer from each, a comparison
        **recomputed from the numbers the record carries**, and agreement
        inside the threshold set's tolerance. Completeness was missing once:
        agreement on the single quantity two routes happened to share bought
        the same level as agreement on all of them. Recomputation was missing
        too: a comparison was taken on its word, so a record could state the
        agreement it wanted.
        """
        return (
            self.routes_are_independent
            and self.outputs_are_complete
            and self.comparison_is_derived
            and self.comparison.agreed
            and self.threshold_authority_gap is None
            and self.execution_binding_gap is None
        )

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
                f"dependencies, so no independence claim is available: a route "
                f"that does not say what it is made of earns nothing"
            )
        if independence is IndependenceVerdict.UNVERIFIED:
            unverified = [
                f"{route_id} {finding}" for route_id, finding in self.unverified_routes
            ]
            return (
                f"independence is read only from declarations the domain layer "
                f"pins and the core verifies, and route(s) {unverified}; the "
                f"comparison is reported and establishes no level"
            )
        if not self.routes_are_independent:
            shared = [
                f"{dimension.value}:{name}"
                for dimension, name in self.shared_dependencies
                if dimension in SOLVER_INDEPENDENCE_DIMENSIONS
            ]
            return (
                f"the routes are {independence.value.replace('_', ' ')}: they "
                f"share {shared}, so agreement between them is evidence about "
                f"the shared machinery and not about the physics; the "
                f"comparison is reported and establishes no level"
            )
        completeness = self.output_completeness
        if completeness is OutputCompleteness.UNDECLARED:
            return (
                "the consensus declares no required outputs, so there is no "
                "statement of what the routes owed and no way to tell a "
                "complete confirmation from a partial one; the comparison is "
                "reported and establishes no level"
            )
        if completeness is OutputCompleteness.INCOMPLETE:
            short = [f"{route}:{name}" for route, name in self.missing_outputs]
            return (
                f"required output(s) {short} were not reported, so at least "
                f"one route answered only part of the question; agreement on "
                f"the rest is agreement about less than was asked and "
                f"establishes no level"
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
        if not self.comparison_is_derived:
            return (
                f"the routes are independent and the comparison states "
                f"agreement to {self.comparison.worst_relative_difference:.3e}, "
                f"but the record carries it without the numbers it was "
                f"computed from, so it is a conclusion nobody can recompute and "
                f"establishes no level"
            )
        authority_gap = self.threshold_authority_gap
        if authority_gap is not None:
            return (
                f"the independent routes agree to "
                f"{self.comparison.worst_relative_difference:.3e} against "
                f"{self.tolerance_key!r} of {self.thresholds.identity}, but the "
                f"level is withheld because that is not the threshold their "
                f"declarations name: {authority_gap}"
            )
        binding_gap = self.execution_binding_gap
        if binding_gap is not None:
            return (
                f"the independent routes agree to "
                f"{self.comparison.worst_relative_difference:.3e}, but the level "
                f"is withheld because the numbers are not bound to distinct "
                f"executed results: {binding_gap}"
            )
        if self.establishes is None:
            return (
                f"the independent routes agree to "
                f"{self.comparison.worst_relative_difference:.3e}, but the "
                f"level is withheld because {self.thresholds.identity} is not "
                f"this gate's declared threshold set"
            )
        shared = [
            f"{dimension.value}:{name}" for dimension, name in self.shared_dependencies
        ]
        return (
            f"{len(self.routes)} routes, {self.independence.value.replace('_', ' ')} "
            f"and independent in every dimension the level requires"
            + (f" (sharing {shared})" if shared else "")
            + f", each reported all {len(self.required_outputs)} required output(s) "
            f"and agree on {len(self.comparison.quantities)} quantities to "
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

        A disagreement beyond tolerance is a FAIL, whether or not the routes are
        independent.

        R-21 (re-audit 2026-09-16, I-12 part B): a disagreement between routes
        that share their machinery used to be a WARNING, on the reasoning that
        "a comparison denied authority to award cannot be given authority to
        condemn". Those are not the same authority. Awarding a level is a claim
        about what the evidence SHOWS; reporting a disagreement is a
        MEASUREMENT of what the two routes did. Both routes were asked for the
        same named quantities, under one declared required-output contract, and
        returned numbers that differ beyond the declared tolerance: at least
        one of them is wrong about the thing they were both asked to compute,
        and that is true however much machinery they share. Sharing machinery
        makes it worse rather than better -- the same arithmetic produced two
        different answers, which is a defect in the computation and not a
        difference of opinion between independent witnesses. The audited case
        read WARNING at a relative difference of 1/3, and the verdict over it
        stayed SUPPORTED.

        The outcome and the level are still allowed to disagree in the other
        direction, which is the sentence this record exists to write: routes
        that AGREE while sharing a Jacobian produce a PASS that establishes
        nothing.
        """
        comparison = self.comparison
        if not comparison.compared_anything:
            outcome = ValidationOutcome.NOT_RUN
        elif comparison.agreed:
            outcome = ValidationOutcome.PASS
        else:
            outcome = ValidationOutcome.FAIL
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
            reported = self.reported_outputs.get(route.route_id)
            produced = (
                ", ".join(reported) if reported else "nothing recorded"
            )
            backend = f"[{route.solver.backend}]" if route.solver.backend else ""
            finding = self._route_findings.get(route.route_id)
            standing = (
                "no dependencies declared"
                if route.declares_nothing
                else "dependencies verified against the domain layer's pin"
                if finding is None
                else f"dependencies UNVERIFIED: {finding}"
            )
            lines.append(
                f"route {route.route_id} = {route.solver.solver_id}@"
                f"{route.solver.version}{backend} declares [{declared}] reports "
                f"[{produced}]; {standing}"
            )
        lines.append(
            "required outputs: "
            + (", ".join(self.required_outputs) or "NONE DECLARED")
        )
        bindings = getattr(self, _EXECUTION_BINDINGS, None) or {}
        for route_id, binding in sorted(bindings.items()):
            solver = binding["solver"]
            lines.append(
                f"route {route_id} read from result {binding['result_id']} of run "
                f"{binding['run_id']} by {solver['solver_id']}@{solver['version']}"
                f"[{solver['backend']}]; numbers sha256:{binding['values_digest']}"
            )
        if not bindings:
            lines.append("execution binding: NONE (numbers handed over as a mapping)")
        # The exact threshold record the comparison was judged under, written
        # so a check carrying CROSS_SOLVER_VALIDATED can be re-verified from its
        # own evidence against the registries (VAL-01). The `threshold:` lines
        # below round to six digits for a reader and cannot be hashed.
        lines.append(
            CONSENSUS_THRESHOLDS_EVIDENCE_PREFIX
            + json.dumps(
                {
                    "gate_id": self.thresholds.gate_id,
                    "version": self.thresholds.version,
                    "tolerance_key": self.tolerance_key,
                    "values": dict(self.thresholds.values),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        # R-21: which independence the level rests on, written only when a level is actually awarded --
        # a check that establishes nothing has no basis to state, and a line saying `declared` beside no
        # level would read as a claim nobody made.
        if self.establishes is not None:
            lines.append(INDEPENDENCE_BASIS_EVIDENCE_PREFIX + INDEPENDENCE_BASIS_DECLARED)
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
        required_outputs: Iterable[str] = (),
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
        required = tuple(sorted(set(required_outputs)))
        # The numbers travel with the record whenever they can be written down.
        # A NaN or an infinity cannot, and the comparison below already records
        # that a route returned one and compares nothing -- which establishes
        # nothing whether the numbers travel or not.
        finite_values = {
            route_id: {
                name: float(value)
                for name, value in produced.items()
                if math.isfinite(float(value))
            }
            for route_id, produced in values.items()
        }
        return cls(
            consensus_id=consensus_id,
            routes=routes,
            comparison=_compare(
                values,
                thresholds[tolerance_key],
                required,
                _declared_floors(thresholds, tolerance_key),
            ),
            thresholds=thresholds,
            required_outputs=required,
            # Recorded from what each route actually handed over, so a refusal
            # can name the route and the quantity. A route that reported
            # nothing appears with an empty tuple rather than being absent,
            # which is what lets `missing_outputs` charge it for the whole
            # required set instead of overlooking it.
            reported_outputs={
                route.route_id: tuple(
                    sorted(finite_values.get(route.route_id, {}))
                )
                for route in routes
            },
            notes=notes,
            tolerance_key=tolerance_key,
            reported_values=finite_values,
        )

    @classmethod
    def from_results(
        cls,
        *,
        consensus_id: str,
        routes: Iterable[SolveRoute],
        results: Mapping[str, Any],
        thresholds: VerificationThresholds,
        tolerance_key: str,
        required_outputs: Iterable[str] = (),
        notes: str = "",
    ) -> "CrossSolverConsensus":
        """Compare executed results, one per route, and bind each route to its result.

        The construction path that can award ``CROSS_SOLVER_VALIDATED`` (IND-02).
        :meth:`over` takes numbers and can no longer award it: a mapping of
        numbers is attributable to nobody.

        Refused outright: a result that is not a ``ScientificResult``; a route
        with no result or a result under no declared route; a result whose own
        provenance does not name the route's solver at the route's version; a
        result whose solver identity is not the route's (backend included).
        Recorded and refused a level rather than raised: two routes bound to one
        result or one run, because the record of that comparison is still worth
        keeping and it establishes nothing.

        The compared numbers are read from each result's values -- every
        ``Quantity``, converted into the CANONICAL unit of its dimension (the
        coherent SI base unit), so that a route which returned the right number
        in another unit is not scored as a disagreement and the comparison does
        not depend on which route was declared first. The unit a declared
        absolute floor is read in is that same canonical unit.

This paragraph used to say each value was read in whatever unit its
        own route reported, and that a route returning the right number in
        another unit therefore showed up as a disagreement. CORE-018 made that
        false and left the sentence standing; I-22 (R-52) makes the common unit
        canonical instead of arbitrary.
        """
        from .results.result import ScientificResult

        routes = tuple(routes)
        by_route = dict(results)
        known = {r.route_id for r in routes}
        strangers = sorted(set(by_route) - known)
        if strangers:
            raise ScientificValidationError(
                f"consensus {consensus_id!r} was handed results for undeclared "
                f"route(s) {strangers}; declared routes: {sorted(known)}"
            )
        values: dict[str, dict[str, float]] = {}
        bindings: dict[str, dict[str, Any]] = {}
        # CORE-018 (scientific core audit 2026-09-16): every route's value of a name is expressed in ONE unit,
        # because raw magnitudes compared 1 m with 1000 mm as a 0.999 disagreement.
        #
        # THAT UNIT IS CANONICAL, NOT THE FIRST DECLARED ROUTE'S (I-22, R-52).
        # CORE-018 took it from whichever declared route reported the name
        # first, and declaration order then decided two things it has no
        # business deciding. 26.85 degC against 300.0000001 kelvin -- one
        # ten-billionth of a kelvin apart -- scored 3.72e-09 and DISAGREED with
        # the Celsius route first, and 3.33e-10 and AGREED with the kelvin
        # route first, against one tolerance of 1e-9. And a declared floor is a
        # bare number read in that same unit, so the same 1e-15 was worth
        # 1e-15 A in one order and 1e-9 A in the other.
        #
        # `base_unit` is a pure function of a unit's DIMENSION, so it cannot
        # depend on order, and it is what this module's own units layer reaches
        # for when two scales must be put on one footing. It is also always a
        # ratio scale, which is what the comparison below needs: |a-b|/max(|a|,
        # |b|) is a statement about a RATIO, and a ratio means nothing where
        # zero of the unit is a convention. Two readings of -273.14 degC and
        # -273.14000000001 degC are 0.01 K apart by a relative 1e-8 -- a real
        # disagreement -- and scored 3.7e-14 on the Celsius scale.
        common_unit: dict[str, str] = {}
        for route in routes:
            for name, quantity in getattr(by_route.get(route.route_id), "values", {}).items():
                canonical = base_unit(quantity.units)
                if not is_ratio_scale(canonical):
                    raise ScientificValidationError(
                        f"consensus {consensus_id!r} cannot compare {str(name)!r}: "
                        f"its canonical unit {canonical!r} is not a ratio scale, "
                        f"so the relative difference this comparison reports "
                        f"would be a ratio of two numbers whose zero is a "
                        f"convention. Report it on a scale whose zero is the "
                        f"quantity's zero, or compare it against a declared "
                        f"absolute floor"
                    )
                common_unit.setdefault(str(name), canonical)
        for route in routes:
            if route.route_id not in by_route:
                raise ScientificValidationError(
                    f"consensus {consensus_id!r} has no result for route "
                    f"{route.route_id!r}; every route is compared on what it "
                    f"actually executed"
                )
            result = by_route[route.route_id]
            if not isinstance(result, ScientificResult):
                raise ScientificValidationError(
                    f"consensus {consensus_id!r} route {route.route_id!r} was "
                    f"handed a {type(result).__name__}, not a ScientificResult; "
                    f"an object that merely carries values and a provenance is "
                    f"not an executed result"
                )
            recorded = tuple(result.provenance.solvers)
            if route.solver.key not in recorded:
                raise ScientificValidationError(
                    f"route {route.route_id!r} runs solver "
                    f"{route.solver.solver_id}@{route.solver.version}, and its "
                    f"result's provenance records solvers {list(recorded)}; a "
                    f"result presented under another solver's identity is refused"
                )
            if result.solver is not None and (
                result.solver.solver_id, result.solver.version, result.solver.backend
            ) != (route.solver.solver_id, route.solver.version, route.solver.backend):
                raise ScientificValidationError(
                    f"route {route.route_id!r} runs solver "
                    f"{route.solver.solver_id}@{route.solver.version} on backend "
                    f"{route.solver.backend!r}, and its result was produced by "
                    f"{result.solver.solver_id}@{result.solver.version} on backend "
                    f"{result.solver.backend!r}"
                )
            produced = {
                str(name): float(quantity.magnitude_in(common_unit.get(str(name), quantity.units)))
                for name, quantity in result.values.items()
            }
            values[route.route_id] = produced
            bindings[route.route_id] = {
                "result_id": result.result_id,
                "run_id": result.provenance.run_id,
                "solver": {
                    "solver_id": route.solver.solver_id,
                    "version": route.solver.version,
                    "backend": route.solver.backend,
                },
                "values_digest": _values_digest(produced),
            }
        record = cls.over(
            consensus_id=consensus_id,
            routes=routes,
            values=values,
            thresholds=thresholds,
            tolerance_key=tolerance_key,
            required_outputs=required_outputs,
            notes=notes,
        )
        object.__setattr__(record, _EXECUTION_BINDINGS, freeze(bindings))
        return record

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSENSUS_SCHEMA,
            "consensus_id": self.consensus_id,
            "routes": [r.to_dict() for r in self.routes],
            "comparison": self.comparison.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "required_outputs": list(self.required_outputs),
            "reported_outputs": {
                route_id: list(names)
                for route_id, names in sorted(self.reported_outputs.items())
            },
            "tolerance_key": self.tolerance_key,
            "reported_values": {
                route_id: dict(sorted(produced.items()))
                for route_id, produced in sorted(self.reported_values.items())
            },
            "notes": self.notes,
            # What each route's numbers were read from; None for a record whose
            # numbers were handed over as a mapping. Re-verified on the way in.
            "execution_bindings": self._serialized_bindings(),
            # Derived, emitted for readers, and recomputed on the way back in.
            "independence": self.independence.value,
            "shared_solver_identities": list(self.shared_solver_identities),
            "output_completeness": self.output_completeness.value,
            "missing_outputs": [
                f"{route}:{name}" for route, name in self.missing_outputs
            ],
            "shared_components": [c.label for c in self.shared_components],
            "unverified_routes": [
                f"{route_id}: {finding}" for route_id, finding in self.unverified_routes
            ],
            "shared_dependencies": [
                f"{dimension.value}:{name}" for dimension, name in self.shared_dependencies
            ],
            "independent_dimensions": [
                d.value for d in IndependenceDimension if d not in self.shared_dimensions
            ],
            "establishes": (
                self.establishes.value if self.establishes else None
            ),
            "reason": self.reason,
        }

    def _serialized_bindings(self) -> dict[str, Any] | None:
        bindings = getattr(self, _EXECUTION_BINDINGS, None)
        if bindings is None:
            return None
        return {
            route_id: {
                "result_id": binding["result_id"],
                "run_id": binding["run_id"],
                "solver": dict(binding["solver"]),
                "values_digest": binding["values_digest"],
            }
            for route_id, binding in sorted(bindings.items())
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CrossSolverConsensus":
        version = require_schema_any(
            payload, (CONSENSUS_SCHEMA_V1, CONSENSUS_SCHEMA_V2, CONSENSUS_SCHEMA)
        )
        if version == CONSENSUS_SCHEMA_V1 and payload.get("establishes"):
            # A /1 record has no field naming what the routes owed, so the
            # level it claims was awarded by a rule that could not tell a
            # complete confirmation from a partial one. The requirement cannot
            # be reconstructed and must not be defaulted: an empty required set
            # is the state this version refuses to award on, so silently
            # re-deriving would either confirm a claim nothing here can check
            # or fail with a message about a contradiction that is really a
            # version difference.
            raise ScientificValidationError(
                f"{CONSENSUS_SCHEMA_V1} record {payload.get('consensus_id')!r} "
                f"claims to establish {payload['establishes']!r} and has no "
                f"field saying which outputs the routes were required to "
                f"produce. That level was awarded under a rule that could not "
                f"see output completeness, and the requirement cannot be "
                f"reconstructed from the record. Re-derive the consensus, or "
                f"read it with the code that wrote it"
            )
        if version == CONSENSUS_SCHEMA_V2 and payload.get("establishes"):
            # The same rule, one version on: a /2 record keeps a comparison's
            # conclusion and not the numbers behind it, so the level it claims
            # was awarded by a rule that took the comparison on its word, and the
            # numbers cannot be reconstructed.
            raise ScientificValidationError(
                f"{CONSENSUS_SCHEMA_V2} record {payload.get('consensus_id')!r} "
                f"claims to establish {payload['establishes']!r} and carries no "
                f"numbers its comparison was computed from. That level was "
                f"awarded under a rule that took a comparison on its word, and "
                f"the numbers cannot be reconstructed from the record. "
                f"Re-derive the consensus, or read it with the code that wrote "
                f"it"
            )
        carries_numbers = version == CONSENSUS_SCHEMA
        record = cls(
            consensus_id=payload["consensus_id"],
            routes=tuple(
                SolveRoute.from_dict(r) for r in payload.get("routes", ())
            ),
            comparison=RouteComparison.from_dict(payload["comparison"]),
            thresholds=VerificationThresholds.from_dict(payload["thresholds"]),
            required_outputs=tuple(payload.get("required_outputs", ())),
            reported_outputs={
                route_id: tuple(names)
                for route_id, names in (
                    payload.get("reported_outputs") or {}
                ).items()
            },
            notes=payload.get("notes", ""),
            tolerance_key=(
                payload.get("tolerance_key", "") if carries_numbers else ""
            ),
            reported_values=(
                {
                    route_id: dict(produced)
                    for route_id, produced in (
                        payload.get("reported_values") or {}
                    ).items()
                }
                if carries_numbers
                else {}
            ),
        )
        serialized_bindings = payload.get("execution_bindings") if carries_numbers else None
        if serialized_bindings is not None:
            if not isinstance(serialized_bindings, _RuntimeMapping):
                raise ScientificValidationError(
                    f"serialized consensus {record.consensus_id!r} carries execution "
                    f"bindings that are not a mapping by route id"
                )
            object.__setattr__(
                record,
                _EXECUTION_BINDINGS,
                freeze({
                    str(route_id): _checked_binding(str(route_id), entry)
                    for route_id, entry in serialized_bindings.items()
                }),
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
