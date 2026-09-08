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
import sys

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

#: Modules the walk could not import, and what stopped each.
#:
#: Recorded rather than discarded. Every discovery below is a sweep, and a
#: sweep that loses part of its population reports a clean tree it did not
#: read -- the failure mode `mutation_guards.py` exists for, in the machinery
#: doing the checking. The floor that was supposed to notice could not: with
#: `assert len(MODELS) >= 14` against sixteen models, one unimportable leaf
#: dropped the sweep to fourteen, silently removed twelve parametrized guard
#: instances, and the assertion whose own docstring reads "a guard over an
#: empty set passes and proves nothing" passed.
MODEL_DISCOVERY_FAILURES: dict[str, str] = {}


def _record_walk_failure(name: str) -> None:
    """`pkgutil`'s own error hook, which otherwise swallows ImportError.

    Re-raises anything that is not an ImportError, which is what
    `walk_packages` does with no hook supplied, so a broken module still
    fails loudly here rather than quietly narrowing the sweep.
    """
    exception = sys.exc_info()[1]
    MODEL_DISCOVERY_FAILURES[name] = f"{type(exception).__name__}: {exception}"
    if not isinstance(exception, ImportError):
        raise  # pragma: no cover - preserves walk_packages' own behaviour


def _every_model() -> tuple[ScientificModelDefinition, ...]:
    """Every model record reachable from ``engcore``, by import rather than list.

    A module-level constant in a package nobody imported here would be missed,
    so this walks the package rather than reading a registry: the registries are
    built by functions, one per domain, and a domain that forgot to write one
    would be exactly the domain worth testing.
    """
    found: dict[tuple[str, str], ScientificModelDefinition] = {}
    for module_info in pkgutil.walk_packages(
        engcore.__path__, "src.engcore.", onerror=_record_walk_failure
    ):
        try:
            module = importlib.import_module(module_info.name)
        except Exception as exc:  # an unimportable module is a different
            # test's failure -- but it is this one's population, so it is
            # counted here instead of vanishing.
            MODEL_DISCOVERY_FAILURES[module_info.name] = (
                f"{type(exc).__name__}: {exc}"
            )
            continue
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

#: What the repository contains, as counted by the walk above.
#:
#: **Exact, not a floor, and that is the whole point.** A floor fails on a
#: loss only if the loss is bigger than its slack, and it never fails on an
#: addition at all -- so a model that lands without being covered here is
#: indistinguishable from one that was. An exact count is wrong in both
#: directions and has to be updated deliberately, which is the moment somebody
#: looks at the new record. `tests/test_pin_portability.py:_pinned_paths` is
#: the pattern: derive the population, then assert its size.
EXPECTED_MODELS = 16
EXPECTED_RESERVING_MODELS = 15
EXPECTED_CONDITION_NAMES = 64
EXPECTED_RESERVED_NAMES = 46


def test_the_discovery_found_exactly_the_repository():
    """A guard over an empty set passes and proves nothing -- and so does a
    guard over most of one.

    Four numbers, all exact. If a model, a condition or a reserved name is
    added, this fails and names what changed; if one is lost -- to a rename, a
    move, or a module that stopped importing -- it fails the same way. Neither
    direction can be reached by accident, and the assertion message carries the
    import failures so a loss names its own cause instead of being a number
    that got smaller.
    """
    assert not MODEL_DISCOVERY_FAILURES, (
        "the model walk could not import these, so every guard below ran over "
        "a smaller repository than it claims to cover: "
        f"{MODEL_DISCOVERY_FAILURES}"
    )
    assert len(MODELS) == EXPECTED_MODELS, sorted(m.model_id for m in MODELS)
    assert len(RESERVING) == EXPECTED_RESERVING_MODELS, sorted(
        m.model_id for m in RESERVING
    )
    domains = {m.domain for m in MODELS}
    assert {"electrical", "thermal", "battery", "kinetics"} == domains

    condition_names = sum(len(m.validity.context_keys) for m in MODELS)
    reserved_names = sum(len(m.derived_quantities) for m in MODELS)
    assert condition_names == EXPECTED_CONDITION_NAMES
    assert reserved_names == EXPECTED_RESERVED_NAMES


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
        "dissipated_power_utilization",
        "peukert_capacity_ratio",
        "reduced_debye_temperature",
    } <= reserved


def test_no_model_declares_a_quantity_its_own_domain_derives():
    """The census, over every model, of the door the constructors leave open.

    ``ScientificModelDefinition`` refuses a condition reading a name that is
    neither reserved nor a declared input. ``ValidityDomain`` refuses a
    reserved name that no condition reads. Between them every condition name
    is classified -- and a domain that declares its own derived quantity as a
    model **input** satisfies both rules, because the name is then genuinely
    declared. That is the fifth instance of the forgery wearing the one
    disguise the two constructors cannot see through.

    This measures the population rather than asserting a list: every condition
    name in the repository, in one of exactly two buckets. It is what makes
    the claim "there is no instance today" a measurement.

    ``temperature`` is the case that shows why the obvious cheap test -- no
    reserved name may be any model's declared input -- would be wrong. The two
    material models both reserve it *and* declare it, and that is correct:
    ``resistance_validity_context`` assembles it, the record documents that
    the model consumes a temperature, and ``validity_context(reserved=...)``
    refuses a caller parameter of that name. Reserved-and-declared is safe;
    declared-and-not-reserved is the defect, and only the second is asserted.
    """
    classified = 0
    for model in MODELS:
        inputs = {spec.name for spec in model.inputs}
        for name in sorted(model.validity.context_keys):
            assert name in model.derived_quantities or name in inputs, (
                model.model_id,
                name,
            )
            classified += 1
    assert classified == EXPECTED_CONDITION_NAMES


def test_a_derived_quantity_declared_as_an_input_is_refused_at_assessment():
    """And the refusal, for the sixth domain that gets there before the census.

    The census above is a fact about today. This is the rule, and it lives on
    ``DomainValidityContext.assess`` rather than in a sweep for the reason
    GUARD 1 moved into the core in the first place: a sweep over the five
    domains that exist is a guard over what somebody remembered.

    The model below is exactly the shape a domain reaches by accident --
    ``forged_group`` is read by a condition and declared as a parameter, so
    the record constructs, imports and passes every guard above it. Handing
    the assembler's own value for it to ``assess`` used to drop the value
    silently, after which the condition read the caller's half instead.
    """
    from src.engcore.domains.derived_context import DomainValidityContext
    from src.engcore.scientific.models.definition import (
        InputSourceKind,
        ModelInputSpec,
        RangeCondition,
        ValidityDomain,
    )

    model = ScientificModelDefinition(
        model_id="synthetic.sixth_domain",
        exclusions=(),
        excludes_nothing_because=(
            "a test fixture: it stands for a model record's shape and "
            "represents no physical process"
        ),
        version="0.1.0",
        name="A domain that declared its derived quantity",
        domain="synthetic",
        inputs=(
            ModelInputSpec(
                name="forged_group",
                source_kind=InputSourceKind.PARAMETER,
                unit_exemplar="dimensionless",
            ),
        ),
        validity=ValidityDomain(
            conditions=(
                RangeCondition(
                    name="forged_group",
                    maximum=Quantity(1.0, "dimensionless"),
                ),
            ),
        ),
    )
    # It constructs. That is the point: nothing before this refuses it.
    assert model.validity.context_keys == frozenset({"forged_group"})
    assert model.derived_quantities == frozenset()

    context = DomainValidityContext(
        declared={},
        assembled={"forged_group": Quantity(0.5, "dimensionless")},
    )
    with pytest.raises(InvalidScientificProblem, match="forged_group"):
        context.assess(model)


def test_the_refusal_does_not_fire_on_another_model_s_business():
    """The narrowness of the rule above, asserted rather than assumed.

    One domain assembles once for every model it serves -- the four battery
    models reserve four different subsets of one assembly -- so an assembled
    name a model's conditions never read must still be dropped silently. A
    refusal that could not tell the two apart would break every multi-model
    domain in the repository, which is a louder failure than the one it fixes
    and would have been found immediately; this is here so that the day it is
    made narrower by mistake, it is found immediately too.
    """
    from src.engcore.domains.derived_context import DomainValidityContext

    model = next(m for m in RESERVING if m.model_id == "electrical.dc.kcl")
    context = DomainValidityContext(
        declared={},
        assembled={
            "lumped_electrical_length": Quantity(0.0, "dimensionless"),
            "a_name_another_model_reserves": Quantity(1.0, "dimensionless"),
        },
    )
    assessment = context.assess(model)
    assert assessment.satisfied == ("lumped_electrical_length",)


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
            # Positional arguments count. This sweep read `node.keywords`
            # alone and was therefore narrower than the rule it audits: three
            # constructions written positionally were invisible to it, and the
            # enforced constructor found them at runtime instead. A sweep that
            # cannot see a construction cannot report it.
            _FIELDS = (
                "name", "outcome", "detail", "establishes",
                "residual", "tolerance", "evidence",
            )
            kwargs = {k.arg: k.value for k in node.keywords}
            for _index, _arg in enumerate(node.args):
                if _index < len(_FIELDS):
                    kwargs.setdefault(_FIELDS[_index], _arg)

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
    # No exception. There was exactly one -- `dimensional_consistency` in the
    # byte-pinned conduction1d tree, an unconditional PASS carrying
    # DIMENSIONALLY_VALID with nothing compared -- and the thermal re-freeze
    # replaced it with a comparison against the model record. The sweep is now
    # clean, which is what let this rule move into `ValidationCheck` itself.
    assert offenders == [], (
        "a validation check claims a level with no residual, no tolerance and "
        "no reference: " + repr(offenders)
    )


def test_the_rule_itself_is_what_that_audit_applied():
    """The rule, exercised directly, so the audit above is not the rule.

    **It is a refusal now, not a property to consult.** Every case that used to
    read ``assert not check(...).earns_its_level`` is a case that can no longer
    be constructed, so it is asserted as the exception it now raises. That is
    the whole of what GUARD 2 becoming enforced means: a claimed level stopped
    being a value a sweep looks for and became one nothing can build.
    """
    import pytest

    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationLevel,
        ValidationOutcome,
    )

    def check(**kwargs):
        return ValidationCheck(name="c", outcome=ValidationOutcome.PASS, **kwargs)

    def refused(**kwargs):
        with pytest.raises(ScientificValidationError, match="no evidence"):
            check(**kwargs)

    # Claiming nothing is always honest.
    assert check().earns_its_level
    # A level with nothing behind it is not, and cannot be built.
    refused(establishes=ValidationLevel.DIMENSIONALLY_VALID)
    # A residual with no bound is a number nobody bounded.
    refused(
        establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-12
    )
    # A bound with nothing measured against it is not a comparison either.
    refused(
        establishes=ValidationLevel.NUMERICALLY_CONVERGED, tolerance=1e-9
    )
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
    # Exact. `>= 10` against the thirteen these two solves produce would have
    # let three checks stop being emitted -- which is how a check stops being
    # audited without anyone deciding that it should.
    assert seen == 13, [c.name for r in reports for c in r.checks]


