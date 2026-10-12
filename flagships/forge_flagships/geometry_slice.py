"""Big Rock O: the first general geometry vertical slice (an architecture proof, not a flagship result).

    ParametricGeometry (two-layer wall) -> GeometryVariant
        -> Gmsh adapter -> SpatialMesh + ProviderEntityMap + MeshBinding + GeometryReceipt
        -> region/boundary mapping -> BIG 5 material binding (RegionMaterialMap -> resolved conductivity field)
        -> PDEProblem (Forge STEADY_DIFFUSION template; every BC from a declared boundary binding)
        -> fidelity 0: closed-form series-resistance model      (always runs; a model computation)
        -> fidelity 2: FEniCSx on the same PDEProblem           (only if the provider is AVAILABLE)
        -> ScientificResult -> DesignCandidate/DesignEvaluation -> TwinRevision -> discovery campaign

Why this geometry: a two-layer wall with adiabatic top/bottom and Dirichlet
hot/cold faces has an EXACT one-dimensional solution (series thermal
resistance), so every number the pipeline produces can be checked against a
closed form.  The numerical rung's agreement with that closed form is
discretisation VERIFICATION; nothing here is validation, because no
measurement of any physical wall is involved.

Material values are ILLUSTRATIVE architecture-proof data with their own
source record ("not reference data").  They exist so the material authority
path (identity -> state -> sourced claim -> resolved property -> cell field)
is exercised exactly as it would be with admitted data.

Every run ends with verdict ``insufficient_evidence``: there is no validation
evidence, by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping

import numpy as np

from engcore.design import (
    DesignCandidate, DesignEvaluation, DesignSpace, FidelityLadder, FidelityObservation, FidelityOutcome, FidelityRung, PromotionPolicy,
    ResultBinding, SelectionEligibility, run_discovery,
)
from engcore.design.evaluation import RESULT_BINDING_METADATA_KEY
from engcore.materials import ApplicabilityRange, MaterialIdentity, MaterialPropertySet, MaterialState, PropertyApplicability, PropertyDatum
from engcore.numerical.core import ProviderUnavailable
from engcore.pde import (
    STEADY_DIFFUSION, BCKind, BoundaryCondition, CoefficientBinding, DiscretizationSpec, FacetRole, PDEProblem, PhysicalModel,
    SourcedQuantity,
)
from engcore.scenarios import NamedQuantity
from engcore.scenarios.timeline import canonical_digest
from engcore.design.grammar import ConstraintEvaluation, evaluate_constraints
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.ir.variables import ScientificVariable
from engcore.scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from engcore.scientific.knowledge.ingestion import KnowledgeIngestionReceipt, verify_ingestion_receipt
from engcore.scientific.knowledge.snapshot import KnowledgeSnapshot
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.models.definition import RangeCondition, ValidityDomain
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.requirements import result_establishment_problems
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome, ValidationReport
from engcore.scientific.solvers.protocol import SolverSettings
from engcore.scientific.twins import ScientificTwin, TwinDatum, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import (
    Body, Boundary, BoundaryBinding, FeatureRef, FrameDefinition, GeometryBuilderRegistry, GeometryModel, GeometryParameter,
    GmshMeshRequest, Interface, Location, MaterialBinding, ParameterKind, ParametricGeometry, Rank, Region, RoleAssignment, Shape,
    SpatialFieldDefinition, Transform, mesh_geometry, region_material_map,
)
from engcore.spatial.gmsh_adapter import facet_measure, mesh_measure
from engcore.systems.twin_revision import EvidenceReference, EvidenceRole, TwinRevision, UncertaintyReference, UncertaintyStatus

CLASSIFICATION = "architecture_proof_not_validation"
VERDICT = "insufficient_evidence"
K_UNIT = "W/(m*K)"

# ---------------------------------------------------------------------------
# Geometry template
# ---------------------------------------------------------------------------

STRUCTURAL = MaterialIdentity("masonry", specification="ILLUSTRATIVE-SLICE-A", grade="dense")
INSULATION = MaterialIdentity("mineral_wool", specification="ILLUSTRATIVE-SLICE-B", grade="board")

TEMPLATE = ParametricGeometry("two_layer_wall", "1", (
    GeometryParameter("t_structural", ParameterKind.THICKNESS, Quantity(20, "mm"), Quantity(300, "mm")),
    GeometryParameter("t_insulation", ParameterKind.THICKNESS, Quantity(10, "mm"), Quantity(300, "mm")),
    GeometryParameter("height", ParameterKind.HEIGHT, Quantity(0.05, "m"), Quantity(2, "m")),
), "two_layer_wall_builder", "1")


def build_wall(v: Mapping[str, Quantity]) -> GeometryModel:
    ts, ti, h = v["t_structural"], v["t_insulation"], v["height"]
    structural = Body("structural", Shape.rectangle(ts, h), "wall", part_id="structural_layer")
    insulation = Body("insulation", Shape.rectangle(ti, h), "wall", Transform.from_quantities((ts, Quantity(0, "m"), Quantity(0, "m"))),
                      part_id="insulation_layer")
    edges = tuple(FeatureRef(b, f) for b in ("structural", "insulation") for f in ("ymin", "ymax"))
    return GeometryModel(
        "two_layer_wall", "1", 2, (FrameDefinition("wall"),), (structural, insulation),
        regions=(Region("structural", ("structural",)), Region("insulation", ("insulation",))),
        boundaries=(Boundary("hot_face", (FeatureRef("structural", "xmin"),)), Boundary("cold_face", (FeatureRef("insulation", "xmax"),)),
                    Boundary("edges", edges)),
        interfaces=(Interface("layer_joint", "structural", "insulation"),),
        roles=(RoleAssignment("boundary:hot_face", "thermal", "dirichlet_face"), RoleAssignment("boundary:hot_face", "structural", "loaded_face"),
               RoleAssignment("boundary:cold_face", "thermal", "dirichlet_face"), RoleAssignment("boundary:edges", "thermal", "adiabatic_face"),
               RoleAssignment("interface:layer_joint", "thermal", "perfect_contact")),
        materials=(MaterialBinding("structural", STRUCTURAL), MaterialBinding("insulation", INSULATION)),
        boundary_bindings=(BoundaryBinding("hot_face", "thermal", "dirichlet", "slice:hot_face_temperature"),
                           BoundaryBinding("cold_face", "thermal", "dirichlet", "slice:cold_face_temperature"),
                           BoundaryBinding("edges", "thermal", "neumann", "slice:declared_adiabatic_edges")),
    )


BUILDERS = GeometryBuilderRegistry()
BUILDERS.register("two_layer_wall_builder", "1", build_wall)

# ---------------------------------------------------------------------------
# Illustrative material data (sourced, but NOT reference data)
# ---------------------------------------------------------------------------


def _property_set(material: MaterialIdentity, k: float, set_id: str) -> MaterialPropertySet:
    rows = [(f"{set_id}-k", "thermal_conductivity", Quantity(k, K_UNIT))]
    payload = json.dumps([[r[0], r[1], r[2].to_dict()] for r in rows], sort_keys=True).encode()
    source = KnowledgeSource(f"{set_id}-source", "Forge geometry slice: illustrative architecture-proof values, NOT reference data",
                             hashlib.sha256(payload).hexdigest(), "1", "flagships/forge_flagships/geometry_slice.py", KnowledgeSourceClass.OTHER)
    app = PropertyApplicability(material.digest, "thermal_conductivity",
                                (ApplicabilityRange("temperature", Quantity(250, "K"), Quantity(450, "K")),), "")
    claim = KnowledgeClaim(rows[0][0], KnowledgeKind.MATERIAL_PROPERTY, material.subject_key, "thermal_conductivity", rows[0][2], "", None,
                           source.source_id, source.document_digest, app.digest)
    snapshot = KnowledgeSnapshot(f"{set_id}-snapshot", (source,), (claim,))
    receipt = KnowledgeIngestionReceipt.from_payload(source, payload, "forge.geometry_slice", "1", (claim.digest,))
    verify_ingestion_receipt(snapshot, receipt)
    return MaterialPropertySet(set_id, material, snapshot, (PropertyDatum(claim, app, "compiled", None),), ())


PROPERTY_SETS = {STRUCTURAL.digest: _property_set(STRUCTURAL, 1.0, "slice-structural"),
                 INSULATION.digest: _property_set(INSULATION, 0.04, "slice-insulation")}


# ---------------------------------------------------------------------------
# Declared conditions and criteria
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SliceConditions:
    """Boundary temperatures and the DECLARED design criteria a candidate is judged against.  Nothing is defaulted."""

    hot: Quantity
    cold: Quantity
    max_heat_flux: Quantity
    max_interface_temperature: Quantity

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k).to_dict() for k in ("hot", "cold", "max_heat_flux", "max_interface_temperature")}

    def boundary_values(self) -> dict[str, Quantity]:
        """Values by the condition_ref the geometry's boundary bindings name.  An unmapped ref is refused upstream."""
        return {"slice:hot_face_temperature": self.hot, "slice:cold_face_temperature": self.cold,
                "slice:declared_adiabatic_edges": Quantity(0, "W/m^2")}

    def constraints(self) -> tuple[ConstraintDefinition, ...]:
        return (ConstraintDefinition("max-heat-flux", "heat_flux", ConstraintOperator.LESS_EQUAL, self.max_heat_flux),
                ConstraintDefinition("max-interface-temperature", "interface_temperature", ConstraintOperator.LESS_EQUAL,
                                     self.max_interface_temperature))

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def states(self) -> dict[str, MaterialState]:
        """Material states at the mean wall temperature (declared evaluation condition, not a measured state)."""
        mean = Quantity((self.hot.magnitude_in("K") + self.cold.magnitude_in("K")) / 2, "K")
        return {"structural": MaterialState(STRUCTURAL, (NamedQuantity("temperature", mean),)),
                "insulation": MaterialState(INSULATION, (NamedQuantity("temperature", mean),))}


