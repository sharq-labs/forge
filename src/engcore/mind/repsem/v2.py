"""Strict, versioned units/execution boundary over the historical repsem engine.

v1 remains historical replay. New assessments use this entrypoint and existing
Assessment/evidence records; no new evidence authority or custody is implied.
Only ratio-scale units and numeric scalar/array constants are supported. The
simulator is trusted Python code, not a sandbox; additional non-code resources
must be declared in artifact_files. Dynamic external I/O is outside this contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import dis
import inspect
import json
import marshal
from pathlib import Path
import sys
from types import CodeType, MappingProxyType, ModuleType
from typing import Mapping

import numpy as np
import scipy

from ...scientific.units.quantity import Quantity, is_ratio_scale, registry_fingerprint
from .assess import Assessment, ReplayMismatch, assess as assess_v1, canonical_bytes
from .families import BoundTrajectory, DeclaredFamily, bind
from .roles import PROBLEM_SCHEMA as V1_PROBLEM_SCHEMA, RoleTable

PROBLEM_SCHEMA = "forge.mind.repsem.problem/2"
FAMILY_SCHEMA = "forge.mind.repsem.family/2"


def _hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _code_bytes(code):
    constants = tuple(_code_bytes(c) if isinstance(c, CodeType) else c for c in code.co_consts)
    return marshal.dumps(code.replace(co_filename="", co_consts=constants))


def _global_names(code):
    if any(i.opname in ("IMPORT_NAME", "IMPORT_FROM") for i in dis.get_instructions(code)):
        raise ValueError("dynamic imports are outside the strict model contract")
    names = set(code.co_names)
    if names & {"eval", "exec", "compile", "__import__", "globals", "locals", "getattr", "setattr", "open"}:
        raise ValueError("dynamic execution or external I/O is outside the strict model contract")
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_global_names(constant))
    return names


def _implementation(value, seen=None):
    """Inspect actual code, reachable function globals, closures and modules."""
    seen = set() if seen is None else seen
    if inspect.isfunction(value):
        name = f"{value.__module__}:{value.__qualname__}"
        if id(value) in seen:
            return {"recursive_function": name}
        seen = seen | {id(value)}
        source = inspect.getsourcefile(value)
        if source is None or not Path(source).is_file():
            raise ValueError("model functions require inspectable source artifacts")
        return {"function": name, "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                "code_sha256": hashlib.sha256(_code_bytes(value.__code__)).hexdigest(),
                "defaults": _implementation(value.__defaults__, seen),
                "kwdefaults": _implementation(value.__kwdefaults__, seen),
                "closure": [_implementation(c.cell_contents, seen) for c in value.__closure__ or ()],
                "globals": {k: _implementation(value.__globals__[k], seen)
                            for k in sorted(_global_names(value.__code__)) if k in value.__globals__},
                "builtins": {k: _implementation(value.__builtins__[k], seen)
                             for k in sorted(_global_names(value.__code__))
                             if k not in value.__globals__ and k in value.__builtins__}}
    if isinstance(value, ModuleType):
        raise ValueError("module dependencies require an inspectable function dependency instead")
    if inspect.isbuiltin(value):
        return {"builtin": f"{value.__module__}:{value.__qualname__}", "python": sys.version}
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, np.ndarray):
        return {"array": value.tolist(), "dtype": str(value.dtype)}
    if isinstance(value, (tuple, list)):
        return [_implementation(x, seen) for x in value]
    if isinstance(value, Mapping) and all(type(k) is str for k in value):
        return {k: _implementation(v, seen) for k, v in sorted(value.items())}
    raise ValueError(f"unsupported mutable/dynamic model dependency: {type(value).__name__}")


def _unit_map(mapping):
    if not isinstance(mapping, Mapping) or any(type(k) is not str or not k for k in mapping):
        raise ValueError("named unit mapping required")
    out = {}
    for name, unit in mapping.items():
        if not unit or not is_ratio_scale(unit):
            raise ValueError("strict repsem supports explicit ratio-scale units only")
        out[name] = Quantity(1, unit).units
    return MappingProxyType(out)


def _factor(source, target):
    if not source or not target or not is_ratio_scale(source) or not is_ratio_scale(target):
        raise ValueError("strict repsem supports explicit ratio-scale units only")
    return Quantity(1, source).magnitude_in(target)


@dataclass(frozen=True)
class FamilyContract:
    family: DeclaredFamily
    version: str
    clock_unit: str
    measurement_unit: str
    slot_units: Mapping[str, str]
    parameter_units: Mapping[str, str]
    condition_units: Mapping[str, str]
    constant_units: Mapping[str, str]
    artifact_files: tuple[str, ...] = ()
    _sealed: str = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.family, DeclaredFamily) or not self.version.strip():
            raise ValueError("declared family and non-empty implementation version required")
        if not inspect.isfunction(self.family.simulate):
            raise ValueError("inspectable Python simulator function required")
        for name in ("slot_units", "parameter_units", "condition_units", "constant_units"):
            object.__setattr__(self, name, _unit_map(getattr(self, name)))
        if set(self.slot_units) != {s.name for s in self.family.slots} or set(self.parameter_units) != set(self.family.parameters):
            raise ValueError("every slot and parameter needs exactly one declared unit")
        if not set(self.family.required_conditions) <= set(self.condition_units):
            raise ValueError("required conditions need declared units")
        _factor(self.clock_unit, "s")
        _factor(self.measurement_unit, self.measurement_unit)
        paths = tuple(str(Path(p).resolve(strict=True)) for p in self.artifact_files)
        if len({Path(p).name for p in paths}) != len(paths):
            raise ValueError("artifact basenames must be unique")
        object.__setattr__(self, "artifact_files", paths)
        object.__setattr__(self, "_sealed", _hash(self._manifest()))

    def _manifest(self):
        return {"schema": FAMILY_SCHEMA, "family": self.family.to_dict(), "version": self.version,
                "clock_unit": self.clock_unit, "measurement_unit": self.measurement_unit,
                **{k: dict(getattr(self, k)) for k in ("slot_units", "parameter_units", "condition_units", "constant_units")},
                "implementation": _implementation(self.family.simulate),
                "artifacts": {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.artifact_files},
                "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
                            "units": registry_fingerprint()},
                "engine": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in Path(__file__).parent.glob("*.py")}}

    def to_dict(self):
        manifest = self._manifest()
        if _hash(manifest) != self._sealed:
            raise ValueError("model implementation or dependency changed after contract sealing")
        return manifest


def adapt(contract: FamilyContract, roles: RoleTable, clock: str, *, constant_units: Mapping[str, str],
          condition_units: Mapping[str, str]) -> DeclaredFamily:
    """Simulator works in family units; the assessment engine keeps problem units."""
    manifest = contract.to_dict()
    family = contract.family
    binding = bind(family, roles, clock)
    clock_scale = _factor(roles.declaration(clock).unit, contract.clock_unit)
    output_scale = _factor(contract.measurement_unit, roles.declaration(binding.measurement).unit)
    slot_scale = {k: _factor(roles.declaration(binding.slots[k]).unit, u) for k, u in contract.slot_units.items()}
    param_scale = {k: _factor(roles.declaration(k).unit, u) for k, u in contract.parameter_units.items()}
    if set(constant_units) != set(contract.constant_units) or set(condition_units) != set(contract.condition_units):
        raise ValueError("problem constant/condition units must match the family contract")
    constant_scale = {k: _factor(constant_units[k], u) for k, u in contract.constant_units.items()}
    condition_scale = {k: _factor(condition_units[k], u) for k, u in contract.condition_units.items()}
    state_names = {s.name for s in family.slots if s.state_of is not None}

    def convert(values, scales):
        if set(values) != set(scales):
            raise ValueError("numeric fields differ from the explicit unit contract")
        out = {k: np.asarray(v, dtype=float) * scales[k] for k, v in values.items()}
        if any(not np.all(np.isfinite(v)) for v in out.values()):
            raise ValueError("nonfinite model inputs")
        return out

    def simulate(params, trajectory, constants):
        contract.to_dict()
        slots = {k: np.asarray(v) * slot_scale[k] for k, v in trajectory.slots.items()}
        initial = {k: v * slot_scale[k] for k, v in trajectory.initial_state.items()}
        columns = {clock: trajectory.clock * clock_scale,
                   binding.measurement: trajectory.measurement / output_scale}
        columns.update({binding.slots[k]: v for k, v in slots.items()})
        converted = replace(trajectory, clock=trajectory.clock * clock_scale, slots=slots, initial_state=initial,
                            conditions=convert(trajectory.conditions, condition_scale),
                            measurement=trajectory.measurement / output_scale, columns=columns)
        prediction, states = family.simulate(convert(params, param_scale), converted, convert(constants, constant_scale))
        contract.to_dict()
        if set(states) != state_names:
            raise ValueError("simulator states differ from declared state units")
        prediction = np.asarray(prediction, float) * output_scale
        states = {k: np.asarray(v, float) / slot_scale[k] for k, v in states.items()}
        if any(v.shape != trajectory.clock.shape or not np.all(np.isfinite(v))
               for v in (prediction, *states.values())):
            raise ValueError("simulator outputs must be finite and aligned with the clock")
        return prediction, states

    class AdaptedFamily(DeclaredFamily):
        def to_dict(self):
            contract.to_dict()
            return {**super().to_dict(), "strict_contract": manifest}

    return AdaptedFamily(family.family_id, family.description, family.slots, family.parameters, simulate, family.required_conditions)


def assess(spec, families: Mapping[str, FamilyContract]) -> Assessment:
    if spec.get("schema") != PROBLEM_SCHEMA:
        raise ValueError("strict assessment requires a v2 problem")
    # Roundtrip snapshots nested caller data before fitting and preserves sigma,
    # bars, parameter bounds and applicability in the problem's own units.
    current = json.loads(canonical_bytes(spec))
    manifests = {k: v.to_dict() for k, v in families.items()}
    if any(k != v.family.family_id for k, v in families.items()):
        raise ValueError("family mapping keys must match declared identities")
    engine_spec = {**current, "schema": V1_PROBLEM_SCHEMA}
    roles = RoleTable.from_spec(engine_spec)
    adapted = {k: adapt(v, roles, current["clock"], constant_units=current.get("constant_units", {}),
                        condition_units=current.get("condition_units", {})) for k, v in families.items()}
    engine_spec["strict_execution"] = {"schema": PROBLEM_SCHEMA, "contracts": manifests, "problem_digest": _hash(current)}
    result = assess_v1(engine_spec, adapted, roles=roles)
    if manifests != {k: v.to_dict() for k, v in families.items()}:
        raise ValueError("model implementation changed during assessment")
    # Reuse the existing record with an explicitly versioned binding.
    return replace(result, binding={**result.binding, "strict_schema": PROBLEM_SCHEMA,
                                    "strict_execution_digest": _hash(engine_spec["strict_execution"])})


def replay(record, spec, families):
    expected = record.to_dict() if isinstance(record, Assessment) else record
    actual = assess(spec, families).to_dict()
    if canonical_bytes(expected) != canonical_bytes(actual):
        raise ReplayMismatch("strict model/problem/implementation replay mismatch")
    return {"status": "EXACT", "digest": _hash(actual), "schema": PROBLEM_SCHEMA}