# =====================================================================
# GUARD 3 — the threshold a level is judged against is not the caller's
# =====================================================================
#
# `VerificationThresholds.award` returns a level only for a domain's declared
# set. A caller who wants different numbers derives a set, gets the whole
# report -- every residual, every detail -- and gets no claim.
#
# One gate in the repository still takes bare floats:
# `src/engcore/domains/thermal/conduction1d/validation.py`, whose bytes were
# pinned by `experiments/thermal_t1/t1_config.py`. The thermal re-freeze
# migrated it to `CONDUCTION_GATE_THRESHOLDS`, so the sweep below now expects
# no offenders at all.

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
    # No exception. `run_verification_gate` took `min_contraction` and
    # `analytic_rel_tol` as bare floats, and both gated a level; it now takes a
    # `VerificationThresholds` and routes both through `award`, so a caller's
    # numbers move the verdict and buy nothing.
    assert offenders == [], (
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
    for module_info in pkgutil.walk_packages(
        engcore.__path__, "src.engcore.", onerror=_record_walk_failure
    ):
        try:
            module = importlib.import_module(module_info.name)
        except Exception as exc:  # counted, for the reason MODEL_DISCOVERY_
            # FAILURES exists: a sweep that quietly loses a module reports a
            # clean tree it did not read.
            MODEL_DISCOVERY_FAILURES[module_info.name] = (
                f"{type(exc).__name__}: {exc}"
            )
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

#: Exact, for the reason EXPECTED_MODELS is. A tenth adapter that lands
#: without being covered by the guards below should fail here on the day it
#: lands, and `>= 8` could not tell that from the nine there are.
EXPECTED_SOLVER_CLASSES = 9


def test_the_solver_discovery_found_the_adapters():
    assert not MODEL_DISCOVERY_FAILURES, MODEL_DISCOVERY_FAILURES
    assert len(SOLVER_CLASSES) == EXPECTED_SOLVER_CLASSES, sorted(SOLVER_CLASSES)
    # The adapter that used to be the exception here, still discovered -- it
    # inherits `DeclaredSupport` now rather than answering for itself.
    assert (
        "src.engcore.domains.thermal.conduction1d.solver.Conduction1DSolver"
        in SOLVER_CLASSES
    )


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
    # No exception. `Conduction1DSolver` was the fifth copy of the three
    # comparisons `DeclaredSupport` makes; it declares them now.
    assert handrolled == [], handrolled


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
    "name", sorted(SOLVER_CLASSES)
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
#: One, and it is not a gap. The conduction1d slab verifier used to be the
#: other, held open only by the freeze; the thermal re-freeze routed it through
#: the core's strict rule and it is gone from this set.
_PERMISSIVE_BY_EXCEPTION = {
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


def test_the_conduction_slab_verifier_refuses_an_unfingerprinted_problem():
    """It used to pass one, and that was the whole of G6.1.

    ``verify_problem_matches_slab`` read ``if declared and declared != actual``,
    so the one case where nothing had said what the problem describes was the
    one case nothing was checked. Two modules outside the freeze carried a
    strict shim in front of it for that reason; the thermal re-freeze routed the
    verifier itself through the core rule and both shims are gone, so this test
    now exercises the real thing rather than the workaround.
    """
    from src.engcore.domains.thermal.conduction1d.errors import (
        SlabConfigurationError,
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

    # An honest pairing still passes.
    verify_problem_matches_slab(honest, slab)

    # An absent fingerprint is an unanswered question, not an answer.
    with pytest.raises(SlabConfigurationError, match="declares no"):
        verify_problem_matches_slab(stripped, slab)

    # And the shims that stood in front of it are gone rather than kept.
    import src.engcore.domains.thermal_models.conduction1d_bulk as bulk
    import src.engcore.domains.thermal_models.conduction1d_schemes as schemes

    assert not hasattr(bulk, "_require_slab_fingerprint")
    assert not hasattr(schemes, "_require_slab_fingerprint")


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


# =====================================================================
# GUARD 8 — the units backend cannot be changed by a run
# =====================================================================
#
# `Quantity` is a magnitude and a unit *string*. It is serialized as a string,
# compared across runs as a string, and read back by someone who was not there
# for the run that wrote it. So the meaning of "volt" is not run-scoped state,
# and a registry a run could edit is a registry in which run A silently changes
# run B's arithmetic — the same class of defect as a fingerprint collision,
# because it produces a wrong number with a correct-looking record around it.
#
# The choice made here is refusal rather than a registry per run, and the
# reason is in `registry()`'s own docstring: per-run isolation would trade a
# mutation hazard for an interpretation hazard, letting "volt" mean one thing
# in the run that wrote a record and another in the run that reads it, with
# nothing in the record able to say which.
#
# Two halves, and they are not equally strong. The refusal is ENFORCED: it is
# on the registry object itself, so there is no route through pint's API or
# through an attribute that does not hit it. The fingerprint is a DETECTOR for
# the one surface refusal cannot reach — a caller writing into the backend's
# own dictionaries — and it detects when it is called. Both are exercised
# below; neither is described as the other.

def _sealed_registry():
    from src.engcore.scientific.units import registry

    return registry()


def test_every_route_pint_offers_for_changing_the_registry_is_refused():
    """The enumeration, not a sample of it.

    Every mutating callable the sealed registry names, called on the live
    registry, must refuse — including through the back-reference a pint
    quantity carries to the registry that made it, which is the route a proxy
    would have left open.
    """
    from src.engcore.scientific.errors import UnitRegistryMutationError
    from src.engcore.scientific.units.quantity import _SEALED_MUTATORS

    registry = _sealed_registry()
    assert len(_SEALED_MUTATORS) >= 15

    unreached = []
    for operation in _SEALED_MUTATORS:
        if not hasattr(registry, operation):
            continue
        try:
            getattr(registry, operation)()
        except UnitRegistryMutationError:
            continue
        except TypeError:  # pragma: no cover - would mean the refusal is
            unreached.append(operation)  # behind an argument check
        else:  # pragma: no cover
            unreached.append(operation)
    assert unreached == [], unreached

    # attribute assignment and deletion, which is what covers every behaviour
    # flag without anyone having to list them
    with pytest.raises(UnitRegistryMutationError):
        registry.autoconvert_offset_to_baseunit = True
    with pytest.raises(UnitRegistryMutationError):
        registry.default_format = "~P"
    with pytest.raises(UnitRegistryMutationError):
        del registry._units

    # and the back-reference every pint quantity carries
    with pytest.raises(UnitRegistryMutationError):
        registry.Quantity(1.0, "volt")._REGISTRY.define("smoot = 1.702 * meter")


def test_one_run_cannot_change_another_run_s_arithmetic():
    """The influence, constructed deliberately, then watched being refused.

    This is the whole claim in one test: run A redefines the volt to be worth
    two of them, run B converts a volt, and run B's answer is the answer it
    would have given if run A had never executed.
    """
    from src.engcore.scientific.errors import UnitRegistryMutationError
    from src.engcore.scientific.units import Quantity

    def run_a_tries_to_redefine_the_volt():
        _sealed_registry().define(
            "volt = 2 * kilogram * meter ** 2 / ampere / second ** 3"
        )

    def run_b_converts_a_volt():
        return Quantity(1.0, "volt").magnitude_in("millivolt")

    assert run_b_converts_a_volt() == 1000.0
    with pytest.raises(UnitRegistryMutationError) as refusal:
        run_a_tries_to_redefine_the_volt()
    assert "sealed" in str(refusal.value)
    assert run_b_converts_a_volt() == 1000.0


def test_nothing_in_the_repository_mutates_the_registry():
    """The refusal's precondition, checked over the tree rather than asserted.

    Refusal is only a workable choice if nothing needs the thing refused. That
    is a claim about every file, so it is read off every file: no module
    outside the units package may import the backend at all, which forecloses
    a private registry as well as a mutation of this one.
    """
    root = pathlib.Path(engcore.__file__).resolve().parent
    permitted = root / "scientific" / "units"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if permitted in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "pint" or n.startswith("pint.") for n in names):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], offenders


def test_the_fingerprint_detects_what_the_refusal_cannot_prevent():
    """The detector, made to fail on purpose, on each shape it must tell apart.

    A redefinition, a removal, a shadowing name and a wholly new one. And the
    case it must NOT flag: pint materialises prefixed units lazily into the
    same mapping the declared ones live in, so `millivolt` appearing after the
    seal is the backend doing its own job, not a mutation.
    """
    import copy

    from src.engcore.scientific.errors import UnitRegistryMutationError
    from src.engcore.scientific.units import (
        Quantity,
        verify_registry_unmutated,
    )

    registry = _sealed_registry()
    store = registry._units.maps[0]

    # pint's own lazy prefixing is not a mutation
    Quantity(1.0, "volt").magnitude_in("millivolt")
    Quantity(1.0, "kiloohm").magnitude_in("ohm")
    verify_registry_unmutated()

    def refused(label, name, value):
        had, previous = name in store, store.get(name)
        if value is None:
            store.pop(name, None)
        else:
            store[name] = value
        try:
            with pytest.raises(UnitRegistryMutationError) as refusal:
                verify_registry_unmutated()
            assert "suspect" in str(refusal.value), label
        finally:
            if had:
                store[name] = previous
            else:
                store.pop(name, None)

    doubled = copy.deepcopy(store["volt"])
    object.__setattr__(
        doubled, "converter", type(doubled.converter)(scale=2.0)
    )
    refused("a redefinition", "volt", doubled)
    refused("a removal", "ohm", None)
    refused("a shadowing prefixed name", "millivolt",
            copy.deepcopy(store["meter"]))
    refused("a wholly new unit", "smoot", copy.deepcopy(store["meter"]))

    verify_registry_unmutated()


# =====================================================================
# GUARD 9 — a result cannot be silent about a model it declares
# =====================================================================
#
# `validity` was populated on one path of five. The four that returned `{}` are
# not four oversights: the core made the field optional, so four domains took
# the permission and a fifth would have taken it too. This guard is over the
# permission rather than over the four, and it is written the way the rest of
# this file is written — over what the repository contains, so the sixth domain
# is covered on the day it lands.

def _every_result_producing_module():
    """Modules that construct a `ScientificResult`, found by reading the tree."""
    root = pathlib.Path(engcore.__file__).resolve().parent
    found = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ScientificResult"
            ):
                found.append((path, node))
    return found