def _prescribed(q: Quantity, ref: str) -> SourcedQuantity:
    return SourcedQuantity(q, "prescribed", {"declared_by": "geometry_slice", "condition_ref": ref})


def series_solution(ts_m: float, ti_m: float, k_s: float, k_i: float, hot_K: float, cold_K: float) -> tuple[float, float]:
    """Exact 1D series conduction: heat flux (W/m^2) and interface temperature (K)."""
    r = ts_m / k_s + ti_m / k_i
    q = (hot_K - cold_K) / r
    return q, hot_K - q * ts_m / k_s


def resolved_conductivities(conditions: SliceConditions) -> dict[str, Any]:
    out = {}
    for region, state in conditions.states().items():
        r = PROPERTY_SETS[state.material.digest].resolve("thermal_conductivity", state)
        if r.status != "known":
            raise ProviderUnavailable(f"conductivity of {region} is UNKNOWN at the declared state: {r.reason}")
        out[region] = r
    return out


# ---------------------------------------------------------------------------
# Fidelity 0: closed form
# ---------------------------------------------------------------------------

SERIES_MODEL = ("forge.slice.series_conduction_1d", "1")
#: The closed form is exact under the declared assumptions (adiabatic edges, perfect contact, constant k per layer);
#: its quantitative domain is the material data's: the evaluation temperature must lie where the conductivity claims apply.
#: Every face temperature (not only the mean) must lie inside the claims' temperature range.
SERIES_DOMAIN = ValidityDomain(conditions=(
    RangeCondition("hot_face_temperature", minimum=Quantity(250, "K"), maximum=Quantity(450, "K")),
    RangeCondition("cold_face_temperature", minimum=Quantity(250, "K"), maximum=Quantity(450, "K")),
))
EXPECTED_DIMENSIONS = {"heat_flux": "W/m^2", "interface_temperature": "K", "total_thickness": "m"}
MATERIAL_DATA_CLASSIFICATION = "illustrative_not_reference_data"
#: Agreement required before a numerical run counts as VERIFICATION of the discretisation against the closed form
#: (P1 on a mesh conforming to the layer joint reproduces the piecewise-linear exact solution up to solver tolerance).
VERIFICATION_TOLERANCE_K = 1e-6


