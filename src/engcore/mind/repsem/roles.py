"""Scientific variable roles: what part each candidate-visible variable plays, declared by the problem, never inferred.

The Minimal Mind knows two kinds of variable: a settable input and a passive covariate.  battery_rediscovery_v1 showed
what that costs (gap map, SEMANTIC_ROLE_ERROR): a current level fixed by the protocol and a state of charge obtained by
integrating that current were both posed as passive covariates, and the Mind correctly refused to read a causal effect
into a passive association it could not intervene on.  The refusal was right for the variables as posed; the posing
was wrong.

A role is a fact about the EXPERIMENT, not about the variable's name or values: the same column "current" is a
controlled input on a cycler and a passively logged nuisance in field data.  So :class:`RoleTable` accepts roles only
from the problem specification or the protocol metadata (:class:`RoleSource`), requires exactly one primary role per
visible variable, and has no code path that guesses a role from a name or from the data.

Each role says how the variable may enter a judgment:

==========================  =========================================================================================
CONTROLLED_INPUT            set by the experimenter as a function of time; drives a declared model; interventional
FIXED_PROTOCOL_CONDITION    held at a level the protocol chose (per segment or per run); interventional across levels
STATE_VARIABLE              evolves under declared dynamics driven by named inputs; reconstructed through those
                            dynamics, never used as a free observed predictor
MEASUREMENT                 the observed response a claim is about
DERIVED_QUANTITY            computed from other variables (``derived_from``); never independent evidence
LATENT_PARAMETER            a model parameter; never observed, has no data column, only estimated
NUISANCE_VARIABLE           observed passively, not set; the only role whose association is confounded by default
==========================  =========================================================================================
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

ROLE_TABLE_SCHEMA = "forge.mind.repsem.role_table/1"
PROBLEM_SCHEMA = "forge.mind.repsem.problem/1"


class RoleRefused(ValueError):
    """A role table that is incomplete, ambiguous, inferred, or contradicted by the data's columns."""


class VariableRole(str, Enum):
    CONTROLLED_INPUT = "CONTROLLED_INPUT"
    FIXED_PROTOCOL_CONDITION = "FIXED_PROTOCOL_CONDITION"
    STATE_VARIABLE = "STATE_VARIABLE"
    MEASUREMENT = "MEASUREMENT"
    DERIVED_QUANTITY = "DERIVED_QUANTITY"
    LATENT_PARAMETER = "LATENT_PARAMETER"
    NUISANCE_VARIABLE = "NUISANCE_VARIABLE"


class RoleSource(str, Enum):
    PROBLEM_SPECIFICATION = "problem_specification"
    PROTOCOL_METADATA = "protocol_metadata"
    #: The battery_rediscovery_v1 adapter's two-class rule (clock settable, measurement observed, everything else a
    #: passive covariate).  It exists so the ablation can reproduce the old semantics; it is not a scientific role
    #: declaration, and :func:`legacy_role_table` is the only producer.
    LEGACY_ADAPTER_DEFAULT = "legacy_adapter_default"


INTERVENTIONAL = (VariableRole.CONTROLLED_INPUT, VariableRole.FIXED_PROTOCOL_CONDITION)
FREE_PREDICTOR = (VariableRole.CONTROLLED_INPUT, VariableRole.FIXED_PROTOCOL_CONDITION, VariableRole.NUISANCE_VARIABLE)