def test_the_result_construction_discovery_found_the_repository():
    """A guard over an empty set passes and proves nothing."""
    assert len(_every_result_producing_module()) >= 10


def test_every_result_construction_in_the_repository_states_a_position():
    """Read off the source, not off the paths that happen to be exercised.

    A construction site reached by no test would still be a domain the core let
    stay silent, so this asks the source: every `ScientificResult(...)` that
    passes `models=` must also pass one of the two fields that answers for
    them — or be a module some package answers for.
    """
    from src.engcore.domains import SCIENTIFIC_UNASSESSED_DECLARATIONS

    # By full module path, never by file name. The first version of this line
    # compared `path.stem`, and both the frozen thermal solver and the CSTR
    # solver are called `solver.py` -- so it excused every `solver.py` in the
    # repository, and the mutation that made the CSTR discard its assessment
    # again walked straight past it. A guard that matches on a leaf name is a
    # guard over a coincidence.
    root = pathlib.Path(engcore.__file__).resolve().parent
    declared_for = {
        name.removeprefix("src.").removeprefix("engcore.")
        for name in SCIENTIFIC_UNASSESSED_DECLARATIONS
    }
    silent = []
    for path, node in _every_result_producing_module():
        module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        keywords = {k.arg for k in node.keywords}
        if "models" not in keywords:
            continue
        if keywords & {"validity", "validity_not_assessed"}:
            continue
        if module in declared_for:
            continue
        silent.append(f"{module}:{node.lineno}")
    assert silent == [], silent


def test_a_result_that_declares_a_model_and_says_nothing_is_refused():
    """The permission, gone. Made to fail here, on purpose, once."""
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.results.provenance import ProvenanceRecord
    from src.engcore.scientific.results.result import ScientificResult

    provenance = ProvenanceRecord(
        run_id="guard9",
        software_version="test",
        git_commit="0" * 40,
        models=(("guard9.model", "1.0"),),
        solvers=(),
        inputs={},
    )
    payload = dict(
        result_id="guard9",
        values={"x": Quantity(1.0, "volt")},
        models=(("guard9.model", "1.0"),),
        provenance=provenance,
    )
    with pytest.raises(ScientificCoreError) as refusal:
        ScientificResult(**payload)
    assert "guard9.model" in str(refusal.value)

    # and both ways out actually work
    stated = ScientificResult(
        **payload, validity_not_assessed={"guard9.model": "nobody asked"}
    )
    assert stated.non_assessment_reason("guard9.model") == "nobody asked"
    assert not stated.is_assessed("guard9.model")


def test_the_only_package_level_exemptions_are_files_a_freeze_actually_pins():
    """The exemption is read off the pins, not off somebody's memory.

    A package may state a position for a module that cannot state its own. The
    only reason a module cannot is that its bytes are pinned — so every entry
    is checked against the frozen experiment configs, and an entry for an
    unpinned module fails here. That is what stops the mechanism from becoming
    a way to be excused from answering.
    """
    import re

    from src.engcore.domains import SCIENTIFIC_UNASSESSED_DECLARATIONS

    repo = pathlib.Path(engcore.__file__).resolve().parents[2]
    pinned: set[str] = set()
    for config in sorted((repo / "experiments").glob("*/*_config.py")):
        for match in re.finditer(
            r'"((?:src|tests|benchmarks)/[^"]+\.py)"\s*:',
            config.read_text(encoding="utf-8"),
        ):
            pinned.add(match.group(1))
    assert pinned, "no frozen experiment pins were found; this test is vacuous"

    assert SCIENTIFIC_UNASSESSED_DECLARATIONS, "an empty mapping proves nothing"
    for module, reason in SCIENTIFIC_UNASSESSED_DECLARATIONS.items():
        relative = (
            "src/" + module.removeprefix("src.").replace(".", "/") + ".py"
        )
        assert relative in pinned, (
            f"{module} is declared unassessable by its package but its source "
            f"is not pinned by any frozen experiment, so it could simply state "
            f"its own position"
        )
        assert reason.strip(), module


def test_the_frozen_module_s_results_carry_the_stated_reason():
    """Wiring is the test: the declaration has to reach a real result.

    A mapping nothing reads is a mapping that proves nothing, and this one is
    consulted on a path no ordinary construction takes. So a result is produced
    by the frozen module itself and asked what it says.
    """
    from src.engcore.domains import SCIENTIFIC_UNASSESSED_DECLARATIONS
    from src.engcore.domains.thermal.conduction1d.problem import (
        ConductionSlab,
        DIFFUSION_MODEL,
        SlabDiscretization,
    )
    from src.engcore.domains.thermal.conduction1d.solver import solve_slab

    slab = ConductionSlab(
        slab_id="guard9-frozen",
        length=Quantity(1.0, "meter"),
        diffusivity=Quantity(1e-4, "meter**2/second"),
        end_time=Quantity(10.0, "second"),
        discretization=SlabDiscretization(16, 20),
    )
    result = solve_slab(slab, run_id="guard9-frozen")

    assert result.unassessed_models == (DIFFUSION_MODEL.model_id,)
    reason = result.non_assessment_reason(DIFFUSION_MODEL.model_id)
    assert reason == SCIENTIFIC_UNASSESSED_DECLARATIONS[
        "src.engcore.domains.thermal.conduction1d.solver"
    ]
    assert "thermal_t1" in reason


def test_the_universal_core_names_no_module_it_exempts():
    """The layering rule, applied to this milestone's own mechanism.

    The first version of this exemption put the frozen module's dotted name in
    `results/result.py` and `test_x2` caught it: the universal core had learned
    a domain's name. The core knows the attribute name and nothing else, and
    that stays true.
    """
    from src.engcore.scientific.results import result as result_module
    from src.engcore.domains import SCIENTIFIC_UNASSESSED_DECLARATIONS

    source = pathlib.Path(result_module.__file__).read_text(encoding="utf-8")
    for module in SCIENTIFIC_UNASSESSED_DECLARATIONS:
        leaf = module.rsplit(".", 1)[0].rsplit(".", 1)[-1]
        assert module not in source
        assert leaf not in source, leaf


# =====================================================================
# GUARD 2, second axis — a level cannot be smuggled past the constructor
# =====================================================================
#
# THE ENUMERATION. Every way a `ValidationCheck` can come into existence, and
# where each is covered. This list is the deliverable, not the fix: the fix was
# one route, and the reason to write the list is that this is the third time a
# guard complete on one axis has been read as complete.
#
#   1. `ValidationCheck(...)`            constructor rule in __post_init__
#   2. `ValidationCheck.from_dict`       delegates to the constructor
#   3. `dataclasses.replace(check, ...)` re-runs __post_init__
#   4. `ValidationReport(checks=...)`    THE OPEN ROUTE. Closed here: anything
#                                        that is not a ValidationCheck is
#                                        refused, and the rule is re-applied to
#                                        the fields of everything held
#   5. `ValidationReport.with_check`     builds a ValidationReport, so (4)
#   6. `ValidationReport.from_dict`      delegates to (2), and separately
#                                        recomputes attained_levels against the
#                                        payload's own declaration
#   7. copy / deepcopy / pickle          bypasses __post_init__, but reproduces
#                                        an already-valid check. A forged
#                                        payload is caught by (4) on entry to a
#                                        report
#   8. `object.__setattr__` on a built   available for EVERY frozen record in
#      check                             this repository and closable on none
#                                        of them. Closed where it matters
#                                        instead: a level becomes a claim only
#                                        through a report, and the report
#                                        re-applies the rule on construction
#                                        AND on every read of attained_levels
#   9. a ValidationCheck SUBCLASS that   isinstance passes, so (4)'s type test
#      overrides earns_its_level         alone would not. The report applies
#                                        `level_is_earned` to FIELDS, so the
#                                        object does not get to answer the
#                                        question about itself
#
# Every one is exercised below.

def _cross_solver():
    from src.engcore.scientific.results.validation import ValidationLevel

    return ValidationLevel.CROSS_SOLVER_VALIDATED


def _earned_check(name="earned"):
    from src.engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationOutcome,
    )

    return ValidationCheck(
        name=name,
        outcome=ValidationOutcome.PASS,
        establishes=_cross_solver(),
        evidence=("route a vs route b",),
    )


def test_the_construction_axis_is_still_closed_on_every_route_to_it():
    """Routes 1, 2, 3 and 6 — re-measured rather than assumed still true."""
    import dataclasses

    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.validation import (
        CHECK_SCHEMA,
        ValidationCheck,
        ValidationOutcome,
    )

    with pytest.raises(ScientificValidationError):  # 1. constructor
        ValidationCheck(
            name="claimed",
            outcome=ValidationOutcome.PASS,
            establishes=_cross_solver(),
        )

    with pytest.raises(ScientificValidationError):  # 2. from_dict
        ValidationCheck.from_dict({
            "schema": CHECK_SCHEMA,
            "name": "claimed",
            "outcome": "pass",
            "detail": "",
            "establishes": _cross_solver().value,
            "residual": None,
            "tolerance": None,
            "evidence": [],
        })

    with pytest.raises(ScientificValidationError):  # 3. replace
        dataclasses.replace(_earned_check(), evidence=())


def test_a_report_refuses_anything_that_is_not_a_validation_check():
    """Route 4, the one that was open.

    Nothing was smuggled in: a stand-in object with a `passed` and an
    `establishes` reached `attained_levels`, satisfied `claims` and passed
    `require_level`, because the constructor rule was never consulted -- the
    constructor was never called.
    """
    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.validation import (
        ValidationOutcome,
        ValidationReport,
    )

    class NotACheck:
        name = "smuggled"
        outcome = ValidationOutcome.PASS
        passed = True
        establishes = _cross_solver()
        residual = None
        tolerance = None
        evidence = ()
        detail = ""

    with pytest.raises(ScientificValidationError, match="not a ValidationCheck"):
        ValidationReport(checks=(NotACheck(),))
    with pytest.raises(ScientificValidationError, match="not a ValidationCheck"):
        ValidationReport().with_check(NotACheck())  # 5. with_check


