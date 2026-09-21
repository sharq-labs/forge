"""What a fit and a sensitivity index may and may not become.

Two of P20's twelve, and they are the two that stop an external provider from
manufacturing the kind of evidence Forge exists to require:

7. PyBOP cannot access validation or holdout data.
8. SALib evidence cannot count as validation evidence.

Both are enforced by types rather than by review. A rule that lives in a
comment is a rule that survives exactly as long as the reviewer who remembers
it, and both of these failures are silent: a model fitted on validation data
scores beautifully, and a sensitivity index promoted to validation looks like
coverage.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from engcore.providers import ExecutionOutcome
from engcore.providers import pybop_provider as bop
from engcore.providers import salib_provider as sal

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

TIME = tuple(float(i) * 10.0 for i in range(24))
CURRENT = tuple(2.0 for _ in TIME)
VOLTAGE = tuple(4.0 - 0.002 * i for i in range(24))

PARAMETERS = (
    bop.FitParameter(name="R0 [Ohm]", lower=0.01, upper=0.4, initial=0.1),
)


def _dataset(role: bop.DatasetRole) -> bop.FitDataset:
    return bop.FitDataset(
        dataset_id=f"nasa.B0005.{role.value}",
        role=role,
        time_s=TIME,
        current_a=CURRENT,
        terminal_voltage_v=VOLTAGE,
    )


def _provider(dataset: bop.FitDataset) -> bop.PyBOPProvider:
    return bop.PyBOPProvider(
        dataset=dataset,
        parameters=PARAMETERS,
        model_factory=_unreachable,
        parameter_values_factory=_unreachable,
    )


def _unreachable(*args, **kwargs):
    raise AssertionError(
        "the fitting machinery was reached for a dataset the role check should "
        "have refused before PyBOP was touched"
    )


# =====================================================================
# 7. PyBOP cannot access validation or holdout data
# =====================================================================

@pytest.mark.parametrize(
    "role",
    [
        bop.DatasetRole.VALIDATION,
        bop.DatasetRole.HOLDOUT,
        bop.DatasetRole.OBSERVED_HOLDOUT,
        bop.DatasetRole.UNSPECIFIED,
    ],
)
def test_pybop_cannot_fit_anything_but_calibration_data(role):
    """Four roles, four refusals, and PyBOP is never imported for any of them.

    ``_unreachable`` is the model factory: if the refusal were checked after
    the machinery was built, the factory would raise and this test would fail
    with a different message. The refusal has to come first.
    """
    outcome = _provider(_dataset(role)).execute(
        bop.build_fit_request(
            dataset=_dataset(role), parameters=PARAMETERS, qoi="terminal_voltage"
        )
    )
    assert outcome.outcome is ExecutionOutcome.FORGE_REFUSED
    assert outcome.evidence is None and outcome.result is None
    assert role.value in outcome.receipt.detail
    assert "calibration data only" in outcome.receipt.detail


def test_only_calibration_may_be_fitted_and_the_enum_says_so():
    """The predicate, asserted over the whole enum rather than the four above.

    A role added later that forgot to be refused would pass the parametrised
    test above by simply not being in its list. This one cannot be evaded.
    """
    allowed = {role for role in bop.DatasetRole if role.may_be_fitted}
    assert allowed == {bop.DatasetRole.CALIBRATION}


def test_unspecified_is_a_role_and_is_refused():
    """Unscreened is not calibration, and defaulting it would be the whole bug."""
    assert not bop.DatasetRole.UNSPECIFIED.may_be_fitted
    with pytest.raises(ValueError, match="DatasetRole"):
        bop.FitDataset(
            dataset_id="d",
            role="calibration",  # a string that looks right and is not a role
            time_s=TIME,
            current_a=CURRENT,
            terminal_voltage_v=VOLTAGE,
        )


def test_relabelling_a_dataset_changes_its_digest():
    """A dataset cannot be laundered into calibration without it being visible."""
    validation = _dataset(bop.DatasetRole.VALIDATION)
    relabelled = bop.FitDataset(
        dataset_id=validation.dataset_id,
        role=bop.DatasetRole.CALIBRATION,
        time_s=validation.time_s,
        current_a=validation.current_a,
        terminal_voltage_v=validation.terminal_voltage_v,
    )
    assert relabelled.digest() != validation.digest()


def test_a_fit_is_evidence_and_never_a_scientific_result():
    """A fit arriving as a ScientificResult would be admissible as a prediction.

    Checked over the AST, not the text: the module's docstring says the word
    while explaining why a fit is not one, and a substring search reported that
    sentence as the violation on the first run.
    """
    tree = ast.parse(
        (REPO_ROOT / "src" / "engcore" / "providers" / "pybop_provider.py").read_text(
            encoding="utf-8"
        )
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "ScientificResult":
            pytest.fail(f"pybop_provider.py names ScientificResult in code at line {node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr == "ScientificResult":
            pytest.fail(f"pybop_provider.py reaches ScientificResult at line {node.lineno}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ProviderResult"
        ):
            assert all(k.arg != "result" for k in node.keywords), (
                f"the fitting provider builds a ProviderResult carrying a "
                f"scientific answer at line {node.lineno}"
            )


def test_a_fit_reports_absent_parameter_uncertainty_as_absent():
    """Missing uncertainty never becomes zero -- the Core's rule, in this record."""
    evidence = bop.FitEvidence(
        dataset_id="d",
        dataset_digest="x" * 64,
        dataset_role="calibration",
        parameters=(PARAMETERS[0].to_dict(),),
        optimiser="SciPyMinimize",
        objective="RootMeanSquaredError",
        best_values={"R0 [Ohm]": 0.12},
        final_cost=0.001,
        parameter_uncertainty=None,
    )
    payload = evidence.to_dict()
    assert payload["parameter_uncertainty"] is None
    assert payload["is_validation_evidence"] is False