#: The study-level vocabulary :class:`engcore.scientific.ir.variables.VariableRole` names four of these roles; the other
#: three (a protocol-fixed level, a latent parameter, a passive nuisance) have no counterpart there.  Recorded so the
#: two vocabularies are never silently conflated.
IR_ROLE = {VariableRole.CONTROLLED_INPUT: "control", VariableRole.STATE_VARIABLE: "state",
           VariableRole.MEASUREMENT: "observable"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RoleDeclaration:
    name: str
    role: VariableRole
    unit: str
    source: RoleSource
    basis: str
    driven_by: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise RoleRefused("a role declaration names its variable")
        try:
            object.__setattr__(self, "role", VariableRole(self.role))
        except ValueError:
            raise RoleRefused(f"{self.name!r}: unknown role {self.role!r}") from None
        try:
            object.__setattr__(self, "source", RoleSource(self.source))
        except ValueError:
            raise RoleRefused(f"{self.name!r}: role source {self.source!r} is not the problem specification or the "
                              "protocol metadata; a role is never inferred") from None
        if not str(self.basis).strip():
            raise RoleRefused(f"{self.name!r}: a role declaration cites its basis in the specification or protocol")
        object.__setattr__(self, "driven_by", tuple(self.driven_by))
        object.__setattr__(self, "derived_from", tuple(self.derived_from))
        if (self.role is VariableRole.STATE_VARIABLE) != bool(self.driven_by):
            raise RoleRefused(f"{self.name!r}: a STATE_VARIABLE names the inputs that drive it, and only a state does")
        if (self.role is VariableRole.DERIVED_QUANTITY) != bool(self.derived_from):
            raise RoleRefused(f"{self.name!r}: a DERIVED_QUANTITY names what it is derived from, and only it does")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "role": self.role.value, "unit": self.unit, "source": self.source.value,
                "basis": self.basis, "driven_by": list(self.driven_by), "derived_from": list(self.derived_from)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RoleDeclaration":
        extra = set(d) - {"name", "role", "unit", "source", "basis", "driven_by", "derived_from"}
        if extra:
            raise RoleRefused(f"unknown role declaration keys {sorted(extra)}")
        return cls(d["name"], d["role"], d.get("unit", "1"), d.get("source", ""), d.get("basis", ""),
                   tuple(d.get("driven_by", ())), tuple(d.get("derived_from", ())))


@dataclass(frozen=True)
class RoleTable:
    declarations: tuple[RoleDeclaration, ...]

    def __post_init__(self) -> None:
        decls = tuple(sorted(self.declarations, key=lambda d: d.name))
        object.__setattr__(self, "declarations", decls)
        names = [d.name for d in decls]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise RoleRefused(f"variables {dup} have more than one primary role")
        known = set(names)
        for d in decls:
            for ref, label in [(r, "driven_by") for r in d.driven_by] + [(r, "derived_from") for r in d.derived_from]:
                if ref not in known:
                    raise RoleRefused(f"{d.name!r}: {label} names undeclared variable {ref!r}")
            for ref in d.driven_by:
                if self.role(ref) not in INTERVENTIONAL:
                    raise RoleRefused(f"{d.name!r}: a state is driven by controlled inputs or protocol conditions, "
                                      f"and {ref!r} is {self.role(ref).value}")
        if sum(d.role is VariableRole.MEASUREMENT for d in decls) < 1:
            raise RoleRefused("a problem declares at least one MEASUREMENT")

    # ---- lookup ---------------------------------------------------------------------------------------------------
    def declaration(self, name: str) -> RoleDeclaration:
        for d in self.declarations:
            if d.name == name:
                return d
        raise RoleRefused(f"variable {name!r} has no declared role (roles are never inferred from a name)")

    def role(self, name: str) -> VariableRole:
        return self.declaration(name).role

    def names(self, *roles: VariableRole) -> tuple[str, ...]:
        return tuple(d.name for d in self.declarations if d.role in roles)

    def interventional(self) -> tuple[str, ...]:
        return self.names(*INTERVENTIONAL)

    def passive(self) -> tuple[str, ...]:
        return self.names(VariableRole.NUISANCE_VARIABLE)

    def free_predictors(self) -> tuple[str, ...]:
        """Variables a regression may use as observed predictors: never a state, a derived quantity or a parameter."""
        return self.names(*FREE_PREDICTOR)

    def observed(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.declarations if d.role is not VariableRole.LATENT_PARAMETER)

    @property
    def is_legacy(self) -> bool:
        return any(d.source is RoleSource.LEGACY_ADAPTER_DEFAULT for d in self.declarations)

    def check_columns(self, columns: Iterable[str], where: str) -> None:
        """Every data column has a declared role, and no LATENT_PARAMETER appears as data."""
        cols = set(columns)
        latent = sorted(cols & set(self.names(VariableRole.LATENT_PARAMETER)))
        if latent:
            raise RoleRefused(f"{where}: latent parameters {latent} appear as data columns; a latent parameter is never "
                              "observed")
        undeclared = sorted(cols - {d.name for d in self.declarations})
        if undeclared:
            raise RoleRefused(f"{where}: columns {undeclared} have no declared role")

    # ---- construction and serialization ---------------------------------------------------------------------------
    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "RoleTable":
        """The roles a problem declares.  Every candidate-visible column must be declared; nothing is filled in."""
        if spec.get("schema") != PROBLEM_SCHEMA:
            raise RoleRefused(f"not a repsem problem: {spec.get('schema')!r}")
        variables = spec.get("variables")
        if not variables:
            raise RoleRefused("the problem declares no variable roles")
        table = cls(tuple(RoleDeclaration.from_dict(v) for v in variables))
        if table.is_legacy:
            raise RoleRefused("a problem specification cannot declare the legacy adapter default as a role source")
        for set_name, trajs in _trajectories(spec):
            for traj in trajs:
                table.check_columns(traj["columns"], f"{set_name}/{traj['id']}")
        return table

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROLE_TABLE_SCHEMA, "declarations": [d.to_dict() for d in self.declarations]}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RoleTable":
        if d.get("schema") != ROLE_TABLE_SCHEMA:
            raise RoleRefused(f"not a role table: {d.get('schema')!r}")
        return cls(tuple(RoleDeclaration.from_dict(x) for x in d["declarations"]))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _trajectories(spec: Mapping[str, Any]) -> list[tuple[str, list[Mapping[str, Any]]]]:
    sets = spec.get("sets", {})
    out = [("calibration", list(sets.get("calibration", [])))]
    for name in ("within_unit_heldout", "cross_unit_heldout"):
        for sub, trajs in sorted((sets.get(name) or {}).items()):
            out.append((f"{name}/{sub}", list(trajs)))
    return out


def legacy_role_table(spec: Mapping[str, Any]) -> RoleTable:
    """The battery_rediscovery_v1 adapter's semantics as a role table: the clock is the one controlled input, the
    observable is the measurement, and every other column is a passive NUISANCE covariate.  No latent parameter and no
    state is declared, because the old adapter had neither concept.  For ablation only."""
    columns = sorted({c for _, trajs in _trajectories(spec) for t in trajs for c in t["columns"]})
    decls = []
    for c in columns:
        role = (VariableRole.CONTROLLED_INPUT if c == spec["clock"] else
                VariableRole.MEASUREMENT if c == spec["observable"] else VariableRole.NUISANCE_VARIABLE)
        decls.append(RoleDeclaration(c, role, "1", RoleSource.LEGACY_ADAPTER_DEFAULT, "v1 adapter two-class rule"))
    return RoleTable(tuple(decls))


__all__ = ["FREE_PREDICTOR", "INTERVENTIONAL", "IR_ROLE", "PROBLEM_SCHEMA", "ROLE_TABLE_SCHEMA", "RoleDeclaration", "RoleRefused",
           "RoleSource", "RoleTable", "VariableRole", "legacy_role_table"]