def test_a_check_altered_after_it_was_built_cannot_carry_a_level():
    """Route 8, at both moments a level becomes a claim.

    A frozen dataclass refuses `check.evidence = ()`. It does not refuse
    `object.__setattr__`, and nothing on the record can make it: that hole is
    the same size for every frozen record in this repository. So it is closed
    where a level stops being a field and becomes a claim -- on entry to a
    report, and on every read of the levels off one.
    """
    import copy

    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.validation import ValidationReport

    poked = copy.deepcopy(_earned_check())
    object.__setattr__(poked, "evidence", ())
    with pytest.raises(ScientificValidationError, match="altered after"):
        ValidationReport(checks=(poked,))

    # and after the report already exists
    report = ValidationReport(checks=(_earned_check(),))
    assert report.attained_levels == frozenset({_cross_solver()})
    object.__setattr__(report.checks[0], "evidence", ())
    with pytest.raises(ScientificValidationError, match="altered after"):
        report.attained_levels
    with pytest.raises(ScientificValidationError):
        report.claims(_cross_solver())
    with pytest.raises(ScientificValidationError):
        report.require_level(_cross_solver())


def test_a_subclass_does_not_get_to_answer_the_question_about_itself():
    """Route 9. `isinstance` alone would have let this through.

    The rule is applied to FIELDS by a module-level function, so overriding
    `earns_its_level` changes what the object says and not what the report
    concludes.
    """
    from src.engcore.scientific.errors import ScientificValidationError
    from src.engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationOutcome,
        ValidationReport,
    )

    class Liar(ValidationCheck):
        @property
        def earns_its_level(self):  # pragma: no cover - never consulted
            return True

        @property
        def compared_something(self):  # pragma: no cover - never consulted
            return True

    liar = Liar.__new__(Liar)
    for field, value in dict(
        name="liar",
        outcome=ValidationOutcome.PASS,
        detail="",
        establishes=_cross_solver(),
        residual=None,
        tolerance=None,
        evidence=(),
    ).items():
        object.__setattr__(liar, field, value)

    assert isinstance(liar, ValidationCheck), "the type test alone would pass"
    assert liar.earns_its_level, "and the object says it is fine"
    with pytest.raises(ScientificValidationError, match="altered after"):
        ValidationReport(checks=(liar,))


def test_every_report_in_the_repository_still_builds():
    """The closure is not vacuous and is not disruptive.

    Every check the repository's own solvers produce still constructs a report,
    which is the difference between a rule and a wall.
    """
    from src.engcore.scientific.results.validation import (
        ValidationReport,
        unverified_report,
    )

    assert unverified_report("nothing ran").attained_levels == frozenset()
    assert ValidationReport(checks=(_earned_check(),)).claims(_cross_solver())


# =====================================================================
# GUARD 10 — a record that cannot be written down cannot be built
# =====================================================================
#
# A result holding an unserializable value used to construct happily and die
# later, inside whatever was trying to record it, with a TypeError from `json`
# that named neither the result nor the field. A result that exists in memory
# and cannot be recorded is a result whose provenance does not exist.
#
# The second half of this guard is the one worth having. Four places in this
# repository refuse over the same value space — the result, its provenance, an
# asserted context, and the digest helper in design memory. Two refusals over
# one value space that do not agree is a worse defect than either alone: a
# payload one accepts and another rejects is a record that can be built here
# and not there, for reasons neither side stated. So they share one rule, and
# the agreement is asserted rather than assumed.

#: ``(label, value, is recordable)``. The last column is the claim; every
#: refusing site below must agree with it, and `json.dumps` must agree too.
_WRITABILITY_TABLE = (
    ("plain nested containers", {"a": {"b": [1, 2.5, "x", True, None]}}, True),
    ("a tuple", {"t": (1, 2)}, True),
    ("an empty mapping", {}, True),
    ("a bare object", {"o": object()}, False),
    ("bytes", {"b": b"\x00"}, False),
    ("a set", {"s": {1, 2}}, False),
    ("a function", {"f": (lambda: 1)}, False),
    ("an object nested three deep", {"a": {"b": [{"c": object()}]}}, False),
    ("a NaN", {"n": float("nan")}, False),
    ("an infinity", {"i": float("inf")}, False),
    ("a non-string key", {1: "a"}, False),
)


def _provenance_for(metadata=None):
    from src.engcore.scientific.results.provenance import ProvenanceRecord

    return ProvenanceRecord(
        run_id="guard10",
        software_version="test",
        git_commit="0" * 40,
        models=(),
        solvers=(),
        inputs={},
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    "label,value,recordable",
    _WRITABILITY_TABLE,
    ids=[row[0] for row in _WRITABILITY_TABLE],
)
def test_a_result_refuses_at_construction_what_it_could_not_record(
    label, value, recordable
):
    """Refused where it is introduced, naming the field and the type."""
    import json

    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.results.result import ScientificResult

    def build():
        return ScientificResult(
            result_id="guard10",
            values={"v": Quantity(1.0, "volt")},
            provenance=_provenance_for(),
            metadata=value,
        )

    if recordable:
        # and the promise the refusal exists to keep: what was accepted can
        # actually be written down.
        json.dumps(build().to_dict(), sort_keys=True, allow_nan=False)
        return

    with pytest.raises(ScientificCoreError) as refusal:
        build()
    message = str(refusal.value)
    assert "metadata" in message, message
    assert "cannot be recorded" in message, message


@pytest.mark.parametrize(
    "label,value,recordable",
    _WRITABILITY_TABLE,
    ids=[row[0] for row in _WRITABILITY_TABLE],
)
def test_every_refusal_over_this_value_space_gives_the_same_answer(
    label, value, recordable
):
    """The agreement, asserted rather than assumed.

    Four sites and `json` itself, on one table. A row on which any two of them
    disagreed would be a value a record could hold in one place and not in
    another — which is how a value space ends up with a hole shaped like
    whichever site was consulted last.
    """
    import json

    from src.engcore.design.memory import _canonical_bytes
    from src.engcore.mcp.errors import CredibilityEvidenceError
    from src.engcore.mcp.evidence import AssertedContext
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.results.result import ScientificResult

    def accepted(fn, expected_error):
        try:
            fn()
        except expected_error:
            return False
        return True

    verdicts = {
        "ScientificResult.metadata": accepted(
            lambda: ScientificResult(
                result_id="g",
                values={"v": Quantity(1.0, "volt")},
                provenance=_provenance_for(),
                metadata=value,
            ),
            ScientificCoreError,
        ),
        "ProvenanceRecord.metadata": accepted(
            lambda: _provenance_for(value), ScientificCoreError
        ),
        "AssertedContext.payload": accepted(
            lambda: AssertedContext(
                source="guard10", description="d", payload=value
            ),
            CredibilityEvidenceError,
        ),
        "design memory _canonical_bytes": accepted(
            lambda: _canonical_bytes(value), ScientificCoreError
        ),
    }
    assert set(verdicts.values()) == {recordable}, verdicts

    # And `json` itself, on the same row. The one deliberate divergence is
    # named rather than hidden: `json.dumps` accepts a non-string key and
    # silently coerces it, so `1` and `"1"` become one key and a record holding
    # both loses one on the way out. These refuse it. Everything else agrees
    # exactly, including the non-finite floats `json.dumps` will emit as bare
    # `NaN` and `Infinity` tokens that no conforming reader accepts.
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
        json_accepts = True
    except (TypeError, ValueError):
        json_accepts = False
    if label == "a non-string key":
        assert json_accepts and not recordable
    else:
        assert json_accepts is recordable, label


def test_the_refusal_points_at_the_leaf_and_not_at_the_field():
    """A path, so a caller knows which of forty metadata keys to look at."""
    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.results.result import ScientificResult

    with pytest.raises(ScientificCoreError) as refusal:
        ScientificResult(
            result_id="guard10",
            values={"v": Quantity(1.0, "volt")},
            provenance=_provenance_for(),
            metadata={"fine": 1, "numerics": {"history": [0, object()]}},
        )
    assert "metadata['numerics']['history'][1]" in str(refusal.value)
    assert "object" in str(refusal.value)


# =====================================================================
# GUARD 11 — provenance cannot name a source it cannot show
# =====================================================================
#
# `ProvenanceRecord.parent_run_id` was a string a caller typed. Nothing about
# `ProvenanceRecord(parent_run_id="run-0001")` required that `run-0001` ever
# existed, ever ran, or was ever anything at all. A provenance record making a
# claim about a source that was never there is the one claim this project
# exists to make impossible, and it was possible in the project's own record
# type.
#
# The rule is the one `ExecutionBinding.from_execution` already uses one field
# over: take the object that exists BECAUSE the thing happened, rather than the
# name someone believes it had.

def _bare_provenance(run_id="guard11", **overrides):
    from src.engcore.scientific.results.provenance import ProvenanceRecord

    payload = dict(
        run_id=run_id,
        software_version="test",
        git_commit="0" * 40,
        models=(),
        solvers=(),
        inputs={},
    )
    payload.update(overrides)
    return ProvenanceRecord(**payload)


def test_a_lineage_claim_without_the_record_it_names_is_refused():
    """Made to fail on purpose. This is the whole guard."""
    from src.engcore.scientific.errors import ScientificCoreError

    with pytest.raises(ScientificCoreError) as refusal:
        _bare_provenance(parent_run_id="a-run-that-never-existed")
    message = str(refusal.value)
    assert "a-run-that-never-existed" in message
    assert "cannot show" in message
    assert "parent=" in message, "the error has to say what to do instead"


def test_the_claim_is_accepted_when_the_parent_is_held():
    parent = _bare_provenance("guard11-parent")
    child = _bare_provenance("guard11-child", parent=parent)
    assert child.parent_run_id == "guard11-parent"
    # and `derived` -- which has always had the parent -- now says so
    assert parent.derived("guard11-derived").parent_run_id == "guard11-parent"


def test_a_typed_name_cannot_outrank_the_record_that_exists():
    """Two answers to one question, and neither silently wins."""
    from src.engcore.scientific.errors import ScientificCoreError

    parent = _bare_provenance("guard11-parent")
    with pytest.raises(ScientificCoreError, match="Two different answers"):
        _bare_provenance(
            "guard11-child", parent=parent, parent_run_id="somebody-else"
        )
    # agreeing is fine; it is a redundant statement, not a contradiction
    assert _bare_provenance(
        "guard11-child", parent=parent, parent_run_id="guard11-parent"
    ).parent_run_id == "guard11-parent"


def test_a_record_cannot_be_its_own_source():
    """A lineage that closes on itself has no root, and a walker does not stop."""
    from src.engcore.scientific.errors import ScientificCoreError

    itself = _bare_provenance("guard11-loop")
    with pytest.raises(ScientificCoreError, match="its own parent"):
        _bare_provenance("guard11-loop", parent=itself)


def test_a_name_wearing_an_objects_clothes_is_refused():
    """`parent` is a record, and a stand-in with a `run_id` is not one."""
    import types

    from src.engcore.scientific.errors import ScientificCoreError

    with pytest.raises(ScientificCoreError, match="wearing an object"):
        _bare_provenance(
            "guard11-child", parent=types.SimpleNamespace(run_id="looks-real")
        )