def domain_problem(conditions: SliceConditions) -> str:
    """'' when both face temperatures are inside the material claims' range; otherwise why the model does not apply."""
    a = SERIES_DOMAIN.assess({"hot_face_temperature": conditions.hot, "cold_face_temperature": conditions.cold})
    return "" if a.status.value == "in_domain" else f"closed form outside its declared domain ({a.status.value}): {list(a.violated)}"


def material_data_digest() -> str:
    return canonical_digest(sorted(ps.digest for ps in PROPERTY_SETS.values()))
VALUES = ("t_structural", "t_insulation", "height")


def analytic_metrics(values: Mapping[str, Quantity], conditions: SliceConditions) -> dict[str, Quantity]:
    k = resolved_conductivities(conditions)
    ts, ti = values["t_structural"].magnitude_in("m"), values["t_insulation"].magnitude_in("m")
    q, t_int = series_solution(ts, ti, k["structural"].value.value.magnitude_in(K_UNIT), k["insulation"].value.value.magnitude_in(K_UNIT),
                               conditions.hot.magnitude_in("K"), conditions.cold.magnitude_in("K"))
    return {"heat_flux": Quantity(q, "W/m^2"), "interface_temperature": Quantity(t_int, "K"), "total_thickness": Quantity(ts + ti, "m")}


