"""The provider contract's load-bearing properties, on a bare install and a full one.

Five of P20's twelve live here, and they are the five that do not need a
provider installed to mean something:

1. Forge imports without the provider extras.
2. The PyBaMM provider's version is recorded.
3. A model or parameter change moves the authority/identity digests.
4. Canonical QoIs are provider-independent.
10. A provider failure is distinct from a scientific refusal.

Plus two guards that close holes this package would otherwise open: no
validation check under ``providers/`` may grant an evidentiary level, and the
license manifest has to actually cover the three providers.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from engcore.providers import (
    ExecutionOutcome,
    ProviderCapability,
    ProviderError,
    ProviderExecutionReceipt,
    ProviderIdentity,
    ProviderRequest,
    ProviderResult,
    manifest_rows,
)
from engcore.providers import pybamm_provider as pp
from engcore.providers.environment import EnvironmentIdentity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROVIDERS = REPO_ROOT / "src" / "engcore" / "providers"


CELL = pp.CellUnderTest(
    cell_id="B0005",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    ambient_temperature_k=297.0,
)
PROTOCOL = pp.CurrentProtocol(duration_s=1800.0, constant_current_a=2.0)

AUTHORITY = pp.ParameterAuthority(
    authority_id="test.nasa_18650",
    source="forge_declared",
    parameter_set_name="ECM_Example",
    defining_provider_version="pybamm",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    temperature_validity_k=(293.15, 313.15),
)


def _request(model_key="thevenin_1rc", authority=AUTHORITY, qois=("terminal_voltage", "time")):
    return pp.build_request(
        model_key=model_key,
        authority=authority,
        cell=CELL,
        protocol=PROTOCOL,
        qois=qois,
        initial_state_of_charge=0.95,
    )


# =====================================================================
# 1. Forge imports without the provider extras
# =====================================================================

def test_forge_imports_without_the_provider_extras():
    """P17, executed rather than asserted about.

    Run in a **subprocess** with the three provider distributions hidden from
    the import system, because this interpreter may have them installed and an
    in-process check would then prove nothing. The child imports the Core, the
    whole providers package and every adapter; if any of them reached for
    PyBaMM at module scope, the import fails and so does this test.
    """
    script = (
        "import sys\n"
        "class Block:\n"
        "    def find_module(self, name, path=None):\n"
        "        return None\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('pybamm', 'pybop', 'SALib'):\n"
        "            raise ImportError('blocked for this test: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import engcore\n"
        "import engcore.scientific, engcore.execution, engcore.studies\n"
        "import engcore.providers\n"
        "import engcore.providers.pybamm_provider as a\n"
        "import engcore.providers.pybop_provider as b\n"
        "import engcore.providers.salib_provider as c\n"
        "import engcore.credibility.risk_coverage as d\n"
        "print('OK', sorted(a.ALLOWED_MODELS), sorted(c.METHODS))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={
            "PATH": "",
            "SYSTEMROOT": "C:\\Windows",
            "PYTHONPATH": str(REPO_ROOT / "src"),
        },
    )
    assert done.returncode == 0, (
        f"importing Forge with the provider packages blocked failed:\n"
        f"{done.stdout}\n{done.stderr}"
    )
    assert done.stdout.startswith("OK"), done.stdout


def test_an_absent_provider_produces_a_result_and_not_an_exception():
    """The other half of P17: a clear provider-unavailable *result*.

    An exception would make every caller write the same try/except, and one of
    them would eventually catch it as a scientific outcome.
    """
    from engcore.providers.contract import unavailable_result

    outcome = unavailable_result(_request(), "not installed")
    assert outcome.outcome is ExecutionOutcome.PROVIDER_UNAVAILABLE
    assert outcome.result is None
    assert outcome.outcome.is_provider_side
    assert not outcome.outcome.is_forge_side


# =====================================================================
# 2. The provider version is recorded
# =====================================================================

def test_the_pybamm_provider_version_is_recorded():
    """Every field of provider identity is required and none may be blank.

    The version that reaches a record is read from the installed distribution
    at run time (:meth:`PyBaMMProvider._identity` uses ``pybamm.__version__``);
    what is asserted here, without needing PyBaMM, is that a record *cannot* be
    built without one.
    """
    identity = ProviderIdentity(
        provider_name="pybamm",
        provider_version="26.8.0.0",
        model_identity="pybamm.lithium_ion.SPMe@spme",
        solver_identity="IDAKLUSolver",
        configuration_digest="c" * 64,
        environment_identity="e" * 64,
        adapter_version=pp.ADAPTER_VERSION,
    )
    assert identity.to_dict()["provider_version"] == "26.8.0.0"
    for blank in ("provider_version", "model_identity", "environment_identity"):
        fields = dict(
            provider_name="pybamm",
            provider_version="26.8.0.0",
            model_identity="m",
            solver_identity="s",
            configuration_digest="c",
            environment_identity="e",
            adapter_version="a",
        )
        fields[blank] = "   "
        with pytest.raises(ProviderError, match=blank):
            ProviderIdentity(**fields)


def test_the_environment_identity_records_versions_and_no_locations():
    """P10 recorded, and the ngspice rule kept: versions, never paths.

    A path in a scientific record means relocating a file mints a different
    record. A *version* is not a path -- it selects which code ran -- so it
    belongs, and the distinction is asserted rather than trusted.
    """
    environment = EnvironmentIdentity.capture()
    payload = environment.to_dict()
    assert set(payload) == {"python_version", "platform_tag", "distributions"}
    flat = repr(payload)
    for forbidden in (str(REPO_ROOT), "site-packages", "\\Users\\", "/home/"):
        assert forbidden not in flat, f"a location leaked into the environment record: {forbidden}"


# =====================================================================
# 3. Model and parameter changes move the digests
# =====================================================================

def test_model_and_parameter_changes_move_the_authority_digests():
    other = AUTHORITY.derive(
        authority_id="test.nasa_18650/fitted",
        overrides={"R0 [Ohm]": 0.11},
        notes="one override",
    )
    assert other.digest() != AUTHORITY.digest()
    assert other.parent_authority_digest == AUTHORITY.digest()
    assert other.source == "forge_derived"

    again = other.derive(
        authority_id="test.nasa_18650/fitted2",
        overrides={"R0 [Ohm]": 0.12},
    )
    assert again.digest() != other.digest(), "a changed override must move the digest"

    # And the request digest follows the authority it cites.
    assert _request(authority=AUTHORITY).digest() != _request(authority=other).digest()
    # ... and the model.
    assert _request(model_key="thevenin_1rc").digest() != _request(model_key="spm").digest()


def test_a_named_parameter_set_cannot_be_mutated_in_place():
    """P4's rule, enforced by the type rather than by a convention.

    A named set carrying overrides would cite the publisher for numbers the
    publisher did not state.
    """
    with pytest.raises(ValueError, match="mutated"):
        pp.ParameterAuthority(
            authority_id="pybamm.Chen2020/edited",
            source="pybamm_named_set",
            parameter_set_name="Chen2020",
            defining_provider_version="pybamm",
            chemistry="NMC811/graphite-SiOx",
            nominal_capacity_ah=5.0,
            temperature_validity_k=(288.15, 308.15),
            overrides={"Nominal cell capacity [A.h]": 2.0},
        )
    named = pp.NAMED_AUTHORITIES["Chen2020"]
    before = named.digest()
    derived = named.derive(authority_id="x", overrides={"a": 1})
    assert named.digest() == before, "deriving must not touch the parent"
    assert derived.digest() != before


def test_deriving_with_no_overrides_is_refused():
    with pytest.raises(ValueError, match="no overrides"):
        AUTHORITY.derive(authority_id="test.pointless", overrides={})


# =====================================================================
# 4. Canonical QoIs are provider-independent
# =====================================================================

def test_canonical_qois_are_provider_independent():
    """The names a provider answers in are the domain's names, not PyBaMM's.

    Two halves. The Forge-facing names must be the battery domain's own
    constants -- so a consumer cannot tell a PyBaMM terminal voltage from a
    native one -- and no PyBaMM spelling may appear on the Forge side of the
    map.
    """
    from engcore.domains.battery import context as bctx
    from engcore.domains.battery import flagship as bflag

    assert bflag.TERMINAL_VOLTAGE_METRIC in pp.CANONICAL_QOIS
    assert bflag.STATE_OF_CHARGE_METRIC in pp.CANONICAL_QOIS
    assert bctx.CELL_TEMPERATURE in pp.CANONICAL_QOIS
    for canonical in pp.CANONICAL_QOIS:
        assert "[" not in canonical and canonical == canonical.lower(), (
            f"{canonical!r} is provider spelling on the Forge side of the map"
        )
    for spec in pp.MODEL_CATALOGUE.values():
        assert spec.produces <= set(pp.CANONICAL_QOIS), spec.model_key


def test_asking_a_model_for_a_quantity_it_does_not_produce_is_refused():
    """Absent is absent. SPM has no state of charge variable and gets none."""
    provider = pp.PyBaMMProvider(authority=AUTHORITY, cell=CELL, protocol=PROTOCOL)
    outcome = provider.execute(
        _request(model_key="spm", qois=("terminal_voltage", "state_of_charge"))
    )
    assert outcome.outcome is ExecutionOutcome.FORGE_REFUSED
    assert "state_of_charge" in outcome.receipt.detail
    assert "not zero" in outcome.receipt.detail


# =====================================================================
# 10. Provider failure is distinct from scientific refusal
# =====================================================================

def test_provider_failure_is_distinct_from_scientific_refusal():
    """P12's separation, as the property that divides the enum.

    The two halves must not overlap and must not be empty, and ``OK`` must be
    in neither: it is the handover, not a verdict.
    """
    provider_side = {o for o in ExecutionOutcome if o.is_provider_side}
    forge_side = {o for o in ExecutionOutcome if o.is_forge_side}
    assert provider_side == {
        ExecutionOutcome.PROVIDER_UNAVAILABLE,
        ExecutionOutcome.PROVIDER_ERROR,
        ExecutionOutcome.NUMERICAL_FAILURE,
    }
    assert forge_side == {
        ExecutionOutcome.MODEL_NOT_APPLICABLE,
        ExecutionOutcome.FORGE_REFUSED,
        ExecutionOutcome.MISSING_EVIDENCE,
    }
    assert not provider_side & forge_side
    assert not ExecutionOutcome.OK.is_provider_side
    assert not ExecutionOutcome.OK.is_forge_side
    assert ExecutionOutcome.OK.delivered
    assert not any(o.delivered for o in provider_side | forge_side)


def test_a_provider_error_is_not_a_scientific_error():
    """It inherits Exception, never ScientificCoreError. The ngspice rule."""
    from engcore.scientific.errors import ScientificCoreError

    assert not issubclass(ProviderError, ScientificCoreError)


def test_a_non_delivering_outcome_cannot_carry_a_payload():
    """A refusal with a result beside it is a number somebody will read."""
    receipt = ProviderExecutionReceipt(
        identity=None,
        request_digest="d" * 64,
        outcome=ExecutionOutcome.MODEL_NOT_APPLICABLE,
        detail="outside applicability",
    )
    with pytest.raises(ProviderError, match="carries a payload"):
        ProviderResult(receipt=receipt, evidence={"anything": 1})


def test_a_delivered_result_must_name_who_produced_it():
    with pytest.raises(ProviderError, match="anonymous"):
        ProviderExecutionReceipt(
            identity=None,
            request_digest="d" * 64,
            outcome=ExecutionOutcome.OK,
        )


# =====================================================================
# Guards this package opens, closed here
# =====================================================================

def test_no_provider_validation_check_grants_an_evidentiary_level():
    """The hole `tests/domains/test_evidentiary_level_audit.py` does not cover.

    That audit walks ``src/engcore/domains/**`` for ``ValidationCheck(...)``
    constructions and holds each against a written decision about whether it
    may earn a ``ValidationLevel``. ``src/engcore/providers/`` is outside its
    scope, so without this check a provider adapter could set ``establishes=``
    on anything and no audit would notice.

    The answer for every provider check is the same and needs no table: an
    external solver's self-consistency check compares an output against the
    shape it was asked for, with no independent reference. External solver
    reputation is not evidence for a specific prediction (P9), so nothing here
    may mint a level that would let it become one.
    """
    offenders = []
    for path in sorted(PROVIDERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ValidationCheck"
            ):
                for keyword in node.keywords:
                    if keyword.arg == "establishes":
                        offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"these provider validation checks grant an evidentiary level: "
        f"{offenders}. No audit covers src/engcore/providers/"
    )


def test_the_license_manifest_covers_every_provider():
    """P19: diligence visibility, and it has to be complete to be that."""
    rows = {row["provider"]: row for row in manifest_rows()}
    assert set(rows) == {"pybamm", "pybop", "salib"}
    for name, row in rows.items():
        assert row["license_identifier"], name
        assert row["source_repository"].startswith("https://"), name
        assert row["integration_mode"] == "optional runtime import", name
        assert "not vendored" in row["distribution_implication"], name


def test_the_provider_package_imports_nothing_above_it():
    """`providers` is an outer boundary: it must not reach claims, sria or mcp.

    A provider adapter that imported the claim layer could shape a verdict from
    inside the thing being judged.
    """
    forbidden = {"claims", "sria", "mcp", "credibility", "product", "design"}
    offenders = []
    for path in sorted(PROVIDERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.ImportFrom) and node.level >= 1:
                names = [(node.module or "")]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                head = name.split(".")[0]
                if head in forbidden or name.startswith(
                    tuple(f"engcore.{f}" for f in forbidden)
                ):
                    offenders.append(f"{path.name} -> {name}")
    assert not offenders, offenders


def test_the_capability_set_is_one_per_provider():
    """P13: no capability graph. A provider declares a set, a request names one."""
    assert set(ProviderCapability) == {
        ProviderCapability.TIME_SERIES_SIMULATION,
        ProviderCapability.PARAMETER_INFERENCE,
        ProviderCapability.SENSITIVITY_ANALYSIS,
    }
    provider = pp.PyBaMMProvider(authority=AUTHORITY, cell=CELL, protocol=PROTOCOL)
    outcome = provider.execute(
        ProviderRequest(
            capability=ProviderCapability.PARAMETER_INFERENCE,
            model_key="thevenin_1rc",
            parameter_authority=AUTHORITY.digest(),
            qois=("terminal_voltage",),
        )
    )
    assert outcome.outcome is ExecutionOutcome.FORGE_REFUSED


def test_a_model_off_the_allowlist_is_refused_with_no_fallback():
    provider = pp.PyBaMMProvider(authority=AUTHORITY, cell=CELL, protocol=PROTOCOL)
    outcome = provider.execute(_request(model_key="pybamm.lithium_ion.MPM"))
    assert outcome.outcome is ExecutionOutcome.FORGE_REFUSED
    assert "no fallback" in outcome.receipt.detail


def test_fidelity_is_a_label_and_not_an_order():
    """P3: no global ranking anywhere in the catalogue or the code that reads it."""
    classes = [spec.fidelity_class for spec in pp.MODEL_CATALOGUE.values()]
    assert len(set(classes)) == len(classes), "fidelity classes must be distinct labels"
    source = (PROVIDERS / "pybamm_provider.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            rendered = ast.unparse(node)
            assert "fidelity" not in rendered, (
                f"fidelity_class is being compared, which makes it an order: "
                f"{rendered}"
            )
    for spec in pp.MODEL_CATALOGUE.values():
        assert spec.physics_excluded, (
            f"{spec.model_key} declares no exclusions, so no refusal about it "
            f"could ever be stated"
        )