def test_a_stored_record_reproduces_its_claim_and_does_not_re_make_it():
    """Reading a payload is not asserting what it says.

    The one exception, and it is a type rather than a flag: `from_dict` has no
    parent record to hold and is not making a claim, so it passes the marker
    that says exactly that. A round trip is lossless, and the marker cannot be
    mistaken for a held parent by anyone reading the code.
    """
    import json

    from src.engcore.scientific.errors import ScientificCoreError
    from src.engcore.scientific.results.provenance import (
        ProvenanceRecord,
        StoredParentClaim,
    )

    original = _bare_provenance("guard11-child", parent=_bare_provenance("p"))
    payload = json.loads(json.dumps(original.to_dict(), sort_keys=True))
    restored = ProvenanceRecord.from_dict(payload)
    assert restored.parent_run_id == "p"
    assert restored == original

    # and the marker is itself a record with a rule, not a free string
    with pytest.raises(ScientificCoreError, match="must name a run"):
        StoredParentClaim("   ")


def test_a_record_with_a_parent_can_still_be_rebuilt_from_itself():
    """`dataclasses.replace` on a record that HAS a parent.

    The first version of this rule set `parent` to None once it had been
    consumed, which made every `replace` on such a record illegal: the rebuilt
    record named a source with nothing behind it, so the rule refused the
    honest reconstruction of a record it had already accepted. Five MVR1 tests
    said so. Kept as a test rather than as a comment, because the shape --
    a constructor invariant that forbids re-running the constructor -- is easy
    to reintroduce.
    """
    import dataclasses

    parent = _bare_provenance("guard11-parent")
    child = _bare_provenance("guard11-child", parent=parent)
    again = dataclasses.replace(child, metadata={"edited": True})
    assert again.parent_run_id == "guard11-parent"
    assert again.metadata["edited"] is True


def test_the_read_back_marker_is_used_where_a_claim_is_reproduced_and_nowhere_else():
    """The one exception, kept to the one place it means something.

    `StoredParentClaim` says "reproducing a claim somebody else made". Used
    anywhere a parent record is actually available, it would be the refusal's
    own back door, so the tree is read rather than trusted.
    """
    root = pathlib.Path(engcore.__file__).resolve().parent
    users = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "StoredParentClaim"
            ):
                module = (
                    path.relative_to(root).with_suffix("").as_posix()
                ).replace("/", ".")
                users.append(module)
    assert sorted(set(users)) == ["scientific.results.provenance"], users


def test_no_module_still_hands_provenance_a_lineage_name_it_does_not_hold():
    """Over the tree, so a sixth domain is covered on the day it lands."""
    root = pathlib.Path(engcore.__file__).resolve().parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "provenance.py":
            continue
        module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "parent_run_id":
                    offenders.append(f"{module}:{node.lineno}")
    # By full module path. Written first as `path.name`, which excused every
    # file called `solver.py` in the repository -- the same coincidence-matching
    # that GUARD 9's mutation caught two commits ago, made again on the next
    # sweep. There are five `solver.py` files here.
    #
    # The frozen thermal solver still THREADS one through as a parameter it
    # cannot be edited to change; what matters is that nobody hands a bare name
    # to the record. Its own call is `parent_run_id=parent_run_id`, a
    # pass-through of a parameter no caller in this repository supplies, and
    # the refusal fires if one ever does.
    assert offenders == ["domains.thermal.conduction1d.solver:393"], offenders


# =====================================================================
# GUARD 12 — a quantity crossing a domain boundary arrives declared
# =====================================================================
#
# The ambient a body declares reaches an element's applicability assessment,
# because a rated dissipation is stated against a reference ambient and derates
# away from it. It used to arrive as `{stage.component_id: ...}` — a dict
# comprehension matching component ids, with no declaration, no source record,
# no instant and no check that both sides meant the same quantity.
#
# What is enforced here is the crossing that exists. A crossing nobody has
# written yet is NOT enforced, and `NEEDS.md` C4 says so in those words rather
# than leaving the reader to assume otherwise.

def _ambient_transfer(value=None, **overrides):
    from src.engcore.domains.electrical.dc import models as dc_models
    from src.engcore.scientific.composition import QuantityTransfer

    payload = dict(
        dependency=dc_models.ambient_transfer_declaration(
            source_problem_id="thermal-lumped-R1",
            source_quantity="ambient_temperature",
            component_id="R1",
        ),
        value=value if value is not None else Quantity(300.0, "kelvin"),
        source_record_id="thermal-result-1",
        instant="coupled_iteration:3",
    )
    payload.update(overrides)
    return QuantityTransfer(**payload)


def test_a_crossed_quantity_arriving_undeclared_is_refused():
    """Fail-closed at the crossing that exists. Made to fail on purpose."""
    from src.engcore.domains.electrical.dc import models as dc_models
    from src.engcore.domains.electrical.dc import problem as dc_problem
    from src.engcore.scientific.errors import InvalidScientificProblem

    class Element:
        component_id = "R1"
        resistance = Quantity(100.0, "ohm")

    problem = dc_problem.resistor_relation_problem(Element())
    with pytest.raises(InvalidScientificProblem) as refusal:
        dc_models.assess_resistor_validity(
            problem,
            dissipated_power=Quantity(0.9, "watt"),
            # A bare Quantity: the shape the dict comprehension produced.
            ambient=Quantity(300.0, "kelvin"),
        )
    message = str(refusal.value)
    assert "QuantityTransfer" in message
    assert "where it came from and when" in message

    # and a transfer declaring some other target is not a declaration of this
    with pytest.raises(InvalidScientificProblem, match="not a declaration of"):
        dc_models.assess_resistor_validity(
            problem,
            dissipated_power=Quantity(0.9, "watt"),
            ambient=_ambient_transfer(
                dependency=__import__(
                    "src.engcore.scientific.composition",
                    fromlist=["QuantityDependency"],
                ).QuantityDependency(
                    source_problem_id="t",
                    source_quantity="ambient_temperature",
                    target_problem_id="electrical_dc_resistor:R1",
                    target_quantity="something_else",
                    unit_exemplar="kelvin",
                )
            ),
        )


def test_a_transfer_states_a_source_an_instant_and_an_agreeing_dimension():
    """Each refusal, once, on purpose."""
    from src.engcore.scientific.errors import InvalidScientificProblem

    assert _ambient_transfer().received_as("degC").magnitude == pytest.approx(
        26.85
    )
    with pytest.raises(InvalidScientificProblem, match="do not mean the same"):
        _ambient_transfer(value=Quantity(5.0, "volt"))
    with pytest.raises(InvalidScientificProblem, match="no source_record_id"):
        _ambient_transfer(source_record_id="  ")
    with pytest.raises(InvalidScientificProblem, match="no instant"):
        _ambient_transfer(instant="")
    with pytest.raises(InvalidScientificProblem, match="QuantityDependency"):
        _ambient_transfer(dependency="thermal-lumped-R1")


def test_two_values_crossing_one_declaration_at_one_instant_are_refused():
    """One fact, stated twice, must be one fact."""
    from src.engcore.scientific.composition import require_agreeing_transfers
    from src.engcore.scientific.errors import InvalidScientificProblem

    one = _ambient_transfer()
    same = _ambient_transfer()
    other = _ambient_transfer(value=Quantity(310.0, "kelvin"))
    assert require_agreeing_transfers((one, same)) == (one,)
    with pytest.raises(InvalidScientificProblem, match="nothing here can say"):
        require_agreeing_transfers((one, other))


def test_the_crossing_is_recorded_in_the_provenance_of_the_run_that_made_it():
    """Not re-derived by the consumer: made once, carried, read back.

    Marked by its own cost — this runs a coupled solve — but the claim needs a
    real run: a transfer set nothing produced would prove that the record can
    hold one, which is not the question.
    """
    from src.engcore.mcp.problem import (
        example_electrothermal_payload,
        run_electrothermal_case,
    )

    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="guard12"
    ).reports[0]
    transfers = report.provenance.transfers
    assert transfers, "the coupled run recorded no crossing"
    for transfer in transfers:
        assert transfer.dependency.target_quantity == "ambient_temperature"
        assert transfer.source_record_id
        assert transfer.instant.startswith("coupled_iteration:")
        assert transfer.dependency.target_problem_id.startswith(
            "electrical_dc_resistor:"
        )
    # and it survives the record boundary
    from src.engcore.scientific.results.provenance import ProvenanceRecord

    restored = ProvenanceRecord.from_dict(report.provenance.to_dict())
    assert restored.transfers == transfers


def test_the_declared_crossing_is_what_lets_repair_invert_the_condition():
    """The proof the fix is real, and the reason it is the proof.

    `repair.py` refused to invert `dissipated_power_utilization` because the
    ambient "is not a declared input of this model -- it crosses in from the
    thermal body sharing this element's component id -- so the offset cannot be
    formed from the assessed context". Both halves are asserted here: without a
    declared crossing the condition is UNKNOWN and nothing inverts; with one,
    the verdict is reached and the hint carries a number.

    The number is checked against the formula rather than against itself:
    u = (T_amb + (P/d)(T_zero - T_rated)/P_rated) / T_zero <= 1 gives
    P_rated >= (P/d)(T_zero - T_rated)/(T_zero - T_amb).
    """
    from src.engcore.domains.electrical.dc import models as dc_models
    from src.engcore.domains.electrical.dc import problem as dc_problem

    class Element:
        component_id = "R1"
        resistance = Quantity(100.0, "ohm")

    rating = dc_models.ComponentRating(
        rated_power=Quantity(0.25, "watt"),
        maximum_working_voltage=Quantity(200.0, "volt"),
        rated_power_temperature=Quantity(343.15, "kelvin"),
        zero_power_temperature=Quantity(428.15, "kelvin"),
        derating_factor=0.8,
    )
    problem = dc_problem.resistor_relation_problem(Element())
    state = dict(
        rating=rating,
        dissipated_power=Quantity(0.9, "watt"),
        voltage_across=Quantity(9.4868, "volt"),
    )

    # Before: the ambient did not cross, so the line cannot be evaluated.
    undeclared = dc_models.assess_resistor_validity(problem, **state)
    assert undeclared.unknown == ("dissipated_power_utilization",)
    refusals = [
        r
        for repair in dc_models.resistor_repairs(
            problem, subject="R1", **state
        )
        for r in repair.refusals
    ]
    assert refusals == [], "nothing is violated, so nothing is repaired yet"

    # After: it crossed under a declaration.
    declared = dc_models.assess_resistor_validity(
        problem, ambient=_ambient_transfer(), **state
    )
    assert declared.violated == ("dissipated_power_utilization",)
    repairs = dc_models.resistor_repairs(
        problem, subject="R1", ambient=_ambient_transfer(), **state
    )
    hints = [h for repair in repairs for h in repair.hints]
    assert [h.target_name for h in hints] == ["rated_power"], hints

    expected = (0.9 / 0.8) * (428.15 - 343.15) / (428.15 - 300.0)
    assert hints[0].threshold.magnitude_in("watt") == pytest.approx(expected)

    # The derating factor inverts too, and is then refused at its ceiling --
    # the inversion working, not failing.
    refused = {
        r.target: r.reason
        for repair in repairs
        for r in repair.refusals
    }
    assert "past" in refused["derating_factor"]


