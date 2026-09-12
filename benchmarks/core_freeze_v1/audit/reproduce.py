"""Core Freeze V1: every fact the freeze says is deterministic, as one JSON document.

Run this in any process that can import ``engcore`` and it prints the same
bytes -- that is the whole claim, and the driver (``freeze_reproduction.py``)
tests it by running this file under different hash seeds, different working
directories, the source checkout and the installed wheel, and comparing the
outputs byte for byte.

Deliberately self-contained: standard library and ``engcore`` only. It is
copied into the wheel's work directory and run under ``python -S -E`` there, so
it cannot import anything from ``tests/``, ``tools/`` or this repository.

NOTHING HERE IS NEW SEMANTICS. Every identity pair below is one Sprint 10
already asserted in ``tests/test_core_api_serialization.py``; every fixture is
built the same way through public constructors. This file does not decide what
the contract is -- it makes the existing contract print itself so that two
environments can be compared.

What is deliberately NOT in the output: anything the contract does not promise
to be stable. Wall-clock seconds, tracebacks (they carry file paths), memory
addresses, and error PROSE from the scientific core -- the freeze policy
excludes undocumented error text, so reading it here would make it load-bearing.

    python -X utf8 benchmarks/core_freeze_v1/audit/reproduce.py
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import sys
import textwrap

SCHEMA = "engcore.core_freeze_reproduction/1"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical(payload) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


# =====================================================================
# API
# =====================================================================

def api_section() -> dict:
    from engcore import api_snapshot

    full = api_snapshot.build()
    frozen = api_snapshot.frozen_only(full)
    experimental = sorted(
        [e["module"], e["name"]] for e in full["symbols"]
        if e["classification"] == "EXPERIMENTAL"
    )
    classifications: dict[str, int] = {}
    for entry in full["symbols"]:
        classifications[entry["classification"]] = (
            classifications.get(entry["classification"], 0) + 1
        )
    return {
        "frozen_digest": api_snapshot.frozen_digest(full),
        "full_digest": api_snapshot.digest(full),
        "frozen_count": frozen["symbol_count"],
        "total_count": full["symbol_count"],
        "experimental": experimental,
        "classifications": dict(sorted(classifications.items())),
        "deprecated": sorted(
            [m, n] for (m, n) in api_snapshot.DEPRECATED_SYMBOLS
        ),
        "frozen_canonical_bytes_sha256": sha(api_snapshot.canonical_bytes(frozen)),
        "canonical_modules": list(api_snapshot.CANONICAL_MODULES),
    }


# =====================================================================
# SERIALIZATION
# =====================================================================

def frozen_classes():
    from engcore import api_snapshot

    for entry in api_snapshot.frozen_only()["symbols"]:
        if entry["kind"] in ("dataclass", "class"):
            yield entry, getattr(importlib.import_module(entry["module"]), entry["name"])


def fixtures() -> dict:
    """Identical construction to ``tests/test_core_api_serialization.py::fixtures``."""
    from engcore.adequacy import PredictiveEvidenceIdentity
    from engcore.inference import (
        CalibrationParameterSet, FieldObservationOperator, ParameterBounds,
        ParameterEstimate, ParameterIdentity,
    )
    from engcore.inference.field_observation import FieldObservationKind
    from engcore.scientific import (
        ModelReference, ProvenanceRecord, Quantity as Q, SolverIdentity,
        TwinReference, ValidationReport,
    )
    from engcore.scientific.fields.mesh import StructuredMesh

    model = ModelReference(model_id="m.demo", version="1.0.0")
    twin = TwinReference(twin_id="t.demo", version="1")
    mesh = StructuredMesh(
        mesh_id="plate", length_x=Q(0.04, "meter"), length_y=Q(0.04, "meter"),
        nodes_x=5, nodes_y=5,
    )
    parameter = ParameterIdentity(
        name="reference_resistance", unit="ohm", model=model,
        bounds=ParameterBounds(Q(0.0, "ohm"), Q(10.0, "ohm")),
    )
    return {
        "Quantity": Q(1.5, "ohm"),
        "ModelReference": model,
        "TwinReference": twin,
        "SolverIdentity": SolverIdentity("s.demo", "1.0"),
        "ValidationReport": ValidationReport(),
        "ProvenanceRecord": ProvenanceRecord(run_id="r-1"),
        "ParameterIdentity": parameter,
        "ParameterEstimate": ParameterEstimate(parameter, 2.5),
        "CalibrationParameterSet": CalibrationParameterSet((parameter,)),
        "PredictiveEvidenceIdentity": PredictiveEvidenceIdentity(
            observation_key="c:y", observed_value=1.0, unit="ohm",
            likelihood_sigma=0.1, heldout_dataset_id="h", posterior_dataset_id="p",
            twin=twin,
        ),
        # EXPERIMENTAL. Kept because Sprint 10's fixture set includes it, and
        # labelled below so it is never counted as frozen evidence.
        "FieldObservationOperator": FieldObservationOperator(
            operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION,
            field_id="temperature", mesh_fingerprint=mesh.fingerprint(),
            unit="kelvin", probe_x=Q(0.02, "meter"), probe_y=Q(0.01, "meter"),
        ),
    }


EXPERIMENTAL_FIXTURES = frozenset({"FieldObservationOperator"})

#: The eight frozen readers that accept older schema versions.
LEGACY_READERS = (
    "ScientificResult", "ProvenanceRecord", "CrossSolverConsensus",
    "RawSolverOutput", "ScientificModelDefinition", "ValidityAssessment",
    "QuantityDependency", "QuantityTransfer",
)


def declared_schemas(klass) -> list[str] | None:
    """The version strings ``klass.from_dict`` hands to ``require_schema_any``.

    Read from the reader's SOURCE and resolved against its module, not parsed
    out of the refusal message: error prose is explicitly not part of the frozen
    contract, and reading it here would quietly make it so. Works identically
    in the installed wheel, because the wheel ships the ``.py`` files.
    """
    method = klass.__dict__.get("from_dict")
    function = getattr(method, "__func__", method)
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    module = sys.modules[klass.__module__]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "require_schema_any" or len(node.args) < 2:
            continue
        accepted = node.args[1]
        if isinstance(accepted, ast.Name):
            return [str(v) for v in getattr(module, accepted.id)]
        if isinstance(accepted, ast.Tuple):
            return [str(getattr(module, element.id)) for element in accepted.elts]
    return None


def serialization_section() -> dict:
    import engcore.scientific as scientific

    classes = list(frozen_classes())
    round_trip = sorted(
        f"{e['module']}.{e['name']}" for e, k in classes
        if hasattr(k, "to_dict") and hasattr(k, "from_dict")
    )
    export_only = sorted(
        f"{e['module']}.{e['name']}" for e, k in classes
        if hasattr(k, "to_dict") and not hasattr(k, "from_dict")
    )

    payloads = {}
    for name, record in sorted(fixtures().items()):
        first = record.to_dict()
        first_bytes = canonical(first)
        second_bytes = canonical(type(record).from_dict(first).to_dict())
        refused = None
        if "schema" in first:
            future = dict(first)
            future["schema"] = first["schema"] + ".from-the-future"
            try:
                type(record).from_dict(future)
                refused = False
            except Exception:  # noqa: BLE001 - WHICH exception is not the claim
                refused = True
        payloads[name] = {
            "classification": (
                "EXPERIMENTAL" if name in EXPERIMENTAL_FIXTURES else "FREEZE"
            ),
            "canonical_sha256": sha(first_bytes),
            "round_trip_byte_identical": first_bytes == second_bytes,
            "schema": first.get("schema"),
            "unknown_version_refused": refused,
        }

    legacy = {}
    for name in LEGACY_READERS:
        klass = getattr(scientific, name)
        versions = declared_schemas(klass)
        undeclared = (versions[-1].rsplit("/", 1)[0] + "/999") if versions else None
        try:
            klass.from_dict({"schema": undeclared})
            undeclared_refused = False
        except Exception:  # noqa: BLE001
            undeclared_refused = True
        legacy[name] = {
            "accepted_versions": versions,
            "undeclared_version": undeclared,
            "undeclared_version_refused": undeclared_refused,
        }

    return {
        "round_trippable_count": len(round_trip),
        "export_only_count": len(export_only),
        "export_only": export_only,
        "round_trippable_sha256": sha(canonical(round_trip)),
        "fixtures": payloads,
        "legacy_readers": legacy,
    }


# =====================================================================
# IDENTITY -- the Sprint 10 pairs, unchanged
# =====================================================================

def identity_section() -> dict:
    from engcore.adequacy import PredictiveEvidenceIdentity
    from engcore.inference import (
        CalibrationParameterSet, ParameterBounds, ParameterIdentity,
    )
    from engcore.inference.field_observation import (
        FieldObservationKind, FieldObservationOperator,
    )
    from engcore.scientific import ModelReference, TwinReference
    from engcore.scientific.fields.mesh import StructuredMesh
    from engcore.scientific.units.quantity import Quantity as Q

    def param(name="r", unit="ohm", model=("m.a", "1"), lo=(0.0, "ohm"), hi=(10.0, "ohm")):
        return ParameterIdentity(
            name, unit, ModelReference(*model),
            ParameterBounds(Q(lo[0], lo[1]), Q(hi[0], hi[1])),
        )

    def operator(nodes=5, description=""):
        mesh = StructuredMesh(
            mesh_id="plate", length_x=Q(0.04, "meter"), length_y=Q(0.04, "meter"),
            nodes_x=nodes, nodes_y=nodes,
        )
        return FieldObservationOperator(
            operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION,
            field_id="temperature", mesh_fingerprint=mesh.fingerprint(),
            unit="kelvin", probe_x=Q(0.02, "meter"), probe_y=Q(0.01, "meter"),
            description=description,
        )

    def evidence(observed):
        return PredictiveEvidenceIdentity(
            observation_key="c:y", observed_value=observed, unit="ohm",
            likelihood_sigma=0.1, heldout_dataset_id="h", posterior_dataset_id="p",
            twin=TwinReference("t", "1"),
        )

    r = param()
    a = param("a", "1/kelvin", lo=(-0.01, "1/kelvin"), hi=(0.01, "1/kelvin"))

    # (name, a, b, expected_equal, classification)
    pairs = [
        ("material:model", param(), param(model=("m.b", "1")), False, "FREEZE"),
        ("material:unit", param(),
         param(unit="milliohm", lo=(0.0, "milliohm"), hi=(10.0, "milliohm")),
         False, "FREEZE"),
        ("non_material:equal_range_other_unit", param(),
         param(lo=(0.0, "milliohm"), hi=(10_000.0, "milliohm")), True, "FREEZE"),
        ("material:observed_value", evidence(1.0), evidence(1.0000001), False,
         "FREEZE"),
        ("contractual_order:parameter_set", CalibrationParameterSet((r, a)),
         CalibrationParameterSet((a, r)), False, "FREEZE"),
        ("non_material:operator_description", operator(description="thermocouple A"),
         operator(description="rewritten note"), True, "EXPERIMENTAL"),
        ("material:operator_mesh", operator(5), operator(9), False, "EXPERIMENTAL"),
    ]
    out = {}
    for name, left, right, expected_equal, classification in pairs:
        equal = left.digest == right.digest
        out[name] = {
            "classification": classification,
            "left": left.digest,
            "right": right.digest,
            "equal": equal,
            "expected_equal": expected_equal,
            "holds": equal == expected_equal,
            "rebuilt_identically": left.digest == (
                # same construction twice in one process
                pairs_rebuild(name, param, operator, evidence, r, a)
            ),
        }
    return {
        "pairs": out,
        "reference": {
            "parameter": r.digest,
            "parameter_set": CalibrationParameterSet((r,)).digest,
            "evidence": evidence(1.0).digest,
        },
    }


def pairs_rebuild(name, param, operator, evidence, r, a):
    """Rebuild the LEFT member of a pair from scratch, for in-process repeatability."""
    from engcore.inference import CalibrationParameterSet

    rebuild = {
        "material:model": lambda: param(),
        "material:unit": lambda: param(),
        "non_material:equal_range_other_unit": lambda: param(),
        "material:observed_value": lambda: evidence(1.0),
        "contractual_order:parameter_set": lambda: CalibrationParameterSet((r, a)),
        "non_material:operator_description":
            lambda: operator(description="thermocouple A"),
        "material:operator_mesh": lambda: operator(5),
    }
    return rebuild[name]().digest


# =====================================================================
# ORDERING -- results and failures come back in declaration order
# =====================================================================

def ordering_section() -> dict:
    from engcore.execution import (
        FailurePolicy, SweepCase, SweepDefinition, run_sweep,
    )

    def operation(shared, case):
        x = case.inputs["x"]
        if x % 3 == 0:
            raise ValueError(f"x={x} is refused by the probe")
        return x * x

    declared = (3, 1, 4, 1, 5, 9, 2, 6, 7, 12)
    cases = tuple(SweepCase(f"c{x}", {"x": x}) for x in declared)

    def summarise(summary):
        return {
            "outcomes": [
                [o.case.case_id, o.status.value, o.value, o.error_type]
                for o in summary.outcomes
            ],
            "failure_order": [o.case.case_id for o in summary.failures()],
            "values": list(summary.values()),
            "counts": [summary.succeeded, summary.failed, summary.not_run],
            "identity": summary.identity,
        }

    forward = SweepDefinition("freeze-probe", operation, cases)
    backward = SweepDefinition("freeze-probe", operation, tuple(reversed(cases)))
    fail_fast = SweepDefinition(
        "freeze-probe", operation, cases, on_failure=FailurePolicy.FAIL_FAST
    )
    return {
        "sequential": summarise(run_sweep(forward)),
        "fail_fast_sequential": summarise(run_sweep(fail_fast)),
        # `workers` is an EXPERIMENTAL parameter. Its ordering is recorded, not
        # frozen: the promise that outcomes return in declaration order is made
        # by the frozen docstring for any worker count, so a difference here
        # would still be worth seeing.
        "threads_4_experimental": summarise(run_sweep(forward, workers=4)),
        "case_identities": [c.identity for c in cases],
        "declaration_identity_forward": forward.identity,
        "declaration_identity_reversed": backward.identity,
        "duplicate_case_ids": list(forward.duplicate_case_ids),
    }


# =====================================================================
# EXCEPTIONS
# =====================================================================

def exception_section() -> dict:
    from engcore import api_snapshot

    roots: dict[str, int] = {}
    for entry in api_snapshot.frozen_only()["symbols"]:
        if entry["kind"] != "exception":
            continue
        klass = getattr(importlib.import_module(entry["module"]), entry["name"])
        chain = [
            f"{k.__module__}.{k.__qualname__}"
            for k in klass.__mro__ if k.__module__.startswith("engcore.")
        ]
        roots[chain[-1]] = roots.get(chain[-1], 0) + 1
    return {"roots": dict(sorted(roots.items())), "count": sum(roots.values())}


def build() -> dict:
    return {
        "schema": SCHEMA,
        "api": api_section(),
        "serialization": serialization_section(),
        "identity": identity_section(),
        "ordering": ordering_section(),
        "exceptions": exception_section(),
    }


if __name__ == "__main__":
    sys.stdout.buffer.write(canonical(build()))
