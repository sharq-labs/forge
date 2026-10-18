# M1C transient nonuniform vertex FV / Backward Euler

Preimplementation decision, 2026-10-18. Branch codex/m1c-transient-fv-1d, exact
M1B base9b092d563507b0de3563c4209d42d6fc0772ea0a. Stack main -> #159 -> #160
-> #161 -> #162 -> M1B Draft#165 -> M1C local. Checkpoint#158 independent.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. M1C only; M1D/full M1 remain outstanding.

## Mathematical formulation and bounded admission

New thermal domain module conduction1d_transient_fv.py; preserve steady module,
frozen exports, shared numerical records and all historical scientific identities.
New model thermal.conduction1d.transient_piecewise_linear and realization
thermal.conduction1d.transient_piecewise_linear.vertex_fv_be, version0.1.0.
Model validity conditions remain undeclared/UNKNOWN; never validated by construction.
No global registry/capability maturity/claims reachability changes.

Grid vertices own M1B endpoint/midpoint duals. Piecewise constant regions partition
the complete interval with explicit positive cross-section A, scalar conductivity k
and volumetric storage c (J/m3/K). No density, heat capacity or area defaults. Resolve
k/c through actual MaterialPropertySet/MaterialState, require exact known unambiguous
constant (no interpolation/ranges/state-dependent functions), declared phase and source.
ASSUMED origins permitted only under explicit SYNTHETIC_FIXTURE admission; they stay
assumptions. PHYSICAL_INPUTS accepts sourced/compiled constants but not applicability
promotion. Scalar phase-constant Fourier model only: multiphase/nonlinear/anisotropic,
temperature-dependent coefficients and unqualified wider cases refuse.

C_i = sum_regions c_r A_r length(dual_i intersect region_r), strictly positive J/K.
For edge [x_i,x_i+1], R_i = sum_regions length(edge intersect region)/(k_r A_r)
plus explicitly declared contact thermal resistances K/W strictly inside that edge.
G_i=1/R_i. Conductivity jumps use series resistances, never arithmetic averaging.
Contact at a represented vertex refuses (one nodal temperature cannot represent its
jump). Quasi-1D series geometry only; no lateral/spreading resistance claim.
P_i = sum q_r A_r overlap(dual_i,region_r), declared piecewise constant volumetric
source W/m3 on each step window, never silently zero.

BE: C_i(T_i_new-T_i_old)/dt = sum_neighbors G_ij(T_j_new-T_i_new)+P_i+B_i.
Each interior face has one oriented power F_i=G_i(T_i_new-T_i+1_new), positive +x;
its adjacent contributions are -F_i,+F_i. Integrated energy E_i=C_i*T_i with explicit
zero-reference linear storage. Each step records local residuals and independent
boundary/source/storage totals with caller-declared dimensioned tolerances.

Both boundaries explicit: inward Neumann heat-flux density [W/m2] times actual end
area gives positive inward B at either end (right positive inward means -x). Dirichlet
replaces endpoint equation; the reservoir exchange is recovered from that endpoint's
storage change minus interior/source terms. Its boundary half-volume remains in energy
accounting. Initial Dirichlet values must agree at run start. Both-Neumann transient
is admitted: positive C/dt regularizes the constant mode, unlike steady all-Neumann.
Dirichlet reservoir exchange is an algebraic boundary reaction, not an independently
measured flux. Tests must independently check specified flux/source cases and analytical
solutions; never cite the recovered reaction as independent proof of physics.

## Provider, state, time, failure and authority

Reuse NumericalProblem/Method/Provider/ExecutionRecord, OperatorIdentity, UnitBoundary,
SolverIdentity/Settings, ConvergenceState and diagnostics. Sparse tridiagonal CSR assembly;
new domain-local sparse-only SuperLU provider through NumericalProvider. Existing
SciPyLinearProvider silently bounds dense conditioning <=1000; do not change it or use
that path here. New provider never densifies and explicitly reports conditioning UNKNOWN.
Actual build identity includes SciPy version and FORGE implementation version. Residuals
are measured algebraic diagnostics, never certified error estimates. Independently
recompute residual against original assembled operands, verify execution/problem/provider/
method identities and succeeded state; failed/nonfinite/incorrect provider results refuse.

Compose exact M1B adapter/support/primary and integrated thermal semantics. Initial source
must already be bound with normalized input bytes and exact problem context including
initial TimePoint, material regions, storage/flux assumptions and mathematical admission.
Register explicit derived C from actual material resolution (normalization origin, not
invented physical source). Return domain-local immutable step records containing M1B
placed primary/energy records, complete declaration/initial/previous-state identities,
TimeWindow and exact dt, actual provider execution and diagnostics, fluxes, boundary
reactions/supplied fluxes, volumetric powers and conservation residuals. Output UQ UNKNOWN.

Serial session on one fixed mesh. Full TimeBasis/TimePoint/TimeWindow identities, exact
start=current and explicit dt=end-start required; no implicit time or continuation.
Forcing bytes bind complete window/boundaries/sources. Require provider/build/method,
material, original initial source and live state integrity on each step. Prepare/check
all outputs before publishing current state/time. Once any attempted solve fails, poison
session; no silent retry/partial continuation. Partial publication also poisons session.
No checkpoint, rollback, adaptation or M1D orchestration claim.

## Compatibility and independent tests

Only a new domain module and tests/docs; no existing source changes, imports/IDs/schema
relabelled, frozen/certified pins or mature capability declaration altered. New domain
records /1 audit-only, no deserialization grants state/solver authority. Legacy transient
adaptation guard unchanged. M1B state-only admission does not grant solver authority;
M1C requires a separate typed formulation/admission and explicit qualified declarations.

Tests authored but NOT RUN: nonuniform equilibrium, insulated integral, prescribed
boundary/source balance from external terms, manufactured exact source, temporal/spatial
refinement, half duals, discontinuity/series resistance/contact, material/source/initial/
BC/time failures, stale mesh/state, provider failure/false residual/build drift, unsupported
physics and coefficient health. Analytical comparisons are synthetic mathematical
verification designs, not experimental evidence. No pytest/solves/providers/assurance/
mutation/OD-3 run; compile-only/static allowed. Independent architecture/scientific review.

M1D still must supply adaptation decisions/transfers/rebuild/cache-history/rollback/full
history and adaptive numerical studies. Owner still selects real physical sources,
validity envelope and integration rules for wider models, and authorizes execution/gates.

## Final static-review corrections and integration hold

Dirichlet replacement rows retain W units using their original positive diagonal
scale. Require explicit temperature_atol [K] and local_power_atol [W], independently
check row-wise residuals and endpoint values after solving. Global residuals and
reconstructed reactions cannot substitute for an endpoint constraint check.
Bind exact original storage identity, its actual J/K coefficient bytes and initial
TimePoint into session configuration. Provider binding hashes this module and the
actual SuperLU binary plus NumPy/SciPy versions; source/binary must be readable.

Model discovery in tests/test_core_guards.py:199,534 pins19 models. New separately
identified transient model makes the expected population20 by static inspection.
No guard/count/certificate edited and no observed test failure claimed. This is a
known integration hold requiring explicit owner compatibility/count-pin review and
separate OD-3 decisions before integration; do not hide or lazily suppress discovery.