# =====================================================================
# GUARD 13 -- an input may be a declared function, and only on stated terms
# =====================================================================
#
# Seven inputs across this repository are fixed while their own models say
# they vary. The mechanism that lets one be declared as a function is only
# worth having if every way of misusing it is refused, because a curve that
# can be handed over loosely is a second way to be confidently wrong rather
# than the fix for the first.


def _ocv_curve(**overrides):
    """An alkaline-shaped OCV curve: 0.9 V empty to 1.6 V full, with a knee."""
    from src.engcore.scientific.models.curves import DeclaredCurve, TabulatedForm

    fields = dict(
        quantity="open_circuit_voltage_curve",
        against="state_of_charge",
        against_unit="dimensionless",
        unit="volt",
        lower=0.0,
        upper=1.0,
        form=TabulatedForm(
            samples=((0.0, 0.9), (0.1, 1.15), (0.3, 1.30), (0.6, 1.42), (1.0, 1.6))
        ),
    )
    fields.update(overrides)
    return DeclaredCurve(**fields)


def test_an_input_declared_as_a_constant_refuses_a_curve():
    """The fail-closed edge: not using the mechanism is an error, not a pass.

    A model whose input is one number and which is handed a function of state
    has been handed something it cannot read. The refusal is what stops that
    arriving as a silent first-sample, a silent midpoint, or a stored object
    nothing consults.
    """
    from src.engcore.scientific.models.definition import (
        InputSourceKind,
        ModelInputSpec,
    )

    constant = ModelInputSpec(
        name="open_circuit_voltage_curve",
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar="volt",
    )
    assert constant.varies_with is None
    with pytest.raises(InvalidScientificProblem) as excinfo:
        constant.accept_curve(_ocv_curve())
    assert "declared as a constant" in str(excinfo.value)

    # And the same spec, having declared the axis, takes it.
    declaring = ModelInputSpec(
        name="open_circuit_voltage_curve",
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar="volt",
        varies_with="state_of_charge",
    )
    assert declaring.accept_curve(_ocv_curve()) is None


def test_the_curve_axis_is_declared_on_both_sides_and_inferred_by_neither():
    """A caller cannot hand over a table and let the model guess the axis."""
    from src.engcore.scientific.models.curves import PolynomialForm
    from src.engcore.scientific.models.definition import (
        InputSourceKind,
        ModelInputSpec,
    )

    spec = ModelInputSpec(
        name="open_circuit_voltage_curve",
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar="volt",
        varies_with="state_of_charge",
    )
    against_temperature = _ocv_curve(
        against="cell_temperature",
        against_unit="kelvin",
        lower=250.0,
        upper=350.0,
        form=PolynomialForm(coefficients=(1.5, 0.001)),
    )
    with pytest.raises(InvalidScientificProblem) as excinfo:
        spec.accept_curve(against_temperature)
    assert "state_of_charge" in str(excinfo.value)
    assert "cell_temperature" in str(excinfo.value)

    # A curve with no axis at all cannot be built in the first place.
    with pytest.raises(InvalidScientificProblem):
        _ocv_curve(against="   ")


def test_outside_a_declared_interval_there_is_no_number_only_a_status():
    """A curve is evidence over the interval it covers and nothing beyond it."""
    from src.engcore.scientific.models.definition import ValidityStatus

    curve = _ocv_curve()
    inside = curve.evaluate(Quantity(0.5, "dimensionless"))
    assert inside.status is ValidityStatus.IN_DOMAIN
    assert inside.value == Quantity(1.38, "volt")

    for beyond in (1.2, -0.05):
        outside = curve.evaluate(Quantity(beyond, "dimensionless"))
        assert outside.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        assert outside.value is None, "an extrapolation arrived"
        assert "not extrapolated" in outside.reason

    # Absence is still UNKNOWN, which is what every unsupplied input here is.
    unsupplied = curve.evaluate(None)
    assert unsupplied.status is ValidityStatus.UNKNOWN
    assert unsupplied.value is None


def test_a_declared_interval_may_not_reach_past_the_samples():
    """Claiming evidence over ground the measurement never covered.

    Refused at declaration rather than at evaluation: by evaluation time the
    held-flat value past the last sample is indistinguishable from a measured
    one, and the caller is the only party who can still tell.
    """
    with pytest.raises(InvalidScientificProblem) as excinfo:
        _ocv_curve(upper=1.4)
    assert "past the samples" in str(excinfo.value)


def test_a_curve_is_structured_data_and_the_record_rules_agree_it_is_writable():
    """C1's refusal and this mechanism, checked against each other.

    A function was the obvious implementation and would have produced a model
    record no reader could reconstruct. Every form here is data: it survives
    the writability rule, round-trips, and digests.
    """
    from src.engcore.scientific.models.curves import (
        DeclaredCurve,
        PiecewiseForm,
        PolynomialForm,
        TabulatedForm,
    )
    from src.engcore.scientific.serialization import unwritable

    forms = (
        TabulatedForm(samples=((0.0, 0.9), (1.0, 1.6))),
        PolynomialForm(coefficients=(1.5, -0.002, 1e-6), reference=298.15),
        PiecewiseForm(
            breakpoints=(0.5,),
            pieces=(
                PolynomialForm(coefficients=(0.0,)),
                PolynomialForm(coefficients=(2.0, 1.0), reference=0.5),
            ),
        ),
    )
    for form in forms:
        curve = _ocv_curve(form=form)
        assert unwritable(curve.to_dict()) is None, form
        back = DeclaredCurve.from_dict(curve.to_dict())
        assert back == curve
        assert back.fingerprint == curve.fingerprint

    # And the digest separates curves that answer differently, which is what
    # a physical identity needs from it.
    steeper = _ocv_curve(form=TabulatedForm(samples=((0.0, 0.9), (1.0, 1.7))))
    assert steeper.fingerprint != _ocv_curve(
        form=TabulatedForm(samples=((0.0, 0.9), (1.0, 1.6)))
    ).fingerprint


def test_a_cell_declaring_a_curve_is_a_different_cell_and_says_so_everywhere():
    """The migrated quantity, end to end: value, identity, record.

    The chord and the curve disagree by 130 mV at half charge on an
    alkaline-shaped discharge -- about 10 % of the terminal voltage. A solver
    keyed on the cell's identity must not treat the two as one cell.
    """
    from src.engcore.domains.battery.cell import CellSpecification

    common = dict(
        cell_id="G13",
        nominal_capacity=Quantity(2.5, "ampere_hour"),
        internal_resistance=Quantity(0.1, "ohm"),
    )
    chord = CellSpecification(
        open_circuit_voltage_at_full=Quantity(1.6, "volt"),
        open_circuit_voltage_at_empty=Quantity(0.9, "volt"),
        **common,
    )
    curved = CellSpecification(open_circuit_voltage_curve=_ocv_curve(), **common)

    half = Quantity(0.5, "dimensionless")
    assert chord.open_circuit_voltage(half) == Quantity(1.25, "volt")
    assert curved.open_circuit_voltage(half) == Quantity(1.38, "volt")

    # The endpoints agree, which is exactly why the identity may not.
    assert curved.open_circuit_voltage_at_full == chord.open_circuit_voltage_at_full
    assert curved.open_circuit_voltage_at_empty == chord.open_circuit_voltage_at_empty
    assert chord.physical_key != curved.physical_key
    assert chord.physical_key[-1] == ""
    assert curved.physical_key[-1] == _ocv_curve().fingerprint

    assert CellSpecification.from_dict(curved.to_dict()) == curved
    assert CellSpecification.from_dict(chord.to_dict()) == chord


def test_one_quantity_may_not_be_declared_twice_at_two_depths():
    """A curve and the endpoints it would imply is a caller error, not a merge."""
    from src.engcore.domains.battery.cell import CellSpecification
    from src.engcore.scientific.models.curves import TabulatedForm

    with pytest.raises(InvalidScientificProblem) as excinfo:
        CellSpecification(
            cell_id="G13",
            nominal_capacity=Quantity(2.5, "ampere_hour"),
            internal_resistance=Quantity(0.1, "ohm"),
            open_circuit_voltage_at_full=Quantity(1.6, "volt"),
            open_circuit_voltage_curve=_ocv_curve(),
        )
    assert "states the same quantity twice" in str(excinfo.value)

    # A curve that does not reach both ends of the charge axis cannot supply
    # the endpoints the chord models still need, and says so.
    partial = _ocv_curve(
        lower=0.1,
        upper=0.9,
        form=TabulatedForm(samples=((0.1, 1.15), (0.9, 1.55))),
    )
    with pytest.raises(InvalidScientificProblem) as excinfo:
        CellSpecification(
            cell_id="G13",
            nominal_capacity=Quantity(2.5, "ampere_hour"),
            internal_resistance=Quantity(0.1, "ohm"),
            open_circuit_voltage_curve=partial,
        )
    assert "whole charge axis" in str(excinfo.value)


def test_the_unmigrated_inversion_refuses_rather_than_answering_from_the_chord():
    """One quantity was migrated. The boundary of that is stated, not implied.

    A cutoff voltage becomes a state of charge by inverting the open-circuit
    relation, and that inversion still assumes the chord. Run against a cell
    that declared a curve it would answer from a model the caller replaced,
    so it refuses.
    """
    from src.engcore.domains.battery.cell import CellSpecification, DischargeLoad
    from src.engcore.domains.battery.solver import evaluate_step

    curved = CellSpecification(
        cell_id="G13",
        nominal_capacity=Quantity(2.5, "ampere_hour"),
        internal_resistance=Quantity(0.1, "ohm"),
        open_circuit_voltage_curve=_ocv_curve(),
    )
    common = dict(
        load_id="G13-load",
        current=Quantity(0.5, "ampere"),
        initial_state_of_charge=Quantity(0.9, "dimensionless"),
        cell_temperature=Quantity(298.15, "kelvin"),
        duration=Quantity(600.0, "second"),
    )
    # Without a cutoff voltage the step computes, and on the curve. The step
    # ends at z = 0.8666..., where the curve reads 1.540 V and the chord this
    # cell would otherwise have carried reads 1.507 V -- 33 mV of difference
    # in the number the terminal voltage is built from.
    step = evaluate_step(curved, DischargeLoad(**common))
    assert step.open_circuit_voltage == pytest.approx(1.54)
    assert 0.9 + 0.7 * (0.9 - 0.5 / 6 / 2.5) == pytest.approx(1.5066666666666666)

    with pytest.raises(InvalidScientificProblem) as excinfo:
        evaluate_step(
            curved,
            DischargeLoad(cutoff_voltage=Quantity(1.0, "volt"), **common),
        )
    assert "has not been migrated" in str(excinfo.value)


