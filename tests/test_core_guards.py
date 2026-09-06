"""Repo-wide guards: properties every model, solver and record must hold.

These tests are written over what the repository *contains*, not over a list
somebody maintains. Every model is discovered by walking ``engcore``, so a
domain added tomorrow is covered on the day it lands, and a domain that opts
out of a guard fails here rather than in a report six months later.

That is the point of the round these tests came from. Each finding they encode
was first found in one domain and then found again in a second, because the
guard was a convention four domains happened to follow rather than a rule the
core enforced. A convention has a fifth domain; a rule does not.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import pkgutil

import pytest

from src import engcore
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    ModelValidityError,
)
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.ir.variables import ScientificParameter
from src.engcore.scientific.models.definition import ScientificModelDefinition
from src.engcore.scientific.models.registry import ModelRegistry
from src.engcore.scientific.units.quantity import Quantity


# =====================================================================
# Discovery
# =====================================================================

def _every_model() -> tuple[ScientificModelDefinition, ...]:
    """Every model record reachable from ``engcore``, by import rather than list.

    A module-level constant in a package nobody imported here would be missed,
    so this walks the package rather than reading a registry: the registries are
    built by functions, one per domain, and a domain that forgot to write one
    would be exactly the domain worth testing.
    """
    found: dict[tuple[str, str], ScientificModelDefinition] = {}
    for module_info in pkgutil.walk_packages(engcore.__path__, "src.engcore."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # pragma: no cover - an unimportable module is a
            continue       # different test's failure, not this one's
        for attribute in dir(module):
            try:
                value = getattr(module, attribute)
            except Exception:  # pragma: no cover
                continue
            if isinstance(value, ScientificModelDefinition):
                found.setdefault(value.key, value)
    return tuple(found[key] for key in sorted(found))


MODELS = _every_model()
MODEL_IDS = [f"{m.model_id}@{m.version}" for m in MODELS]
RESERVING = [m for m in MODELS if m.derived_quantities]
RESERVING_IDS = [f"{m.model_id}@{m.version}" for m in RESERVING]


def test_the_discovery_actually_found_the_repository():
    """A guard over an empty set passes and proves nothing."""
    assert len(MODELS) >= 14
    domains = {m.domain for m in MODELS}
    assert {"electrical", "thermal", "battery"} <= domains
    # And most of them reserve something, so the guards below are not vacuous.
    assert len(RESERVING) >= 12


# =====================================================================
# GUARD 1 — a caller parameter cannot occupy a derived quantity's name
# =====================================================================

@pytest.mark.parametrize("model", MODELS, ids=MODEL_IDS)
def test_every_condition_name_is_either_declared_or_reserved(model):
    """The classification the core refuses to construct a model without.

    A validity condition reads a context key by name. That key is filled either
    by a caller declaration -- in which case the model must declare it as an
    input, so a reader can see the caller is meant to supply it -- or by the
    domain's assembler, in which case it must be reserved so no caller can. A
    name in neither category is filled by whatever happens to occupy it, which
    is the forgery.
    """
    declared = {spec.name for spec in model.inputs}
    unclassified = model.validity.context_keys - declared - model.derived_quantities
    assert not unclassified, (model.model_id, sorted(unclassified))


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_no_model_reserves_a_name_nothing_reads(model):
    """A reserved name that decides nothing is a claim of protection, not one."""
    assert model.derived_quantities <= model.validity.context_keys


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_a_caller_parameter_named_after_a_derived_quantity_is_refused(model):
    """The round's central test, over every model in the repository.

    For each name a model derives, a problem declaring a parameter of that name
    cannot produce a caller-declared context at all. Not "the value is ignored"
    and not "the verdict is the same": the assessment does not happen, because
    a caller asking for a verdict over a derived quantity they supplied is
    asking a question they are not entitled to ask.

    The property the round asked for -- *a caller parameter named after a
    derived quantity changes no verdict* -- follows and is stronger here: there
    is no verdict for it to change.
    """
    for name in sorted(model.derived_quantities):
        problem = ScientificProblem(
            problem_id=f"forge:{model.model_id}:{name}",
            parameters=(
                ScientificParameter(
                    name=name, value=Quantity(0.5, "dimensionless")
                ),
            ),
        )
        with pytest.raises(InvalidScientificProblem, match="derives"):
            problem.validity_context(reserved=model.derived_quantities)


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_a_reserved_name_is_refused_in_the_declared_half_of_an_assessment(model):
    """The second door: assembly, rather than problem construction.

    A context can be built by hand, deserialized from a payload or produced by
    a builder nobody has written yet. Whatever route it took, ``assess`` refuses
    to read a reserved name out of the caller's half.
    """
    for name in sorted(model.derived_quantities):
        with pytest.raises(ModelValidityError, match="reserved name"):
            model.assess_validity(declared={name: Quantity(0.5, "dimensionless")})
        # And the same mapping handed in as the single-argument form, which is
        # what a domain merging the two namespaces would produce.
        with pytest.raises(ModelValidityError, match="reserved name"):
            model.assess_validity({name: Quantity(0.5, "dimensionless")})


@pytest.mark.parametrize("model", MODELS, ids=MODEL_IDS)
def test_a_domain_cannot_assemble_a_name_it_did_not_reserve(model):
    """The third door: the assembler's own output.

    A derived quantity added to a domain's assembly without being reserved
    would be impersonable from the day it landed. It is refused at the
    assessment that would have read it.
    """
    with pytest.raises(ModelValidityError, match="does not reserve"):
        model.assess_validity(
            assembled={"a_name_no_model_reserves": Quantity(1.0, "dimensionless")}
        )


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_the_reserved_namespace_survives_serialization(model):
    """A guard that stopped at a process boundary would not be one.

    A model record crosses a boundary as JSON. If the reserved set did not
    travel with it, the receiving side would assess the same conditions with
    nothing protected -- and would not know that it was.
    """
    restored = ScientificModelDefinition.from_dict(model.to_dict())
    assert restored.derived_quantities == model.derived_quantities
    assert restored == model


def test_a_registry_can_enumerate_every_reserved_name_in_the_repository():
    """Why the set lives on the record rather than beside it.

    This is the test that could not be written while each domain kept its
    reserved names in a module-level constant: nothing could reach them without
    importing five specific modules and remembering the sixth.
    """
    registry = ModelRegistry(MODELS)
    reserved: set[str] = set()
    for model in registry:
        reserved |= model.derived_quantities
    assert {
        "biot_number",
        "damkohler_number",
        "dissipated_power_utilization",
        "peukert_capacity_ratio",
        "reduced_debye_temperature",
    } <= reserved


# =====================================================================
# GUARD 2 — a check cannot PASS with a level it did not check for
# =====================================================================
#
# The rule lives on `ValidationCheck.earns_its_level`. Where it is *enforced*
# is the part this round could not finish, and the reason is recorded here as
# a failing-if-violated test rather than in a comment nobody reads.
#
# `ValidationCheck.__post_init__` cannot refuse a check that fails the rule,
# because exactly one such construction lives in
# `src/engcore/domains/thermal/conduction1d/validation.py`, whose bytes are
# pinned by `experiments/thermal_t1/t1_config.py`. Refusing at construction
# would break a frozen experiment; exempting that one construction would be a
# guard with a hole in it, and the next domain would find the hole. So the rule
# is checked here over every construction in the repository, with that single
# site named -- and the test asserts it is the ONLY one, so a second cannot
# appear without this failing.

_LEVEL_NAMES = frozenset(
    {
        "DIMENSIONALLY_VALID",
        "NUMERICALLY_CONVERGED",
        "ANALYTICALLY_VERIFIED",
        "BENCHMARK_VALIDATED",
        "CROSS_SOLVER_VALIDATED",
        "EXPERIMENTALLY_VALIDATED",
    }
)

#: The one construction that cannot satisfy the rule and cannot be edited: a
#: frozen file, pinned by SHA-256 over its bytes. See NEEDS.md.
_FROZEN_UNEARNED_LEVEL = (
    "src/engcore/domains/thermal/conduction1d/validation.py",
    "dimensional_consistency",
)


def _static_check_constructions():
    """Every literal ``ValidationCheck(...)`` in ``src``, with its literal args.

    Static rather than by running solvers: a construction on a branch no test
    exercises is exactly the one worth auditing, and a coverage-shaped guard
    would miss it.
    """
    root = pathlib.Path(__file__).resolve().parent.parent / "src"
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        relative = path.relative_to(root.parent).as_posix()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "ValidationCheck"
            ):
                continue
            kwargs = {k.arg: k.value for k in node.keywords}

            def literal(key, _kwargs=kwargs):
                value = _kwargs.get(key)
                if isinstance(value, ast.Attribute):
                    return value.attr
                if isinstance(value, ast.Constant):
                    return value.value
                return None

            yield (
                relative,
                node.lineno,
                literal("name"),
                literal("outcome"),
                literal("establishes"),
                {"residual", "tolerance"} <= set(kwargs) or "evidence" in kwargs,
            )


def test_no_check_in_the_repository_claims_a_level_it_did_not_check_for():
    """A PASS declaring a level must carry evidence that it compared something.

    The CSTR reproduction was an unconditional PASS carrying
    ``establishes=DIMENSIONALLY_VALID`` beside a sentence describing what the
    units were. Nothing was compared. The sentence was true and it was still a
    claimed level, because a claim is what occupies the field a reader consults
    to find out whether anybody checked.
    """
    offenders = [
        (path, line, name)
        for path, line, name, outcome, establishes, has_evidence in (
            _static_check_constructions()
        )
        if outcome in ("PASS", "WARNING")
        and establishes in _LEVEL_NAMES
        and not has_evidence
    ]
    assert [(p, n) for p, _, n in offenders] == [_FROZEN_UNEARNED_LEVEL], (
        "a validation check claims a level with no residual, no tolerance and "
        "no reference: " + repr(offenders)
    )


def test_the_rule_itself_is_what_that_audit_applied():
    """The property, exercised directly, so the audit above is not the rule."""
    from src.engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationLevel,
        ValidationOutcome,
    )

    def check(**kwargs):
        return ValidationCheck(name="c", outcome=ValidationOutcome.PASS, **kwargs)

    # Claiming nothing is always honest.
    assert check().earns_its_level
    # A level with nothing behind it is not.
    assert not check(
        establishes=ValidationLevel.DIMENSIONALLY_VALID
    ).earns_its_level
    # A residual with no bound is a number nobody bounded.
    assert not check(
        establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-12
    ).earns_its_level
    # A bound with nothing measured against it is not a comparison either.
    assert not check(
        establishes=ValidationLevel.NUMERICALLY_CONVERGED, tolerance=1e-9
    ).earns_its_level
    # Both is a comparison.
    assert check(
        establishes=ValidationLevel.NUMERICALLY_CONVERGED,
        residual=1e-12,
        tolerance=1e-9,
    ).earns_its_level
    # And so is a named reference, for a level no residual can express.
    assert check(
        establishes=ValidationLevel.DIMENSIONALLY_VALID,
        evidence=("model.outputs:u=dimensionless",),
    ).earns_its_level
    # A FAIL or NOT_RUN contributes no level whatever it declares, so it is not
    # asked to prove one.
    assert ValidationCheck(
        name="c",
        outcome=ValidationOutcome.NOT_RUN,
        establishes=ValidationLevel.DIMENSIONALLY_VALID,
    ).earns_its_level


def test_the_cstr_dimension_check_compares_against_the_model_record():
    """The fix, exercised: a real comparison rather than a sentence.

    A solve whose metrics match the record's declared units earns the level and
    names what it was compared against. A solve with nothing comparable earns
    nothing and says NOT_RUN, rather than passing over an empty set.
    """
    from src.engcore.domains.kinetics.cstr.validation import (
        check_metric_dimensions,
    )
    from src.engcore.scientific.results.validation import (
        ValidationLevel,
        ValidationOutcome,
    )

    class _Raw:
        def __init__(self, values):
            self.values = values

    honest = check_metric_dimensions(
        _Raw({"C_A:final": 950.0, "T:final": 312.0, "conversion:final": 0.05})
    )
    assert honest.outcome is ValidationOutcome.PASS
    assert honest.establishes is ValidationLevel.DIMENSIONALLY_VALID
    assert honest.earns_its_level
    assert honest.evidence  # names the ModelOutputSpecs it compared against

    empty = check_metric_dimensions(_Raw({}))
    assert empty.outcome is ValidationOutcome.NOT_RUN
    assert empty.establishes is None
    assert empty.earns_its_level


def test_every_check_a_live_solve_produces_earns_its_level():
    """The runtime half: reports as the domains actually build them.

    The static audit cannot see a check whose ``outcome`` or ``establishes`` is
    computed, and most of them are. This drives two domains end to end and
    holds every check in the resulting reports to the same rule.
    """
    from src.engcore.domains.kinetics.cstr import solve_reactor
    from src.engcore.domains.kinetics.cstr.problem import (
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
    )
    from src.engcore.domains.electrical.dc import (
        DCCircuit,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
        solve_circuit,
    )

    circuit = DCCircuit(
        circuit_id="guard2",
        nodes=(ElectricalNode("gnd", is_reference=True), ElectricalNode("n1")),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="n1",
                node_b="gnd",
                resistance=Quantity(1000.0, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="n1",
                negative_node="gnd",
                voltage=Quantity(5.0, "volt"),
            ),
        ),
    )
    run = ReactorRun(
        run_label="guard2",
        chemistry=ReactorChemistry(
            k0=Quantity(7.2e10 / 60.0, "1/s"),
            activation_energy=Quantity(8750.0 * 8.314462618, "J/mol"),
            heat_of_reaction=Quantity(-5.0e4, "J/mol"),
            density=Quantity(1000.0, "kg/m**3"),
            heat_capacity=Quantity(239.0, "J/(kg*K)"),
        ),
        operation=ReactorOperation(
            volume=Quantity(0.1, "m**3"),
            flow_rate=Quantity(0.1 / 60.0, "m**3/s"),
            feed_concentration=Quantity(1000.0, "mol/m**3"),
            feed_temperature=Quantity(350.0, "kelvin"),
            coolant_temperature=Quantity(290.0, "kelvin"),
            ua=Quantity(5.0e4 / 60.0, "W/K"),
            end_time=Quantity(600.0, "second"),
        ),
        initial_concentration=Quantity(1000.0, "mol/m**3"),
        initial_temperature=Quantity(300.0, "kelvin"),
    )

    reports = [
        solve_circuit(circuit, run_id="guard2-dc").validation,
        solve_reactor(run, run_id="guard2").validation,
    ]

    seen = 0
    for report in reports:
        for check in report.checks:
            seen += 1
            assert check.earns_its_level, (check.name, check.to_dict())
    assert seen >= 10


# =====================================================================
# GUARD 3 — the threshold a level is judged against is not the caller's
# =====================================================================
#
# `VerificationThresholds.award` returns a level only for a domain's declared
# set. A caller who wants different numbers derives a set, gets the whole
# report -- every residual, every detail -- and gets no claim.
#
# One gate in the repository still takes bare floats:
# `src/engcore/domains/thermal/conduction1d/validation.py`, whose bytes are
# pinned by `experiments/thermal_t1/t1_config.py`. It is named below and the
# test asserts it is the ONLY one. NEEDS.md G3.1 records what migrating it
# costs.

#: Gates that judge a level against numbers a caller can still set as floats.
_FROZEN_CALLER_THRESHOLDS = (
    "src/engcore/domains/thermal/conduction1d/validation.py",
    "run_verification_gate",
)

#: Parameter names that name a threshold a verification is judged against.
#: A gate taking one of these as a float has the defect this guard removes.
_THRESHOLD_PARAMETER_MARKERS = ("_rel_tol", "_atol", "min_contraction")


def _gates_taking_bare_float_thresholds():
    """Every function in ``src`` with a float parameter that names a threshold.

    Crude on purpose. A guard that only looked at the two gates this round knew
    about would be exactly the kind of list the round exists to stop writing.
    """
    root = pathlib.Path(__file__).resolve().parent.parent / "src"
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        relative = path.relative_to(root.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = list(node.args.args) + list(node.args.kwonlyargs)
            offending = [
                argument.arg
                for argument in arguments
                if any(
                    marker in argument.arg
                    for marker in _THRESHOLD_PARAMETER_MARKERS
                )
            ]
            if offending:
                yield relative, node.name, offending


def test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against():
    """A caller who can set the tolerance has defeated the verification.

    The CSTR gate took ``invariant_rel_tol`` as a keyword argument, so a caller
    passing ``1e-3`` received a report awarding ANALYTICALLY_VERIFIED that read,
    in every field a consumer looks at, exactly like one judged against 1e-9.
    """
    offenders = [
        (path, function)
        for path, function, _ in _gates_taking_bare_float_thresholds()
    ]
    assert offenders == [_FROZEN_CALLER_THRESHOLDS], (
        "a function takes a verification threshold as a bare float: "
        + repr(list(_gates_taking_bare_float_thresholds()))
    )


def test_a_derived_threshold_set_awards_nothing():
    """The mechanism, on both domains that now use it."""
    from src.engcore.domains.electrical.dc.validation import (
        DC_CONVERGENCE_THRESHOLDS,
    )
    from src.engcore.domains.kinetics.cstr.validation import CSTR_GATE_THRESHOLDS
    from src.engcore.scientific.results.validation import ValidationLevel

    for declared, override in (
        (CSTR_GATE_THRESHOLDS, {"invariant_rel_tol": 1e-3}),
        (DC_CONVERGENCE_THRESHOLDS, {"residual_atol": 1.0}),
    ):
        assert declared.is_declared
        assert declared.award(
            ValidationLevel.NUMERICALLY_CONVERGED, earned=True
        ) is ValidationLevel.NUMERICALLY_CONVERGED

        derived = declared.derive(**override)
        assert not derived.is_declared
        assert derived.derived_from == declared.identity
        assert derived.identity != declared.identity
        assert derived.fingerprint != declared.fingerprint
        # The comparison still runs. Only the claim is withheld.
        assert derived.award(
            ValidationLevel.NUMERICALLY_CONVERGED, earned=True
        ) is None
        # And a passing comparison against the declared set is unaffected.
        assert declared.award(
            ValidationLevel.NUMERICALLY_CONVERGED, earned=False
        ) is None


def test_a_derivation_that_changes_nothing_is_not_an_override():
    """Withholding a level from a caller who changed no number would be noise."""
    from src.engcore.domains.kinetics.cstr.validation import (
        CSTR_GATE_THRESHOLDS,
        INVARIANT_REL_TOL,
    )

    same = CSTR_GATE_THRESHOLDS.derive(invariant_rel_tol=INVARIANT_REL_TOL)
    assert same is CSTR_GATE_THRESHOLDS
    assert same.is_declared


def test_a_threshold_the_gate_does_not_read_cannot_be_derived():
    """Inventing a criterion nothing evaluates is not configuration."""
    from src.engcore.domains.kinetics.cstr.validation import CSTR_GATE_THRESHOLDS
    from src.engcore.scientific.errors import ScientificValidationError

    with pytest.raises(ScientificValidationError, match="have no"):
        CSTR_GATE_THRESHOLDS.derive(a_criterion_nothing_reads=1e-3)


def test_a_non_finite_threshold_is_refused():
    """NaN makes every comparison false; infinity makes every one true."""
    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.thresholds import VerificationThresholds

    for bad in (float("nan"), float("inf")):
        with pytest.raises(ScientificValidationError, match="non-finite"):
            VerificationThresholds(
                gate_id="g", version="1", values={"rel_tol": bad}
            )


def test_widening_the_dc_residual_bound_buys_no_level():
    """End to end, on a real solve: the check passes and awards nothing."""
    from src.engcore.domains.electrical.dc import (
        DCCircuit,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
        solve_circuit,
    )
    from src.engcore.domains.electrical.dc.solver import ElectricalDCSolver
    from src.engcore.domains.electrical.dc.validation import DCValidationSettings
    from src.engcore.scientific.results.validation import (
        ValidationLevel,
        ValidationOutcome,
    )

    circuit = DCCircuit(
        circuit_id="guard3",
        nodes=(ElectricalNode("gnd", is_reference=True), ElectricalNode("n1")),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="n1",
                node_b="gnd",
                resistance=Quantity(1000.0, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="n1",
                negative_node="gnd",
                voltage=Quantity(5.0, "volt"),
            ),
        ),
    )

    honest = solve_circuit(circuit, run_id="guard3-declared")
    assert ValidationLevel.NUMERICALLY_CONVERGED in honest.validation.attained_levels

    widened = solve_circuit(
        circuit,
        run_id="guard3-widened",
        solver=ElectricalDCSolver(
            settings=DCValidationSettings(residual_atol=1.0)
        ),
    )
    check = next(
        c for c in widened.validation.checks if c.name == "linear_system_residual"
    )
    # The comparison ran and passed, and says so.
    assert check.outcome is ValidationOutcome.PASS
    assert check.residual is not None and check.tolerance is not None
    # The claim is withheld, and the report says which set it was judged against.
    assert check.establishes is None
    assert (
        ValidationLevel.NUMERICALLY_CONVERGED
        not in widened.validation.attained_levels
    )
    assert any(e.startswith("thresholds-override-of:") for e in check.evidence)


# =====================================================================
# GUARD 4 — supports() answers about the whole capability set
# =====================================================================
#
# Two adapters checked one capability and returned True; a third matched on a
# model reference and never looked at capabilities at all. The other five had
# five separate implementations of the same three comparisons, which is the
# same defect one step from happening.
#
# The comparison is `DeclaredSupport.support_gap` now, and an adapter declares
# rather than compares. `SolverRegistry.register` refuses a solver that
# overrides `supports`, so a hand-rolled answer cannot reach `resolve`.


def _every_solver():
    """Every solver class in ``src``, instantiated where it takes no arguments.

    Walking the package rather than listing: the sixth adapter is the one this
    guard is for, and a list would not contain it.
    """
    import inspect

    from src.engcore.scientific.solvers.protocol import ScientificSolver

    seen: dict[str, type] = {}
    for module_info in pkgutil.walk_packages(engcore.__path__, "src.engcore."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # pragma: no cover
            continue
        for _, value in inspect.getmembers(module, inspect.isclass):
            if not value.__module__.startswith("src.engcore."):
                continue
            if not isinstance(value, type):  # pragma: no cover
                continue
            # The Protocol itself and the base class that implements the
            # support decision are the contract, not adapters of it.
            if value is ScientificSolver or getattr(
                value, "_is_protocol", False
            ):
                continue
            if value.__name__ == "DeclaredSupport":
                continue
            required = ("identity", "capabilities", "supports", "prepare", "solve")
            if all(hasattr(value, name) for name in required):
                seen.setdefault(f"{value.__module__}.{value.__qualname__}", value)
    return seen


SOLVER_CLASSES = _every_solver()

#: The one adapter that cannot inherit the core contract: a frozen file.
_FROZEN_HANDROLLED_SUPPORT = (
    "src.engcore.domains.thermal.conduction1d.solver.Conduction1DSolver"
)


def test_the_solver_discovery_found_the_adapters():
    assert len(SOLVER_CLASSES) >= 8, sorted(SOLVER_CLASSES)
    assert _FROZEN_HANDROLLED_SUPPORT in SOLVER_CLASSES


def test_no_adapter_answers_the_support_question_for_itself():
    """Declare, do not compare — for every solver in the repository.

    A solver that implements ``supports`` is answering a question about
    capability coverage that only the core sees the whole of, and the two
    adapters that did answer it got it wrong in the same way.
    """
    from src.engcore.scientific.solvers.protocol import DeclaredSupport

    handrolled = sorted(
        name
        for name, cls in SOLVER_CLASSES.items()
        if not issubclass(cls, DeclaredSupport)
        or cls.supports is not DeclaredSupport.supports
    )
    assert handrolled == [_FROZEN_HANDROLLED_SUPPORT], handrolled


def test_the_registry_refuses_a_solver_that_decides_its_own_support():
    """The lock, not just the convention.

    ``supports`` is what ``resolve`` acts on, so the registry is where a wrong
    "yes" becomes a solve, and it is where the refusal belongs.
    """
    from src.engcore.scientific.solvers.protocol import SolverIdentity
    from src.engcore.scientific.solvers.registry import SolverRegistry

    class _HandRolled:
        identity = SolverIdentity("hand.rolled", "1.0.0")
        capabilities = frozenset()

        def supports(self, problem):
            return True

    with pytest.raises(TypeError, match="does not use the core support"):
        SolverRegistry([_HandRolled()])

    from src.engcore.scientific.solvers.protocol import DeclaredSupport

    class _Overrider(DeclaredSupport):
        identity = SolverIdentity("overrider", "1.0.0")
        capabilities = frozenset()

        def supports(self, problem):
            return True

    with pytest.raises(TypeError, match="overrides supports"):
        SolverRegistry([_Overrider()])


def _instantiate(cls):
    try:
        return cls()
    except Exception:  # pragma: no cover - a solver needing arguments
        return None


@pytest.mark.parametrize(
    "name", sorted(n for n in SOLVER_CLASSES if n != _FROZEN_HANDROLLED_SUPPORT)
)
def test_a_problem_requesting_a_superset_is_refused(name):
    """The defect itself, for every adapter, with the expectation from the record.

    The problem is built from what the solver *declares*: its own
    ``serves_capabilities``, one of its own ``served_models``, and then one
    capability it does not declare. That capability is chosen to be one no
    solver in the repository could confuse for its own, and the expectation is
    derived rather than written down, so an adapter added tomorrow is covered
    without anybody extending a list.
    """
    from src.engcore.scientific.ir.problem import ModelReference, ScientificProblem

    solver = _instantiate(SOLVER_CLASSES[name])
    if solver is None:
        pytest.skip(f"{name} needs constructor arguments")
    if not solver.capabilities:
        pytest.skip(f"{name} declares no capabilities, so nothing is a superset")

    models = tuple(
        ModelReference(model.model_id, model.version)
        for model in getattr(solver, "served_models", ())
    )
    required = frozenset(getattr(solver, "serves_capabilities", frozenset()))
    if not required:
        required = frozenset({next(iter(solver.capabilities)).name})

    exact = ScientificProblem(
        problem_id=f"{name}-exact",
        models=models,
        required_capabilities=required,
    )
    # A capability no solver here declares, so "superset" means superset.
    alien = "guard4:a_capability_no_solver_declares"
    assert alien not in {c.name for c in solver.capabilities}
    superset = ScientificProblem(
        problem_id=f"{name}-superset",
        models=models,
        required_capabilities=required | {alien},
    )

    # The exact request is served (or refused for a reason that is not the
    # capability set — an adapter may need a model this construction cannot
    # supply, and that is a different question from this one).
    gap_exact = solver.support_gap(exact)
    assert not any("does not declare" in reason for reason in gap_exact), gap_exact

    # The superset is refused, and says which capability it could not cover.
    assert not solver.supports(superset)
    assert any(
        alien in reason and "does not declare" in reason
        for reason in solver.support_gap(superset)
    ), solver.support_gap(superset)


def test_a_problem_that_asks_for_nothing_is_nobody_s():
    """The empty set is a subset of everything, which is why subset is not enough.

    Every adapter that declares what it is *for* refuses a problem that
    requires no capability at all. An adapter that only asked "is the request a
    subset of what I declare" answered yes to this, which is how a solver
    claims a problem nobody asked it to serve.
    """
    from src.engcore.scientific.ir.problem import ScientificProblem

    empty = ScientificProblem(problem_id="asks-for-nothing")
    checked = 0
    for name, cls in sorted(SOLVER_CLASSES.items()):
        solver = _instantiate(cls)
        if solver is None or not getattr(solver, "serves_capabilities", None):
            continue
        checked += 1
        assert not solver.supports(empty), name
    assert checked >= 6


# =====================================================================
# GUARD 5 — provenance cannot name what did not run
# =====================================================================
#
# This is the guard the round called the hardest to make fail-closed, and it
# is: the record is built after the fact and has no direct view of execution.
# What is enforced:
#
#   - a record carrying bindings may not name a SOLVER no binding covers
#     (a model may be named unbound -- see the test for why);
#   - `ExecutionBinding.from_execution` reads the solver identity off the
#     prepared solve, so a binding cannot name a solver that did not prepare
#     the work, and refuses a model the prepared problem does not name.
#
# What is NOT enforced: that a `RawSolverOutput` handed to `from_execution`
# came from a real solve. NEEDS.md G5.1 has what that would cost.


def test_provenance_refuses_a_solver_no_binding_covers():
    """The battery defect, in the core, as a rule.

    A solver's only job is to execute. Naming one in a record that states what
    ran is a claim that it ran, and the binding is where a record says what it
    ran.
    """
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.ir.problem import ModelReference
    from src.engcore.scientific.results.provenance import (
        ExecutionBinding,
        ProvenanceRecord,
    )
    from src.engcore.scientific.solvers.protocol import SolverIdentity

    binding = ExecutionBinding(
        model=ModelReference("m.alpha", "1.0"),
        solver=SolverIdentity("s.that.ran", "1.0"),
    )
    with pytest.raises(ScientificCoreError, match="no binding covers"):
        ProvenanceRecord(
            run_id="g5",
            solvers=(("s.that.ran", "1.0"), ("s.that.did.not", "1.0")),
            bindings=(binding,),
        )
    # The bound one alone is fine, and so is omitting the set entirely.
    assert ProvenanceRecord(
        run_id="g5b", solvers=(("s.that.ran", "1.0"),), bindings=(binding,)
    ).solvers == (("s.that.ran", "1.0"),)
    assert ProvenanceRecord(run_id="g5c", bindings=(binding,)).solvers == (
        ("s.that.ran", "1.0"),
    )


def test_a_model_may_be_named_without_a_binding_and_a_solver_may_not():
    """The asymmetry is the point, not an oversight.

    A model can be named by a result without any solver having executed it: its
    assumptions travel with the record and its validity was assessed. That is
    partial knowledge and it is honest. A solver has nothing to contribute
    except execution, so naming one says it executed.
    """
    from src.engcore.scientific.ir.problem import ModelReference
    from src.engcore.scientific.results.provenance import (
        ExecutionBinding,
        ProvenanceRecord,
    )
    from src.engcore.scientific.solvers.protocol import SolverIdentity

    record = ProvenanceRecord(
        run_id="g5d",
        models=(("m.alpha", "1.0"), ("m.assessed.only", "1.0")),
        bindings=(
            ExecutionBinding(
                model=ModelReference("m.alpha", "1.0"),
                solver=SolverIdentity("s", "1.0"),
            ),
        ),
    )
    assert len(record.models) == 2
    assert record.executed_models == (("m.alpha", "1.0"),)
    assert record.bindings_for_model("m.assessed.only") == ()


def test_a_binding_from_an_execution_cannot_name_another_solver():
    """The identity is read off the prepared solve, not accepted as an argument."""
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.ir.problem import ModelReference, ScientificProblem
    from src.engcore.scientific.results.provenance import ExecutionBinding
    from src.engcore.scientific.solvers.protocol import (
        ConvergenceState,
        PreparedSolve,
        RawSolverOutput,
        SolverIdentity,
    )

    problem = ScientificProblem(
        problem_id="p", models=(ModelReference("m.alpha", "1.0"),)
    )
    prepared = PreparedSolve(
        problem=problem, solver=SolverIdentity("s.that.ran", "1.0")
    )
    raw = RawSolverOutput(convergence=ConvergenceState.NOT_APPLICABLE)

    binding = ExecutionBinding.from_execution(
        prepared, raw, model=ModelReference("m.alpha", "1.0")
    )
    assert binding.solver.key == ("s.that.ran", "1.0")

    # A model the problem was not about cannot be attributed this execution.
    with pytest.raises(ScientificCoreError, match="does not name model"):
        ExecutionBinding.from_execution(
            prepared, raw, model=ModelReference("m.unrelated", "1.0")
        )

    # And neither object may be something other than what prepare/solve return.
    with pytest.raises(ScientificCoreError, match="PreparedSolve"):
        ExecutionBinding.from_execution(
            object(), raw, model=ModelReference("m.alpha", "1.0")
        )
    with pytest.raises(ScientificCoreError, match="RawSolverOutput"):
        ExecutionBinding.from_execution(
            prepared, object(), model=ModelReference("m.alpha", "1.0")
        )


def test_the_battery_march_runs_the_solver_it_names():
    """The live case. Before this, provenance named a solver that did nothing.

    ``run_self_heating_discharge`` called ``evaluate_step`` directly, so
    ``BatteryCellSolver.validate`` never ran, its three checks reached no report
    anywhere, and the transport still named that solver among the participants.
    """
    from src.engcore.domains.battery import models as bmdl
    from src.engcore.domains.thermal_models import lumped as lump

    from tests.mcp.test_battery_boundary import example_battery_payload
    from src.engcore.mcp.battery import run_battery_case

    outcome = run_battery_case(example_battery_payload())
    march, report = outcome.run, outcome.report

    # Every binding was produced by an execution, and covers both sub-solvers.
    assert march.bindings
    bound_solvers = {b.solver.key for b in march.bindings}
    assert len(bound_solvers) == 2
    bound_models = {b.model.key for b in march.bindings}
    assert {m.key for m in bmdl.BATTERY_MODELS} <= bound_models
    assert lump.LUMPED_CAPACITY_MODEL.key in bound_models

    # The provenance derives from them and names no other solver.
    assert report.provenance.solvers == tuple(sorted(bound_solvers))
    assert report.provenance.executed_solvers == report.provenance.solvers
    # Every named solver is one a recorded execution is attributed to.
    assert set(report.provenance.solvers) <= {
        b.solver.key for b in report.provenance.bindings
    }

    # The cell solver's three checks now exist and reach the report.
    cell_checks = {c.name for c in march.steps[-1].cell_validation.checks}
    assert cell_checks == {
        "metric_dimensions",
        "coulomb_balance_residual",
        "rint_terminal_residual",
    }
    assert cell_checks <= {c.name for c in report.validation}


def test_every_marched_step_carries_its_own_cell_report():
    """Not just the last one: a check that stopped passing mid-march is a finding."""
    from tests.mcp.test_battery_boundary import example_battery_payload
    from src.engcore.mcp.battery import run_battery_case

    march = run_battery_case(example_battery_payload()).run
    assert len(march.steps) > 1
    for step in march.steps:
        assert step.cell_validation.checks, step.index
        assert step.thermal_validation.checks, step.index


# =====================================================================
# GUARD 6 — a missing fingerprint is a refusal
# =====================================================================
#
# `if declared and declared != actual` waves through a problem carrying no
# fingerprint at all: an integrity check that refuses the paired records which
# disagree, and passes the unpaired one it exists for.

#: Sites that still compare "if it is there", with why each is allowed to.
#:
#: Only two, and they are allowed for opposite reasons. Everything else that
#: had this shape was made strict: the CSTR pairing check, and the campaign
#: event log's head digest -- which was the same defect in a third place and
#: was not on this round's list.
_PERMISSIVE_BY_EXCEPTION = {
    # FROZEN. `verify_problem_matches_slab` still reads
    # `if declared and declared != actual`, so a slab problem carrying no
    # fingerprint passes it. The file is byte-pinned by
    # `experiments/thermal_t1/t1_config.py` and this round may not edit it.
    # Its two callers outside that file go through the core's strict rule
    # first, so only the path through the pinned solver is still open.
    # NEEDS.md G6.1.
    "src/engcore/domains/thermal/conduction1d/problem.py",
    # REVIEWED AND CORRECT, which is a different thing from unfixed.
    # `ValidationReport.from_dict` cross-checks a serialized `attained_levels`
    # against the levels recomputed from the checks. That field is advisory
    # and derived: the report's levels come from its checks whether the key is
    # present or not, so an absent key withholds no guarantee and forges
    # nothing. Absence here is a payload that omitted a derived view, not an
    # integrity question left unanswered.
    "src/engcore/scientific/results/validation.py",
}


def test_no_verifier_still_treats_an_absent_fingerprint_as_a_match():
    """Swept over ``src``, not over the two sites this round happened to know.

    The pattern is ``if <name> and <name> != ...`` guarding a raise -- the
    "compare it if it is there" shape. It is the shape, not the variable name,
    that makes it wrong.
    """
    import io
    import re
    import tokenize

    def code_only(text: str) -> str:
        """The source with every string literal and comment removed.

        Necessary rather than fastidious: several modules in this repository
        quote the wrong pattern in prose in order to explain why it is wrong,
        and a search over raw text reports every one of them as an offender.
        """
        kept: list[str] = []
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            kept.append(token.string)
        return " ".join(kept)

    root = pathlib.Path(__file__).resolve().parent.parent / "src"
    permissive = re.compile(
        r"if\s+(\w*declared\w*|\w*expected\w*)\s+and\s+\1\s*!="
    )
    offenders = sorted(
        path.relative_to(root.parent).as_posix()
        for path in root.rglob("*.py")
        if permissive.search(code_only(path.read_bytes().decode("utf-8")))
    )
    assert set(offenders) == _PERMISSIVE_BY_EXCEPTION, sorted(
        set(offenders) ^ _PERMISSIVE_BY_EXCEPTION
    )


def test_the_core_refuses_a_problem_that_declares_no_fingerprint():
    """Absence is an unanswered question, not an answer that happens to match."""
    from src.engcore.scientific.errors import InvalidScientificProblem
    from src.engcore.scientific.ir.fingerprints import require_matching_fingerprint

    problem = ScientificProblem(problem_id="unpaired", metadata={})
    with pytest.raises(InvalidScientificProblem, match="declares no"):
        require_matching_fingerprint(
            problem=problem,
            key="artifact_fingerprint",
            actual="abc123",
            error=InvalidScientificProblem,
            subject="artifact",
        )

    # An empty string is absence too: a builder that wrote the key and had
    # nothing to write is not a builder that answered.
    blank = ScientificProblem(
        problem_id="blank", metadata={"artifact_fingerprint": ""}
    )
    with pytest.raises(InvalidScientificProblem, match="declares no"):
        require_matching_fingerprint(
            problem=blank,
            key="artifact_fingerprint",
            actual="abc123",
            error=InvalidScientificProblem,
            subject="artifact",
        )

    # A mismatch is still a mismatch, and a match still returns.
    paired = ScientificProblem(
        problem_id="paired", metadata={"artifact_fingerprint": "abc123"}
    )
    require_matching_fingerprint(
        problem=paired,
        key="artifact_fingerprint",
        actual="abc123",
        error=InvalidScientificProblem,
        subject="artifact",
    )
    with pytest.raises(InvalidScientificProblem, match="different physical"):
        require_matching_fingerprint(
            problem=paired,
            key="artifact_fingerprint",
            actual="def456",
            error=InvalidScientificProblem,
            subject="artifact",
        )


def test_the_cstr_domain_refuses_an_unfingerprinted_problem():
    """The live case, end to end, in the domain that failed open."""
    from src.engcore.domains.kinetics.cstr.errors import ReactorConfigurationError
    from src.engcore.domains.kinetics.cstr.problem import (
        build_cstr_problem,
        verify_problem_matches_run,
    )
    from tests.domains.kinetics.test_cstr_applicability import reactor

    run = reactor()
    honest = build_cstr_problem(run, problem_id="g6-honest")
    verify_problem_matches_run(honest, run)  # returns

    stripped = ScientificProblem.from_dict(
        {
            **honest.to_dict(),
            "metadata": {
                key: value
                for key, value in honest.metadata.items()
                if key != "physics_fingerprint"
            },
        }
    )
    with pytest.raises(ReactorConfigurationError, match="declares no"):
        verify_problem_matches_run(stripped, run)


def test_the_non_frozen_conduction_paths_refuse_an_unfingerprinted_problem():
    """The frozen verifier is permissive; the callers outside it are not."""
    from src.engcore.domains.thermal.conduction1d.errors import (
        SlabConfigurationError,
    )
    from src.engcore.domains.thermal_models.conduction1d_bulk import (
        _require_slab_fingerprint,
    )
    from src.engcore.domains.thermal.conduction1d.problem import (
        build_conduction_problem,
        verify_problem_matches_slab,
    )
    from tests.domains.thermal.test_conduction1d import make_slab

    slab = make_slab()
    honest = build_conduction_problem(slab)
    stripped = ScientificProblem.from_dict(
        {
            **honest.to_dict(),
            "metadata": {
                key: value
                for key, value in honest.metadata.items()
                if key != "slab_fingerprint"
            },
        }
    )

    # The frozen verifier still passes it. Named, not worked around.
    verify_problem_matches_slab(stripped, slab)

    # The non-frozen path does not.
    with pytest.raises(SlabConfigurationError, match="declares no"):
        _require_slab_fingerprint(stripped, slab)


def test_the_campaign_event_log_refuses_a_payload_with_no_head_digest():
    """The same defect in a third place, found by the sweep rather than the round.

    ``CampaignEventLog.from_dict`` compared ``if declared and declared !=
    log.head_digest``, so a stored log carrying no head digest reloaded with
    its chain unchecked -- which is the one payload whose chain nothing has
    verified. A truncation, a hand-edited record and a writer that died between
    the events and the digest all arrive in exactly that shape.
    """
    from src.engcore.sria.campaign.events import (
        CampaignEventLog,
        CampaignEventType,
        ChainBroken,
    )

    empty = CampaignEventLog(run_id="g6-empty")
    # An empty chain has no digest and that is a true statement, not a missing
    # one -- so it is not what the refusal is about.
    assert empty.head_digest == ""
    assert CampaignEventLog.from_dict(empty.to_dict()).head_digest == ""

    log = CampaignEventLog(run_id="g6-log")
    log.append(next(iter(CampaignEventType)), iteration=0, payload={"n": 1})
    stored = log.to_dict()
    assert stored["head_digest"]
    assert CampaignEventLog.from_dict(stored).head_digest == log.head_digest

    with pytest.raises(ChainBroken, match="no head digest"):
        CampaignEventLog.from_dict(
            {k: v for k, v in stored.items() if k != "head_digest"}
        )


# =====================================================================
# GUARD 7 — a non-finite provider number cannot pass admission
# =====================================================================
#
# Every admission gate is a tolerance comparison, and `abs(nan - x) > tol` is
# False. A provider returning NaN therefore disagreed with nothing and walked
# through a gate written to catch exactly the provider that disagrees.
#
# The finiteness rule is `engcore.scientific.solvers.admission`, in the core,
# before any comparison -- because a comparison is the one thing that cannot
# detect this.


def test_a_tolerance_comparison_cannot_see_a_non_finite_value():
    """The arithmetic the whole guard rests on, stated rather than assumed."""
    import math

    nan, inf = float("nan"), float("inf")
    tol = 1e-9
    # The exact shape every admission gate in this repository is written in.
    assert not (abs(nan - 1.0) > tol)
    assert not (abs(inf - inf) > tol)
    assert not (nan < -tol)  # and the sign check underneath is one too
    assert math.isnan(abs(nan - 1.0))


def test_the_core_admission_layer_refuses_before_it_compares():
    """Finiteness first. Ordering is the property, not an early-out."""
    from src.engcore.scientific.solvers.admission import (
        require_agreement,
        require_finite,
    )

    class _Refused(Exception):
        pass

    nan, inf = float("nan"), float("inf")

    require_finite({"a": 1.0, "b": -2.5}, error=_Refused, source="probe")
    for bad in (nan, inf, -inf):
        with pytest.raises(_Refused, match="non-finite"):
            require_finite({"a": 1.0, "b": bad}, error=_Refused, source="probe")

    # Agreement: the honest pair passes, the disagreeing pair is refused with
    # the caller's own message, and the non-finite pair is refused as
    # non-finite -- not silently admitted, which is what the bare comparison did.
    require_agreement(
        actual=1.0, expected=1.0, atol=1e-9, rtol=1e-9,
        error=_Refused, detail="they agree",
    )
    with pytest.raises(_Refused, match="they disagree"):
        require_agreement(
            actual=1.0, expected=2.0, atol=1e-9, rtol=1e-9,
            error=_Refused, detail="they disagree",
        )
    with pytest.raises(_Refused, match="non-finite"):
        require_agreement(
            actual=nan, expected=1.0, atol=1e-9, rtol=1e-9,
            error=_Refused, detail="would have been admitted",
        )
    # And an operand behind the comparison, which a gate looking only at its
    # own two numbers would have missed.
    with pytest.raises(_Refused, match="non-finite"):
        require_agreement(
            actual=1.0, expected=1.0, atol=1e-9, rtol=1e-9,
            error=_Refused, detail="derived from an infinity",
            operands={"v_drop": inf},
        )


def test_the_element_gate_refuses_every_non_finite_shape():
    """The gate itself, over the shapes that used to pass it."""
    from src.engcore.domains.electrical.ngspice import (
        NgspiceDCSolver,
        NgspiceExecutionFailure,
    )

    nan, inf = float("nan"), float("inf")
    honest = dict(
        component_id="R1", v_drop=1.0, current=1e-3, power=1e-3, ohms=1000.0
    )
    NgspiceDCSolver._admit_element_power(**honest)  # returns

    for label, override in (
        ("nan power", {"power": nan}),
        ("nan current and power", {"current": nan, "power": nan}),
        ("inf power", {"power": inf}),
        ("everything infinite", {"v_drop": inf, "current": inf, "power": inf}),
        ("nan voltage drop", {"v_drop": nan}),
        ("nan resistance", {"ohms": nan}),
    ):
        with pytest.raises(NgspiceExecutionFailure, match="non-finite"):
            NgspiceDCSolver._admit_element_power(**{**honest, **override})


# ---------------------------------------------------------------------
# GUARD 7, enforced: the admission layer is the only route in
# ---------------------------------------------------------------------
#
# The rule above lives in `engcore.scientific.solvers.admission` and one
# adapter uses it. What follows is the floor underneath, on the object every
# adapter must return: a solve reporting CONVERGED or NOT_APPLICABLE cannot
# carry a non-finite value or residual. An adapter that skips the admission
# layer therefore produces NOTHING rather than something unchecked.


def test_a_succeeded_solve_cannot_return_a_number_that_is_not_a_number():
    """The floor, on the one object no adapter can avoid constructing.

    There is no route from a backend into a ``ScientificResult`` that does not
    pass through this constructor: ``extract_metrics`` reads this record, and a
    value invented after it is not a value the backend produced.
    """
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.solvers.protocol import (
        ConvergenceState,
        RawSolverOutput,
    )

    nan, inf = float("nan"), float("inf")

    for state in (ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE):
        for payload in (
            {"values": {"u": nan}},
            {"values": {"u": inf}},
            {"values": {"u": -inf}},
            {"residuals": {"r": nan}},
        ):
            with pytest.raises(ScientificCoreError, match="non-finite"):
                RawSolverOutput(convergence=state, **payload)
        # The same record with finite numbers is fine.
        RawSolverOutput(convergence=state, values={"u": 1.0}, residuals={"r": 0.0})


def test_a_failed_solve_keeps_the_sanctioned_home_for_non_finite_values():
    """The scope is the design, not an oversight.

    A diverged solve genuinely produces NaN, and a record that could not say so
    would force every adapter to launder its own failure. What is refused is a
    solve claiming to have completed *and* returning a non-number, which is two
    stories at once.
    """
    from src.engcore.scientific.solvers.protocol import (
        ConvergenceState,
        RawSolverOutput,
    )

    nan = float("nan")
    for state in (
        ConvergenceState.NOT_CONVERGED,
        ConvergenceState.MAX_ITERATIONS,
        ConvergenceState.DIVERGED,
        ConvergenceState.FAILED,
    ):
        raw = RawSolverOutput(convergence=state, values={"u": nan})
        assert raw.values["u"] != raw.values["u"]  # still NaN, still recorded
        assert not raw.succeeded


def test_an_adapter_that_skips_the_admission_layer_produces_nothing():
    """The property the enforcement is for, written as the adapter that skips it.

    This is the next provider adapter, in miniature: it fetches numbers from
    somewhere outside itself and hands them straight to ``RawSolverOutput``
    without going near ``engcore.scientific.solvers.admission``. It gets no
    result -- not a result carrying a NaN, and not a result whose validation
    checks all passed because every comparison against a NaN is False.
    """
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.solvers.protocol import (
        ConvergenceState,
        DeclaredSupport,
        PreparedSolve,
        RawSolverOutput,
        SolverIdentity,
    )

    class _ForgetfulProviderAdapter(DeclaredSupport):
        """Reaches an external provider and admits nothing."""

        identity = SolverIdentity("forgetful.provider", "1.0.0")
        capabilities = frozenset()

        def prepare(self, problem):
            return PreparedSolve(problem=problem, solver=self.identity)

        def solve(self, prepared):
            # What "the provider said". No admission layer anywhere.
            from_provider = {"v(n1)": float("nan"), "@r1[p]": 1.0}
            return RawSolverOutput(
                convergence=ConvergenceState.CONVERGED, values=from_provider
            )

    problem = ScientificProblem(problem_id="forgetful")
    adapter = _ForgetfulProviderAdapter()
    with pytest.raises(ScientificCoreError, match="non-finite"):
        adapter.solve(adapter.prepare(problem))


def test_the_admission_layer_is_still_the_route_that_says_what_went_wrong():
    """Enforcement is the floor; the layer is the door, and both are wanted.

    The core's refusal is about a *record* and arrives as a
    ``ScientificCoreError``. The truth at a provider boundary is that the
    provider ran and did not deliver what was asked, which is the adapter's own
    failure category and the one its callers already catch. The adapter that
    exists admits first, so that is what a caller sees.
    """
    from src.engcore.domains.electrical import ngspice as ng
    from src.engcore.scientific.errors import ScientificCoreError

    source = pathlib.Path(ng.__file__).read_bytes().decode("utf-8")
    # Admission happens where the provider's numbers first exist, not only at
    # the element gate that sees three channels of one resistor.
    assert "require_finite(" in source
    assert source.index("require_finite(") < source.index("_admit_element_power")

    # And the refusal a caller sees is the adapter's, not the core's.
    import os
    import sys

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests",
        "nonfinite_provider.py",
    )
    solver = ng.NgspiceDCSolver(
        invocation=ng.NgspiceInvocation(
            command=(sys.executable, script, "--nan")
        )
    )
    from src.engcore.domains.electrical.dc import (
        DCCircuit,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )

    circuit = DCCircuit(
        circuit_id="guard7-enforced",
        nodes=(ElectricalNode("gnd", is_reference=True), ElectricalNode("n1")),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="n1",
                node_b="gnd",
                resistance=Quantity(1000.0, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="n1",
                negative_node="gnd",
                voltage=Quantity(5.0, "volt"),
            ),
        ),
    )
    with pytest.raises(ng.NgspiceExecutionFailure) as refusal:
        ng.solve_circuit_with_ngspice(
            circuit, run_id="guard7-enforced", solver=solver
        )
    assert not isinstance(refusal.value, ScientificCoreError)
    assert "non-finite" in str(refusal.value)