def _criteria(metrics: Mapping[str, Quantity], conditions: SliceConditions) -> tuple[ConstraintEvaluation, str]:
    """Three-valued: a missing metric is UNKNOWN and the candidate is then undetermined, never feasible."""
    e = evaluate_constraints(conditions.constraints(), metrics)
    return e, f"declared criteria: violated {list(e.violated)}, unknown {list(e.unknown)}"


def _observation(key: str, rung: str, rank: int, provider: str, metrics: Mapping[str, Quantity], conditions: SliceConditions,
                 note: str = "") -> FidelityObservation:
    e, why = _criteria(metrics, conditions)
    outcome = {True: FidelityOutcome.SUPPORTS, False: FidelityOutcome.CONTRADICTS, None: FidelityOutcome.INCONCLUSIVE}[e.feasible]
    return FidelityObservation(key, rung, rank, outcome, provider, why + note, dict(metrics) if outcome is not FidelityOutcome.CONTRADICTS else {},
                               uncertainty="unknown", constraints=e)


# ---------------------------------------------------------------------------
# Mesh + PDE problem
# ---------------------------------------------------------------------------

HEAT = PhysicalModel("heat.fourier_conduction", "1", "steady Fourier conduction, isotropic k per layer, no source, perfect contact",
                     ("conductivity constant within each layer at the declared mean temperature",))
SOLVER = SolverSettings({"rtol": 1e-12, "residual_rtol": 1e-9}, {"ksp_type": "preonly", "pc_type": "lu", "max_iterations": 1})


@dataclass(frozen=True)
class MeshedSlice:
    model: GeometryModel
    variant: Any
    meshed: Any
    problem: PDEProblem
    geometric_checks: Mapping[str, float]