# =====================================================================
# 8. SALib evidence cannot count as validation evidence
# =====================================================================

def test_salib_evidence_cannot_count_as_validation_evidence():
    """``is_validation_evidence`` is a constant property, not a settable field.

    Asserted structurally as well as by value: a field could be set by a
    constructor argument or a payload key, and a property returning a literal
    cannot be.
    """
    evidence = sal.SensitivityEvidence(
        method="morris",
        qoi="terminal_voltage",
        scenario_id="s",
        provider_version="1.6.0",
        parameters=({"name": "R0", "lower": 0.0, "upper": 1.0},),
        indices={"R0": {"mu_star": 1.0}},
        ranking=("R0",),
        primary_index="mu_star",
        sample_count=10,
        failed_evaluations=0,
    )
    assert evidence.is_validation_evidence is False
    assert evidence.to_dict()["is_validation_evidence"] is False

    descriptor = type(evidence).__dict__["is_validation_evidence"]
    assert isinstance(descriptor, property), (
        "is_validation_evidence became a field, which a caller can set"
    )
    assert descriptor.fset is None, "a setter appeared on is_validation_evidence"
    with pytest.raises(AttributeError):
        evidence.is_validation_evidence = True  # type: ignore[misc]

    fields = {f for f in sal.SensitivityEvidence.__dataclass_fields__}
    assert "is_validation_evidence" not in fields


def test_sensitivity_evidence_states_what_it_is_not():
    """The record carries its own limit, so a reader of the payload sees it too."""
    evidence = sal.SensitivityEvidence(
        method="sobol",
        qoi="terminal_voltage",
        scenario_id="s",
        provider_version="1.6.0",
        parameters=(),
        indices={},
        ranking=(),
        primary_index="S1",
        sample_count=0,
        failed_evaluations=0,
    )
    text = evidence.to_dict()["what_this_is_not"]
    assert "validation level" in text
    assert "agreement with a measurement" in text


def test_the_sensitivity_provider_grants_no_validation_level():
    """No ValidationLevel and no ValidationCheck anywhere in the SALib adapter."""
    source = (
        REPO_ROOT / "src" / "engcore" / "providers" / "salib_provider.py"
    ).read_text(encoding="utf-8")
    assert "ValidationLevel" not in source
    assert "ValidationCheck" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "establishes":
            pytest.fail("the sensitivity adapter touches `establishes`")


def test_a_failed_design_point_is_missing_evidence_and_is_not_repaired():
    """A hole in the design is not a zero, and filling it fabricates a variance.

    SALib is required for this one: the refusal happens after sampling, which
    is SALib's, and asserting it against a stub would assert nothing about the
    real path.
    """
    pytest.importorskip("SALib")
    provider = sal.SALibProvider(
        method="morris",
        parameters=[
            sal.SensitivityParameter("R0", 0.05, 0.3),
            sal.SensitivityParameter("R1", 0.01, 0.2),
        ],
        qoi="terminal_voltage",
        scenario_id="unit",
        evaluator=lambda point: None if point["R0"] > 0.2 else 1.0,
        samples=4,
    )
    request = sal.build_sensitivity_request(
        method="morris",
        parameters=[
            sal.SensitivityParameter("R0", 0.05, 0.3),
            sal.SensitivityParameter("R1", 0.01, 0.2),
        ],
        qoi="terminal_voltage",
        scenario_id="unit",
        samples=4,
    )
    outcome = provider.execute(request)
    assert outcome.outcome is ExecutionOutcome.MISSING_EVIDENCE
    assert outcome.outcome.is_forge_side
    assert outcome.evidence is None
    assert "substituted value" in outcome.receipt.detail


def test_the_three_methods_are_the_declared_ones_and_no_more():
    """P6 names Morris, Sobol and FAST. An allowlist, not a dispatch on input."""
    assert set(sal.METHODS) == {"morris", "sobol", "fast"}
    assert set(sal.PRIMARY_INDEX) == set(sal.METHODS)
    provider = sal.SALibProvider(
        method="delta",
        parameters=[sal.SensitivityParameter("R0", 0.0, 1.0)],
        qoi="terminal_voltage",
        scenario_id="unit",
        evaluator=lambda point: 1.0,
    )
    outcome = provider.execute(
        sal.build_sensitivity_request(
            method="delta",
            parameters=[sal.SensitivityParameter("R0", 0.0, 1.0)],
            qoi="terminal_voltage",
            scenario_id="unit",
            samples=4,
        )
    )
    assert outcome.outcome is ExecutionOutcome.FORGE_REFUSED