# =====================================================================
# GUARD 14 -- a model states what it does not represent, where a reader is
# =====================================================================
#
# Ten models stated their exclusions in a docstring and in an `assumptions`
# tuple that no report carries. A caller reads a report; a caller cannot read
# the source. An exclusion a caller cannot see is not declared -- it is a
# silent assumption, and a risk nobody was told about.


#: The one model allowed to leave `exclusions` undeclared, and why. It is
#: constructed inside a frozen, byte-pinned tree the round that added the
#: field could not edit, so its exclusions cannot be written where they
#: belong. Its own `assumptions` carry them -- no convection, no radiation, no
#: phase change, no source term -- and a reader of a report still cannot see
#: them, which is what closing this entry would fix. One entry, for one stated
#: reason: the difference between that and a general escape is the whole of
#: whether the guard below means anything.
EXCLUSIONS_NOT_DECLARED = frozenset({"thermal.conduction1d.linear_diffusion"})


def test_every_shipped_model_declares_what_it_does_not_represent():
    """Over the tree, so a sixth domain is covered on the day it lands.

    The rule is about authoring, and this is the authored population: every
    model definition reachable in the package. It is deliberately not enforced
    in the constructor, which also reads archived records -- a record written
    before the field existed does not declare exclusions, and refusing to load
    it would destroy information rather than prevent a claim.
    """
    from src.engcore.scientific.models.definition import NOT_DECLARED

    undeclared = sorted(
        model.model_id
        for model in MODELS
        if model.exclusions is NOT_DECLARED
        and model.model_id not in EXCLUSIONS_NOT_DECLARED
    )
    assert undeclared == [], (
        f"{undeclared} name a domain and do not say what they leave out. A "
        f"reader of a credibility report cannot read this source"
    )

    # And the exemption is one model, for a stated reason, not a hole. A
    # second entry appearing here is a decision somebody has to defend.
    assert len(MODELS) >= 16, "the sweep must actually reach the models"


def test_an_empty_exclusion_list_is_a_claim_and_nobody_makes_it_by_accident():
    """`None` and `()` are different, and the difference is the whole field.

    An undeclared list read as "excludes nothing" is the defect. So no shipped
    model may reach `()` by omission -- it is not the default -- and today no
    model claims it at all.
    """
    from src.engcore.scientific.models.definition import (
        NOT_DECLARED,
        ScientificModelDefinition,
    )

    claiming_nothing = sorted(
        model.model_id
        for model in MODELS
        if model.exclusions is not NOT_DECLARED and model.exclusions == ()
    )
    assert claiming_nothing == [], (
        f"{claiming_nothing} claim to exclude nothing, which is almost never "
        f"true; check that this was written deliberately"
    )

    # THE FIELD IS MANDATORY. Omitting it raises -- there is no usable
    # default, because a default records whether somebody thought about the
    # question and not what the model excludes, and it reads exactly like a
    # declaration.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        ScientificModelDefinition(model_id="probe.silent", version="0.1.0")
    assert "declares no exclusions" in str(excinfo.value)

    # An empty list justifies itself. It is the strongest claim the field can
    # carry and the one least often true, so it costs a sentence.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        ScientificModelDefinition(
            model_id="probe.empty", version="0.1.0", exclusions=()
        )
    assert "does not say why" in str(excinfo.value)

    justified = ScientificModelDefinition(
        model_id="probe.empty",
        version="0.1.0",
        exclusions=(),
        excludes_nothing_because="a probe with no physical content",
    )
    assert justified.exclusions == ()

    # And the justification may not accompany a non-empty list, where it would
    # contradict it.
    with pytest.raises(InvalidScientificProblem):
        ScientificModelDefinition(
            model_id="probe.both",
            version="0.1.0",
            exclusions=("no phase change",),
            excludes_nothing_because="but also nothing",
        )

    # A blank exclusion is refused: it looks like a statement and is not one.
    with pytest.raises(InvalidScientificProblem):
        ScientificModelDefinition(
            model_id="probe.blank",
            version="0.1.0",
            exclusions=("no phase change", "   "),
        )


def test_the_credibility_report_carries_exclusions_beside_validity():
    """What the model does not represent, next to what it assessed.

    IN_DOMAIN answers the checkable half. The exclusions are the phenomena no
    condition can check, because the model does not represent them -- so a
    reader who sees only a status has been told less than they think.
    """
    from src.engcore.mcp.evidence import ModelValidityRecord
    from src.engcore.scientific.models.definition import (
        ValidityAssessment,
        ValidityStatus,
    )

    record = ModelValidityRecord(
        model_id="thermal.lumped.first_order_capacity",
        version="0.1.0",
        assessment=ValidityAssessment(
            status=ValidityStatus.IN_DOMAIN, satisfied=("biot_number",)
        ),
    )
    payload = record.to_dict()
    assert payload["assessment"]["status"] == "in_domain"
    assert "phase change" in payload["exclusions"]
    assert "radiation" in payload["exclusions"]

    # Read from the model record, never supplied: a caller cannot construct a
    # record claiming a shorter list, and a payload's own `exclusions` is not
    # read back, so a hand-edited report cannot shrink it either.
    assert "exclusions" not in ModelValidityRecord.__dataclass_fields__
    shrunk = dict(payload, exclusions=["nothing at all"])
    assert ModelValidityRecord.from_dict(shrunk).exclusions == record.exclusions

    # The one model that cannot declare them reports None, not an empty list.
    # A reader must be able to tell "nobody wrote them down" from "there are
    # none", and that is exactly the model this round could not edit.
    frozen = ModelValidityRecord(
        model_id="thermal.conduction1d.linear_diffusion",
        version="0.1.0",
        assessment=ValidityAssessment(
            status=ValidityStatus.UNKNOWN, unknown=("mesh_resolution",)
        ),
    )
    assert frozen.to_dict()["exclusions"] is None

    # And the exemption is stated by the DOMAIN layer, not by the core: the
    # universal core names no domain, and `test_x2` refused the first version
    # of this field for putting a model id in `definition.py`.
    from src import engcore
    from src.engcore.scientific.models.definition import (
        UNDECLARED_EXCLUSIONS_ATTRIBUTE,
    )

    stated = getattr(engcore.domains, UNDECLARED_EXCLUSIONS_ATTRIBUTE)
    assert any("conduction1d" in module for module in stated)
    assert all(reason.strip() for reason in stated.values())


def test_an_exclusion_is_not_an_assumption_and_the_records_are_separate():
    """Two fields because they answer different questions.

    An assumption is a condition a run can be checked against. An exclusion is
    a phenomenon that no condition can detect, because the model does not
    represent it. Collapsing them is how "no phase change" ended up in a tuple
    that no report carries.
    """
    by_id = {model.model_id: model for model in MODELS}
    lumped = by_id["thermal.lumped.first_order_capacity"]

    # The checkable one stays an assumption; it has a condition behind it.
    assert any("Biot" in a for a in lumped.assumptions)
    assert "biot_number" in lumped.validity.context_keys

    # The undetectable one is an exclusion, and no condition names it.
    assert "phase change" in lumped.exclusions
    assert not any(
        "phase" in name for name in lumped.validity.context_keys
    ), "a phase-change condition would make this an assumption, not an exclusion"


# =====================================================================
# GUARD 15 -- energy crossing a boundary says how much of it arrives
# =====================================================================
#
# The repository's one energy conversion was an ordinary dependency plus a
# sentence in a twin's assumptions. "All of it arrives" was what you got by
# writing nothing, and the next four systems all convert energy with real
# losses. A crossing that means "all of it arrives" and one that means "82 %
# arrives and the rest is heat" must not be written identically.


def test_a_crossing_that_carries_energy_must_say_how_much_arrives():
    """The fail-closed edge: a power-dimensioned dependency with no conversion.

    Enforced by dimension, so a domain does not have to opt in. An energy or a
    power moving between two problems either arrives whole or does not, and
    which of those is a claim somebody has to make.
    """
    from src.engcore.scientific.composition import (
        EnergyConversion,
        QuantityDependency,
    )

    common = dict(
        source_problem_id="shaft",
        source_quantity="friction_loss",
        target_problem_id="film",
        target_quantity="dissipated_power",
    )
    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityDependency(unit_exemplar="watt", **common)
    assert "declares no conversion" in str(excinfo.value)
    assert "deliberately not 1" in str(excinfo.value)

    # Energy, not only power.
    with pytest.raises(InvalidScientificProblem):
        QuantityDependency(unit_exemplar="joule", **common)

    # A crossing of anything else is transported, not converted, and may not
    # claim an efficiency -- a record that let a temperature declare one would
    # make the word mean nothing.
    temperature = QuantityDependency(
        source_problem_id="body",
        source_quantity="temperature",
        target_problem_id="material",
        target_quantity="temperature",
        unit_exemplar="kelvin",
    )
    assert temperature.conversion is None
    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityDependency(
            source_problem_id="body",
            source_quantity="temperature",
            target_problem_id="material",
            target_quantity="temperature",
            unit_exemplar="kelvin",
            conversion=EnergyConversion(
                name="not-a-conversion",
                input_form="a",
                output_form="b",
                unit_exemplar="watt",
                efficiency=1.0,
            ),
        )
    assert "is transported" in str(excinfo.value)


def test_an_undeclared_efficiency_is_unknown_and_never_one():
    """The confident-and-wrong failure, refused at the one place it arrives."""
    from src.engcore.scientific.composition import EnergyConversion
    from src.engcore.scientific.models.definition import ValidityStatus

    silent = EnergyConversion(
        name="motor",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
    )
    assert silent.efficiency is None
    assert silent.is_declared is False

    outcome = silent.convert(Quantity(100.0, "watt"))
    assert outcome.status is ValidityStatus.UNKNOWN
    assert outcome.value is None, "a lossless number was invented"
    assert "not assumed to be all of it" in outcome.reason

    # And a declared one answers, losses and all.
    from src.engcore.scientific.composition import LossPath

    declared = EnergyConversion(
        name="motor",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
        efficiency=0.82,
        losses=(LossPath(form="thermal", fraction=0.18),),
    )
    answered = declared.convert(Quantity(100.0, "watt"))
    assert answered.status is ValidityStatus.IN_DOMAIN
    assert answered.value == Quantity(82.0, "watt")
    assert answered.losses == {"thermal": Quantity(18.0, "watt")}