def build_problem(values: Mapping[str, Quantity], conditions: SliceConditions, mesh_size: Quantity) -> MeshedSlice:
    model, variant = TEMPLATE.instantiate(values, BUILDERS)
    meshed = mesh_geometry(model, GmshMeshRequest(size=mesh_size))
    mesh = meshed.mesh
    rmm = region_material_map(model, mesh, meshed.binding, meshed.receipt, conditions.states())
    k_field, _ = rmm.property_field(PROPERTY_SETS, "thermal_conductivity", K_UNIT, "k")
    values_by_ref = conditions.boundary_values()
    unmapped = sorted(b.condition_ref for b in model.boundary_bindings if b.domain == "thermal" and b.condition_ref not in values_by_ref)
    if unmapped:
        raise ProviderUnavailable(f"boundary condition records {unmapped} have no declared value; a boundary value is never defaulted")
    bcs = tuple(BoundaryCondition(BCKind(b.condition_kind), b.boundary, _prescribed(values_by_ref[b.condition_ref], b.condition_ref))
                for b in model.boundary_bindings if b.domain == "thermal")
    roles = {b.name: FacetRole.EXTERNAL_BOUNDARY for b in model.boundaries}
    roles.update({i.name: FacetRole.INTERNAL_INTERFACE for i in model.interfaces})
    problem = PDEProblem("two-layer-wall", mesh, HEAT, STEADY_DIFFUSION,
                         SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR),
                         (CoefficientBinding("conductivity", field=k_field),), bcs, roles, DiscretizationSpec(), SOLVER)
    h = values["height"].magnitude_in("m")
    area = (values["t_structural"].magnitude_in("m") + values["t_insulation"].magnitude_in("m")) * h
    checks = {"mesh_area_rel_error": abs(mesh_measure(mesh) - area) / area,
              "hot_face_length_rel_error": abs(facet_measure(mesh, mesh.facet_indices(mesh.region("hot_face"))) - h) / h,
              "joint_length_rel_error": abs(facet_measure(mesh, mesh.facet_indices(mesh.region("layer_joint"))) - h) / h}
    return MeshedSlice(model, variant, meshed, problem, checks)


def numerical_metrics(slice_: MeshedSlice, values: Mapping[str, Quantity]) -> tuple[dict[str, Quantity], dict[str, Any]]:
    """Run the Forge PDEProblem on FEniCSx.  Raises ProviderUnavailable when FEniCSx is not installed."""
    try:
        from forge_fenicsx import FenicsxProvider
    except ImportError as exc:
        raise ProviderUnavailable(f"forge_fenicsx adapter is not importable: {exc}") from exc
    provider = FenicsxProvider()
    if not provider.available():
        raise ProviderUnavailable(f"FEniCSx is unavailable: {provider._detail}")
    rec = provider.execute(slice_.problem)
    if not rec.succeeded:
        raise ProviderUnavailable(f"FEniCSx solve failed: {rec.reason}")
    mesh = slice_.problem.mesh
    t = np.asarray(rec.field.values, dtype=float)
    joint = mesh.node_indices(mesh.region("layer_joint"))
    hot = mesh.node_indices(mesh.region("hot_face"))
    ts = values["t_structural"].magnitude_in("m")
    k_s = float(np.asarray(slice_.problem.coefficients[0].field.values)[mesh.cell_indices(mesh.region("structural"))][0])
    t_int = float(np.mean(t[joint]))
    q = k_s * (float(np.mean(t[hot])) - t_int) / ts  # flux through the homogeneous structural layer
    return ({"heat_flux": Quantity(q, "W/m^2"), "interface_temperature": Quantity(t_int, "K"),
             "total_thickness": Quantity(ts + values["t_insulation"].magnitude_in("m"), "m")},
            {"execution": rec.execution_identity, "provider": rec.provider.to_dict(), "interface_spread_K": float(np.ptp(t[joint]))})


# ---------------------------------------------------------------------------
# Records: twin, candidate, evaluation, revision
# ---------------------------------------------------------------------------

