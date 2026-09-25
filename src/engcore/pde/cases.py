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