def test_conservation_is_checked_and_a_conversion_that_does_not_balance_fails():
    """What enters equals what leaves plus what is declared lost.

    Checked at declaration rather than at use: a conversion that does not
    balance is wrong before anything is run through it, and the caller who
    wrote it is the only one who can fix it.
    """
    from src.engcore.scientific.composition import EnergyConversion, LossPath

    base = dict(
        name="motor",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
    )

    # Loses energy and says nothing about where it went.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        EnergyConversion(efficiency=0.82, **base)
    assert "does not balance" in str(excinfo.value)
    assert "18 % that does not arrive has gone somewhere" in str(excinfo.value)

    # Declares a destination, and the fractions still do not add up.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        EnergyConversion(
            efficiency=0.82,
            losses=(LossPath(form="thermal", fraction=0.10),),
            **base,
        )
    assert "does not balance" in str(excinfo.value)

    # Accounts for more than it was given.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        EnergyConversion(
            efficiency=0.82,
            losses=(LossPath(form="thermal", fraction=0.30),),
            **base,
        )
    assert "more than it was given" in str(excinfo.value)

    # Balances, and constructs.
    balanced = EnergyConversion(
        efficiency=0.82,
        losses=(
            LossPath(form="thermal", fraction=0.15),
            LossPath(form="acoustic", fraction=0.03),
        ),
        **base,
    )
    assert balanced.efficiency == 0.82

    # Two paths to one destination is a duplicate or a disagreement, and this
    # record will not add them up on a caller's behalf.
    with pytest.raises(InvalidScientificProblem) as excinfo:
        EnergyConversion(
            efficiency=0.82,
            losses=(
                LossPath(form="thermal", fraction=0.09),
                LossPath(form="thermal", fraction=0.09),
            ),
            **base,
        )
    assert "two loss paths" in str(excinfo.value)


def test_the_conversion_appears_in_provenance_with_its_efficiency():
    """A report must show that a value crossed a boundary, and on what terms."""
    from src.engcore.scientific.composition import (
        QuantityDependency,
        QuantityTransfer,
    )
    from src.engcore.scientific.results.provenance import ProvenanceRecord
    from src.engcore.systems.electrothermal.coupled import (
        JOULE_HEATING_CONVERSION,
    )

    dependency = QuantityDependency(
        source_problem_id="electrical-series",
        source_quantity="resistor_power:R1",
        target_problem_id="thermal-lumped-R1",
        target_quantity="heat_input",
        unit_exemplar="watt",
        conversion=JOULE_HEATING_CONVERSION,
        name="joule-dissipation-heats-body",
    )
    record = ProvenanceRecord(
        run_id="r1",
        transfers=(
            QuantityTransfer(
                dependency=dependency,
                value=Quantity(4.0, "watt"),
                source_value=Quantity(4.0, "watt"),
                source_record_id="electrical-result-1",
                instant="iteration:3",
            ),
        ),
    )
    carried = record.to_dict()["transfers"][0]["dependency"]["conversion"]
    assert carried["input_form"] == "electrical"
    assert carried["output_form"] == "thermal"
    assert carried["efficiency"] == 1.0
    assert carried["losses"] == []

    # And it survives the round trip, efficiency and all.
    assert (
        ProvenanceRecord.from_dict(record.to_dict()).transfers[0].dependency
        == dependency
    )

    # An old record that declared no conversion is refused on read rather than
    # taken as lossless -- the same direction the writer refuses.
    stale = record.to_dict()
    stale["transfers"][0]["dependency"].pop("conversion")
    stale["transfers"][0]["dependency"]["schema"] = "quantity_dependency/1"
    with pytest.raises(InvalidScientificProblem):
        ProvenanceRecord.from_dict(stale)


def test_the_electrothermal_crossing_is_the_declaration_it_always_was():
    """Migrated, not changed: efficiency 1, no losses, and now written down.

    The twin has always asserted that the whole dissipated power enters the
    body. That sentence was the entire record of it. It is now a conversion
    that travels with the declaration and reaches a report, and it says the
    same thing.
    """
    from src.engcore.systems.electrothermal import resistor_body as rb
    from src.engcore.systems.electrothermal.coupled import (
        JOULE_HEATING_CONVERSION,
    )

    assert JOULE_HEATING_CONVERSION.efficiency == 1.0
    assert JOULE_HEATING_CONVERSION.losses == ()
    assert JOULE_HEATING_CONVERSION.crosses_forms is True
    assert JOULE_HEATING_CONVERSION.convert(
        Quantity(4.0, "watt")
    ).value == Quantity(4.0, "watt")

    # Both systems that make this crossing declare it, and neither leaves it
    # to be inferred from two dimensionally-compatible names.
    assert rb.JOULE_HEATING_CONVERSION.efficiency == 1.0


# =====================================================================
# GUARD 16 -- the declared conversion budget is spent on the real value
# =====================================================================
#
# GUARD 15 checks that a conversion's own declared numbers add up. That is a
# statement about the declaration and says nothing about the run. A conversion
# declaring that half the energy arrives, realized by a crossing that moved all
# of it, satisfies every check in GUARD 15 -- and every number downstream is
# then twice what the record claims. The budget has to be spent where the value
# actually crosses.


def _halving_motor():
    """A conversion with a real loss: half arrives, half leaves as heat."""
    from src.engcore.scientific.composition import EnergyConversion, LossPath

    return EnergyConversion(
        name="motor",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
        efficiency=0.5,
        losses=(LossPath(form="thermal", fraction=0.5),),
    )


def _conversion_edge(conversion):
    from src.engcore.scientific.composition import QuantityDependency

    return QuantityDependency(
        source_problem_id="electrical",
        source_quantity="drive_power",
        target_problem_id="mechanical",
        target_quantity="shaft_power",
        unit_exemplar="watt",
        conversion=conversion,
    )


def test_a_transfer_may_not_carry_more_than_its_conversion_budgets():
    """The gap GUARD 15 left: declared 0.5, transported all of it.

    Every check written before this one passes on that record. It is the
    confident-and-wrong crossing arriving through the realization instead of
    through the declaration.
    """
    from src.engcore.scientific.composition import QuantityTransfer

    edge = _conversion_edge(_halving_motor())
    common = dict(source_record_id="electrical-1", instant="iteration:1")

    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityTransfer(
            dependency=edge,
            value=Quantity(100.0, "watt"),
            source_value=Quantity(100.0, "watt"),
            **common,
        )
    assert "budgets" in str(excinfo.value)
    assert "efficiency of 0.5" in str(excinfo.value)

    # The budgeted one constructs, and says where the rest went.
    spent = QuantityTransfer(
        dependency=edge,
        value=Quantity(50.0, "watt"),
        source_value=Quantity(100.0, "watt"),
        **common,
    )
    assert spent.realized_losses == {"thermal": Quantity(50.0, "watt")}


def test_a_conversion_transfer_must_say_what_entered_and_a_transport_may_not():
    """A ratio needs both numbers, and a transport has only one."""
    from src.engcore.scientific.composition import (
        QuantityDependency,
        QuantityTransfer,
    )

    common = dict(source_record_id="electrical-1", instant="iteration:1")

    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityTransfer(
            dependency=_conversion_edge(_halving_motor()),
            value=Quantity(50.0, "watt"),
            **common,
        )
    assert "does not say what entered" in str(excinfo.value)

    transport = QuantityDependency(
        source_problem_id="body",
        source_quantity="temperature",
        target_problem_id="material",
        target_quantity="temperature",
        unit_exemplar="kelvin",
    )
    assert (
        QuantityTransfer(
            dependency=transport, value=Quantity(300.0, "kelvin"), **common
        ).realized_losses
        == {}
    )
    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityTransfer(
            dependency=transport,
            value=Quantity(300.0, "kelvin"),
            source_value=Quantity(300.0, "kelvin"),
            **common,
        )
    assert "is a transport, not a conversion" in str(excinfo.value)


def test_an_uncharacterised_conversion_cannot_be_realized_with_a_number():
    """Declaring the crossing is allowed; running a value through it is not.

    This is the drone's motor before anybody measures it. An efficiency nobody
    stated cannot become a definite arriving value, because the only way to
    produce one is to assume the crossing is lossless -- the assumption this
    whole record exists to stop being silent.
    """
    from src.engcore.scientific.composition import (
        EnergyConversion,
        QuantityTransfer,
    )

    uncharacterised = EnergyConversion(
        name="motor",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
    )
    assert uncharacterised.efficiency is None

    with pytest.raises(InvalidScientificProblem) as excinfo:
        QuantityTransfer(
            dependency=_conversion_edge(uncharacterised),
            value=Quantity(100.0, "watt"),
            source_value=Quantity(100.0, "watt"),
            source_record_id="electrical-1",
            instant="iteration:1",
        )
    assert "efficiency is not declared" in str(excinfo.value)


def test_the_coupling_loop_spends_the_budget_where_the_value_crosses():
    """`_transport` is the one place a value moves, so it is where it is spent.

    A record that is checked and a loop that ignores it would leave the
    declaration decorative. This drives the real transport boundary rather
    than the record, because they are two different things to get wrong.
    """
    from src.engcore.scientific.results.provenance import ProvenanceRecord
    from src.engcore.scientific.results.result import ScientificResult
    from src.engcore.systems.electrothermal import coupled as cp

    produced = ScientificResult(
        result_id="electrical-1",
        values={"drive_power": Quantity(100.0, "watt")},
        provenance=ProvenanceRecord(run_id="r1"),
    )

    # A lossless edge moves the whole value, exactly as before this existed.
    from src.engcore.systems.electrothermal.coupled import (
        JOULE_HEATING_CONVERSION,
    )

    lossless = _conversion_edge(JOULE_HEATING_CONVERSION)
    assert cp._transport(produced, lossless, 1) == Quantity(100.0, "watt")

    # A halving edge moves half. Before the binding this returned 100 W and
    # the declaration said 50 -- with nothing anywhere comparing the two.
    halved = cp._transport(produced, _conversion_edge(_halving_motor()), 1)
    assert halved == Quantity(50.0, "watt")

    # And an uncharacterised one refuses rather than moving all of it.
    from src.engcore.scientific.composition import EnergyConversion

    silent = _conversion_edge(
        EnergyConversion(
            name="motor",
            input_form="electrical",
            output_form="mechanical",
            unit_exemplar="watt",
        )
    )
    with pytest.raises(cp.TransportRefused) as excinfo:
        cp._transport(produced, silent, 1)
    assert "efficiency is not declared" in str(excinfo.value)