SPACE = DesignSpace("two_layer_wall", "1", (
    ScientificVariable("t_structural", "mm", lower=Quantity(20, "mm"), upper=Quantity(300, "mm")),
    ScientificVariable("t_insulation", "mm", lower=Quantity(10, "mm"), upper=Quantity(300, "mm")),
))
OBJECTIVE = ObjectiveDefinition("min-thickness", "total_thickness", ObjectiveDirection.MINIMIZE, "m")


def twin_for(values: Mapping[str, Quantity]) -> ScientificTwin:
    tag = canonical_digest({k: values[k].magnitude_in("m") for k in VALUES})[:16]
    return ScientificTwin(f"wall-{tag}", "1", TwinKind.CANDIDATE, models=(ModelReference(*SERIES_MODEL), ModelReference("heat.fourier_conduction", "1")),
                          declarations=tuple(TwinDatum(k, values[k].to("m")) for k in VALUES),
                          assumptions=("perfect contact at the layer joint", "adiabatic top and bottom edges"))


def analytic_result(candidate: DesignCandidate, metrics: Mapping[str, Quantity], conditions: SliceConditions) -> ScientificResult:
    binding = ResultBinding(candidate.reference, candidate.twin, candidate.design_space)
    dims_ok = all(metrics[k].dimensionality == Quantity(1, u).dimensionality for k, u in EXPECTED_DIMENSIONS.items())
    return ScientificResult(
        result_id=f"slice-analytic-{candidate.candidate_id}-{conditions.digest[:12]}",
        values=dict(metrics),
        models=(SERIES_MODEL,),
        validity={SERIES_MODEL[0]: SERIES_DOMAIN.assess({"hot_face_temperature": conditions.hot, "cold_face_temperature": conditions.cold})},
        validation=ValidationReport(checks=(ValidationCheck(
            name="dimensional_consistency", outcome=ValidationOutcome.PASS if dims_ok else ValidationOutcome.FAIL,
            establishes=ValidationLevel.DIMENSIONALLY_VALID,
            evidence=(f"computed: every metric's dimensionality matches {EXPECTED_DIMENSIONS}",)),)),
        provenance=ProvenanceRecord(run_id=f"run-{candidate.candidate_id}-{conditions.digest[:12]}", models=(SERIES_MODEL,),
                                    metadata={RESULT_BINDING_METADATA_KEY: binding.to_dict(), "conditions_digest": conditions.digest,
                                              "material_data_digest": material_data_digest(),
                                              "material_data_classification": MATERIAL_DATA_CLASSIFICATION}),
    )


@dataclass(frozen=True)
class SliceRecord:
    values: Mapping[str, float]
    geometry_digest: str
    variant_id: str
    mesh_digest: str
    mesh_binding_digest: str
    mesh_receipt_digest: str
    pde_problem_digest: str
    geometric_checks: Mapping[str, float]
    analytic: Mapping[str, float]
    numerical: Mapping[str, Any]
    criteria_met: bool | None
    criteria_reason: str
    evaluation: DesignEvaluation
    revision: TwinRevision
    evidence_stop: Mapping[str, str]
    conditions: Mapping[str, Any] = field(default_factory=dict)
    mesh_size_m: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"classification": CLASSIFICATION, "verdict": VERDICT, "values_m": dict(self.values), "geometry_digest": self.geometry_digest,
                "conditions": dict(self.conditions), "mesh_size_m": self.mesh_size_m, "material_data_digest": material_data_digest(),
                "variant_id": self.variant_id, "mesh_digest": self.mesh_digest, "mesh_binding_digest": self.mesh_binding_digest,
                "mesh_receipt_digest": self.mesh_receipt_digest, "pde_problem_digest": self.pde_problem_digest,
                "geometric_checks": dict(self.geometric_checks), "analytic": dict(self.analytic), "numerical": dict(self.numerical),
                "criteria_met": self.criteria_met, "criteria_reason": self.criteria_reason,
                "evaluation_id": self.evaluation.evaluation_id, "eligibility": self.evaluation.eligibility.value,
                "revision_id": self.revision.revision_id, "twin_context_digest": self.revision.context_digest,
                "evidence_stop": dict(self.evidence_stop)}


