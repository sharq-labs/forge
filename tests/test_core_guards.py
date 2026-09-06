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
