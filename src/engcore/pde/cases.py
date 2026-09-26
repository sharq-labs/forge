"""Provider-neutral structural load cases consumed by process-based structural providers (BIG 11).

A :class:`PlaneStressProblem` is a linear-elastic plane-stress case on an exact
BIG 7 triangle mesh: one isotropic material per cell region whose properties
are the BIG 5 RESOLVED records (their digests travel as provenance), a clamped
facet group and a uniform traction on another facet group.  Providers
(CalculiX, Code_Aster, ...) translate it into their own decks; none of them
owns it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..materials.properties import ResolvedProperty
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity


@dataclass(frozen=True)
class RegionMaterial:
    """One region's isotropic elastic constants, carried AS the BIG 5 resolved records (value and digest bound)."""

    region: str
    youngs_modulus_record: ResolvedProperty
    poisson_ratio_record: ResolvedProperty

    @property
    def youngs_modulus(self) -> Quantity:
        return self.youngs_modulus_record.value.value

    @property
    def poisson_ratio(self) -> Quantity:
        return self.poisson_ratio_record.value.value

    @property
    def provenance(self) -> tuple[str, ...]:
        return (self.youngs_modulus_record.digest, self.poisson_ratio_record.digest)

    def __post_init__(self) -> None:
        for record, pid in ((self.youngs_modulus_record, "youngs_modulus"), (self.poisson_ratio_record, "poisson_ratio")):
            if not isinstance(record, ResolvedProperty) or record.property_id != pid or record.status != "known":
                raise InvalidScientificProblem(f"a region material takes a KNOWN BIG 5 resolved {pid!r} record, not a number")
        nu = self.poisson_ratio.to("dimensionless").magnitude
        if not (self.youngs_modulus.to("Pa").magnitude > 0 and 0 <= nu < 0.5):
            raise InvalidScientificProblem("isotropic elastic constants outside 0 < E, 0 <= nu < 0.5")


@dataclass(frozen=True)
class PlaneStressProblem:
    mesh: object
    materials: tuple[RegionMaterial, ...]
    thickness: Quantity
    clamped_group: str
    traction_group: str
    traction: tuple[Quantity, Quantity]

    def __post_init__(self) -> None:
        if not self.thickness.to("m").magnitude > 0:
            raise InvalidScientificProblem("plane-stress thickness must be positive")
        for group in (self.clamped_group, self.traction_group):
            region = self.mesh.region(group)
            if len(self.mesh.facet_indices(region)) == 0:
                raise InvalidScientificProblem(f"facet group {group!r} is empty; a load or support is never defaulted")
        regions = [m.region for m in self.materials]
        if len(set(regions)) != len(regions):
            raise InvalidScientificProblem("one material per region")

    def to_dict(self) -> dict:
        return {"mesh": self.mesh.digest,
                "materials": [[m.region, m.youngs_modulus.to_dict(), m.poisson_ratio.to_dict(), list(m.provenance)] for m in self.materials],
                "thickness": self.thickness.to_dict(), "clamped": self.clamped_group, "traction_group": self.traction_group,
                "traction": [t.to_dict() for t in self.traction]}


@dataclass(frozen=True)
class RegionExpansion:
    """One region's isotropic thermal expansion coefficient, carried AS a BIG 5 resolved record (value and digest bound)."""

    region: str
    expansion_record: ResolvedProperty

    @property
    def coefficient(self) -> Quantity:
        return self.expansion_record.value.value

    def __post_init__(self) -> None:
        r = self.expansion_record
        if not isinstance(r, ResolvedProperty) or r.property_id != "thermal_expansion" or r.status != "known":
            raise InvalidScientificProblem("a region expansion takes a KNOWN BIG 5 resolved 'thermal_expansion' record, not a number")
        if not self.coefficient.to("1/K").magnitude == self.coefficient.to("1/K").magnitude:
            raise InvalidScientificProblem("a thermal expansion coefficient is a number")


@dataclass(frozen=True)
class Restraint:
    """Zero displacement of the listed components (0 = x, 1 = y) on a facet group.  A restraint is declared; none is defaulted."""

    group: str
    components: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.components or any(c not in (0, 1) for c in self.components) or len(set(self.components)) != len(self.components):
            raise InvalidScientificProblem("a restraint fixes component 0 and/or 1, each once")


@dataclass(frozen=True)
class ThermoelasticPlaneStressProblem:
    """A linear thermo-elastic plane-stress case: a temperature field on the nodes drives isotropic thermal strain ``alpha (T - T_ref)``.

    Provider-neutral like :class:`PlaneStressProblem`.  ``temperature`` is one value per mesh node (units ``temperature_unit``), and it
    is bound by content (``temperature_digest``, normally the digest of the thermal solution field it came from), so a structural
    execution can never be confused with one driven by another thermal state.  There is NO traction option: loads here are thermal.
    """

    mesh: object
    materials: tuple[RegionMaterial, ...]
    expansions: tuple[RegionExpansion, ...]
    thickness: Quantity
    restraints: tuple[Restraint, ...]
    temperature: tuple[float, ...]
    temperature_unit: str
    temperature_digest: str
    reference_temperature: Quantity

    def __post_init__(self) -> None:
        if not self.thickness.to("m").magnitude > 0:
            raise InvalidScientificProblem("plane-stress thickness must be positive")
        if len(self.temperature) != self.mesh.node_count:
            raise InvalidScientificProblem("the temperature field needs exactly one value per mesh node")
        import math
        if not all(math.isfinite(float(t)) for t in self.temperature):
            raise InvalidScientificProblem("a temperature field with non-finite values is not a solved field")
        if not self.restraints:
            raise InvalidScientificProblem("a structure with no restraint is not supported; supports are never defaulted")
        for r in self.restraints:
            if len(self.mesh.facet_indices(self.mesh.region(r.group))) == 0:
                raise InvalidScientificProblem(f"restraint group {r.group!r} is empty")
        regions = [m.region for m in self.materials]
        if len(set(regions)) != len(regions) or {e.region for e in self.expansions} != set(regions) or len(self.expansions) != len(regions):
            raise InvalidScientificProblem("one material and one expansion record per region, for the same regions")
        if len(str(self.temperature_digest)) != 64:
            raise InvalidScientificProblem("the temperature field is bound by its 64-hex content digest")

    def temperature_K(self):
        import numpy as np
        return np.array([Quantity(float(v), self.temperature_unit).to("K").magnitude for v in self.temperature])

    def to_dict(self) -> dict:
        return {"mesh": self.mesh.digest,
                "materials": [[m.region, m.youngs_modulus.to_dict(), m.poisson_ratio.to_dict(), list(m.provenance)] for m in self.materials],
                "expansions": [[e.region, e.coefficient.to_dict(), e.expansion_record.digest] for e in self.expansions],
                "thickness": self.thickness.to_dict(), "restraints": [[r.group, list(r.components)] for r in self.restraints],
                "temperature_digest": self.temperature_digest, "temperature_unit": self.temperature_unit,
                "reference_temperature": self.reference_temperature.to_dict()}