def run_slice(values: Mapping[str, Quantity], *, conditions: SliceConditions, mesh_size: Quantity) -> SliceRecord:
    """One candidate through the whole pipeline.  Raises ProviderUnavailable only if Gmsh cannot run."""
    admitted = TEMPLATE.admit(values)
    slice_ = build_problem(admitted, conditions, mesh_size)
    metrics = analytic_metrics(admitted, conditions)
    evaluation_c, why = _criteria(metrics, conditions)
    ok = evaluation_c.feasible
    twin = twin_for(admitted)
    assignments = {"t_structural": admitted["t_structural"].to("mm"), "t_insulation": admitted["t_insulation"].to("mm")}
    candidate = DesignCandidate(f"wall-{slice_.variant.variant_id[:16]}", SPACE.reference, twin.reference, assignments,
                                metadata={"variant_id": slice_.variant.variant_id})
    result = analytic_result(candidate, metrics, conditions)
    problems = result_establishment_problems(result)
    # Illustrative material data never makes a result selection-ELIGIBLE: it is compared, labelled as such.
    reasons = [f"material data is {MATERIAL_DATA_CLASSIFICATION}"] + ([f"establishment problems: {list(problems)}"] if problems else [])
    evaluation = DesignEvaluation(f"eval-{candidate.candidate_id}-{conditions.digest[:12]}", candidate.reference, candidate.twin,
                                  candidate.design_space, result, eligibility=SelectionEligibility.RANKED_WITHOUT_ASSESSMENT,
                                  eligibility_reasons=tuple(reasons))
    plan_digest = canonical_digest({"rungs": ["analytic:forge.slice.series_conduction_1d", "numerical:fenicsx"],
                                    "conditions": conditions.digest, "pde_problem": slice_.problem.digest})
    revision = TwinRevision(twin, geometry_digests=(slice_.model.digest,), geometry_variant_ids=(slice_.variant.variant_id,),
                            material_digests=(STRUCTURAL.digest, INSULATION.digest), scenario_digest=conditions.digest,
                            provider_plan_digest=plan_digest,
                            uncertainty=(UncertaintyReference("heat_flux", UncertaintyStatus.UNKNOWN),
                                         UncertaintyReference("interface_temperature", UncertaintyStatus.UNKNOWN)))
    revision = revision.with_evidence(EvidenceReference(f"result-sha256:{canonical_digest(result.to_dict())}", EvidenceRole.PROVIDER_RUN,
                                                        revision.context_digest))
    try:
        num, info = numerical_metrics(slice_, admitted)
        diff = abs(num["interface_temperature"].magnitude_in("K") - metrics["interface_temperature"].magnitude_in("K"))
        verified = diff <= VERIFICATION_TOLERANCE_K
        numerical = {"status": "ran", "interface_temperature_K": num["interface_temperature"].magnitude_in("K"),
                     "abs_difference_from_closed_form_K": diff, "verification_tolerance_K": VERIFICATION_TOLERANCE_K,
                     "verification": "met" if verified else "not_met", **info}
        role = EvidenceRole.VERIFICATION if verified else EvidenceRole.PROVIDER_RUN
        revision = revision.with_evidence(EvidenceReference(f"execution:{info['execution']}", role, revision.context_digest))
    except ProviderUnavailable as exc:
        numerical = {"status": "provider_unavailable", "reason": str(exc)}
    stop = {"contract_integrity": "geometry, mesh binding, material resolution and PDE problem contracts all accepted",
            "analytic_limit": (f"numerical vs closed form: {numerical['verification']}" if numerical["status"] == "ran"
                               else "not attempted: the numerical provider is unavailable"),
            "material_data": MATERIAL_DATA_CLASSIFICATION,
            "experimental_validation": "not available: no measurement of any physical wall",
            "uncertainty": "UNKNOWN: illustrative material values carry no uncertainty"}
    return SliceRecord({k: admitted[k].magnitude_in("m") for k in VALUES}, slice_.model.digest, slice_.variant.variant_id,
                       slice_.meshed.mesh.digest, slice_.meshed.binding.digest, slice_.meshed.receipt.digest, slice_.problem.digest,
                       slice_.geometric_checks, {k: v.magnitude for k, v in metrics.items()}, numerical, ok, why, evaluation, revision, stop,
                       conditions.to_dict(), mesh_size.magnitude_in("m"))


# ---------------------------------------------------------------------------
# Discovery over the slice
# ---------------------------------------------------------------------------


class AnalyticRung:
    rung_id, provider = "analytic", "forge.slice.series_conduction_1d@1"

    def __init__(self, conditions: SliceConditions, height: Quantity) -> None:
        self.conditions, self.height = conditions, height

    def evaluate(self, key: str, a: Mapping[str, Any]) -> FidelityObservation:
        problem = domain_problem(self.conditions)
        if problem:
            return FidelityObservation(key, "analytic", 0, FidelityOutcome.REFUSED, self.provider, problem)
        values = {"t_structural": a["t_structural"], "t_insulation": a["t_insulation"], "height": self.height}
        return _observation(key, "analytic", 0, self.provider, analytic_metrics(values, self.conditions), self.conditions)


class NumericalRung:
    """Rung 2: FEniCSx on the same PDEProblem (PROVIDER_FAILED when unavailable)."""

    rung_id, provider = "numerical", "fenicsx"

    def __init__(self, conditions: SliceConditions, height: Quantity, mesh_size: Quantity) -> None:
        self.conditions, self.height, self.mesh_size = conditions, height, mesh_size

    def evaluate(self, key: str, a: Mapping[str, Any]) -> FidelityObservation:
        values = TEMPLATE.admit({"t_structural": a["t_structural"], "t_insulation": a["t_insulation"], "height": self.height})
        problem = domain_problem(self.conditions)
        if problem:
            return FidelityObservation(key, "numerical", 2, FidelityOutcome.REFUSED, self.provider, problem)
        try:
            num, _ = numerical_metrics(build_problem(values, self.conditions, self.mesh_size), values)
        except ProviderUnavailable as exc:
            return FidelityObservation(key, "numerical", 2, FidelityOutcome.PROVIDER_FAILED, self.provider, str(exc))
        return _observation(key, "numerical", 2, self.provider, num, self.conditions, "; uncertainty UNKNOWN (illustrative material data)")


#: The slice's own ladder: the closed form IS the reduced-order model here, so there is no separate rank-1 rung --
#: running the same model under a second label would be a fake fidelity escalation.
SLICE_LADDER = FidelityLadder("forge.slice.two_layer_wall", "1", (
    FidelityRung("analytic", 0, description="closed-form 1D series resistance (exact under the declared assumptions)"),
    FidelityRung("numerical", 2, description="P1 FEM of the same PDEProblem on the Gmsh mesh"),
    FidelityRung("experimental", 4, description="measurement of a physical wall (none exists)"),
))


def run_slice_campaign(count: int, *, conditions: SliceConditions, height: Quantity, mesh_size: Quantity, budget: int):
    context = canonical_digest({"conditions": conditions.digest, "template": TEMPLATE.digest, "height_m": height.magnitude_in("m"),
                                "material_data": material_data_digest(), "mesh_size_m": mesh_size.magnitude_in("m")})
    policy = PromotionPolicy(SLICE_LADDER, OBJECTIVE, {"analytic": budget})
    evaluators = {"analytic": AnalyticRung(conditions, height), "numerical": NumericalRung(conditions, height, mesh_size)}
    return run_discovery(SPACE, count=count, evaluators=evaluators, policy=policy, context_digest=context)
