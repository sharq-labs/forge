"""Build and verify a Core certificate: what was certified, and is it still that.

The question this answers, in one command, is the one V1 could not be asked:

    is the checked-out tree exactly the tree that was certified?

V1 could be *computed* — its algorithm is written out inside the certificate
itself and reproduces its stored digest exactly at the commit it names — but
nothing executed it. There was no script, no test, and no command. So the
certificate went two sprints out of date without anything noticing, which is a
gap in the infrastructure rather than in the algorithm.

What V2 adds
------------
* **an executable algorithm**, here, rather than a snippet quoted in prose;
* **a per-file manifest**, so a failure names the file that moved instead of
  reporting that two hex strings differ;
* **named scope areas**, so what is certified is a table a reader can argue
  with rather than one path;
* **a verifier that reads the stored certificate** and compares the tree to
  it — never regenerating the expected values from the same tree it is
  checking, which would make verification a tautology.

The digest algorithm, stated exactly
------------------------------------
Per file::

    file_digest = sha256(exact bytes on disk)

Per area, over its files sorted by UTF-8 path bytes::

    area_digest = sha256( for each: path_utf8 + b"\\x00" + file_digest_bytes )

Over the whole certificate, areas sorted by name::

    aggregate = sha256( for each: area_name_utf8 + b"\\x00" + area_digest_bytes )

and the rules that make that deterministic:

=========================  ====================================================
root                       the repository root
included                   each area's explicit glob patterns, files only
excluded                   any path with a ``__pycache__`` component; ``*.pyc``
path normalization         repository-relative, POSIX separators, no ``./``
ordering                   sorted by the UTF-8 encoded path bytes
byte handling               exact bytes; nothing is decoded
line endings               **not normalized** — CRLF and LF are different files
symlinks                   refused: a symlink in scope fails the build
generated files            none in scope beyond the exclusions above
hash                       SHA-256 throughout
=========================  ====================================================

Line endings are deliberately not normalized. This repository pins several
trees by SHA-256 over raw bytes already, and a certificate that silently
normalized would disagree with them and would also hide a real change to what
ships.

The per-area construction is V1's, with repository-relative paths in place of
area-relative ones. That means **V2's core area digest is not comparable to
V1's stored value by construction**, so the certificate also records
``v1_compatible_core_digest``, computed exactly V1's way, which makes the
continuity between them checkable rather than asserted.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: Bumped when the algorithm or the certificate's shape changes. A verifier
#: refuses a certificate whose schema it does not implement rather than
#: comparing fields that may not mean what it thinks.
CERTIFICATE_SCHEMA = "core_certificate/2"

#: Identity of the code that produced a certificate, recorded in it. Not a
#: version of the repository: a version of *this algorithm*.
TOOL_ID = "tools/certification/core_certificate.py"
TOOL_VERSION = "2.5.0"  # 2.5.0: derived dependency closure of every certified module (BR-15)
# 2.4.0: registry pin covers source bytes; loader detection widened (F2, fourth pass)
# 2.3.0: dynamic import reach, production registry pin (hostile review F2, third pass)
# 2.2.0: verdict_authority area and the derived authority-closure check (hostile review F2)

EXCLUDED_DIR_PARTS = frozenset({"__pycache__"})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class ScopeArea:
    """One named part of what is certified, and the argument for including it.

    ``file_reasons`` is for an area where one sentence for the whole area is not
    enough, because each file is in for its own reason. When it is non-empty the
    builder requires the files the patterns enumerate and the files given a
    reason to be **the same set**: a file that appears under a glob without a
    reason is refused rather than certified silently, and a reason for a file
    that no longer exists is refused rather than left describing nothing.
    """

    name: str
    classification: str
    patterns: tuple[str, ...]
    why: str
    file_reasons: tuple[tuple[str, str], ...] = ()


#: The certification control plane: the code that decides what "certificate
#: valid" MEANS, as distinct from the code a certificate is about.
#:
#: Without this area a change to the verifier changed the meaning of PASS while
#: the certified manifest stayed byte-identical, so a certificate could keep
#: verifying under a verifier it was never produced by. With it, the verifier,
#: the workflows that run it, the self-checks the certificate child runs, and
#: every helper they load are pinned by the certificate they validate.
#:
#: The boundary is narrow on purpose. It is not ``tools/**`` or ``.github/**``:
#: a file is in only when an edit to it can turn a failing certificate, a
#: skipped gate or an incomplete mutation population into a PASS. Each file
#: carries its own reason, and ``tools/certification/*.py`` is matched by glob
#: so a new certification module cannot be added outside the plane: the
#: builder refuses it until it has a reason here.
#:
#: Not self-referential: ``certification/current_core_v2.json`` is the output
#: of this plane and is never matched by it, so no fixed point is needed.
CERTIFICATION_CONTROL_FILES: tuple[tuple[str, str], ...] = (
    (".github/workflows/recertify-hardened-core.yml",
     "defines the source gates, the evidence the certify job consumes, the "
     "official-builder invocation and the certificate-child checks. Removing "
     "a gate from certify's needs, or a step from a gate, changes what a "
     "certificate attests without touching any Python"),
    (".github/workflows/tests.yml",
     "decides which pull requests delegate assurance to recertification and "
     "what the certificate-child job runs. A narrower classifier call or a "
     "dropped child check lets a core change merge on the ordinary suite"),
    ("benchmarks/core_freeze_v1/audit/reproduce.py",
     "loaded by core_freeze.py through importlib to compute the live contract "
     "facts the freeze self-check compares against the stored manifest; it is "
     "a helper of the verifier, not a benchmark"),
    ("tests/test_core_certificate.py",
     "holds the certificate self-checks the certificate child executes. A "
     "self-check that no longer asserts would still be reported as passed"),
    ("tests/test_core_freeze_manifest.py",
     "holds the freeze self-checks the certificate child executes, for the "
     "same reason as the certificate self-checks"),
    ("tests/test_local_assurance.py",
     "hostile checks for the local authority path: automatic workflows stay "
     "disabled, dirty or moved sources are refused, required runtimes exist and "
     "frozen evidence tampering is detected"),
    ("tests/scientific_regression/manifest.json",
     "is the fixed false-confidence regression population executed by the "
     "regression312 source gate. Changing its membership changes what that "
     "gate proves, so the certificate must pin the exact manifest bytes"),
    ("src/__init__.py",
     "the src.engcore alias package; executed before any certified module when "
     "the core is imported through that path, so an import-time side effect here "
     "runs ahead of every certified byte"),
    ("src/engcore/__init__.py",
     "package initialisation executed before every certified module is imported; "
     "an import-time side effect here could replace a certified symbol"),
    ("src/engcore/api_snapshot.py",
     "both freeze verifiers compute the live frozen-API facts through it; a "
     "change to how it enumerates symbols would let the frozen digest keep "
     "matching while the contract drifts"),
    ("tools/__init__.py",
     "executed on every import of tools.certification, before any verifier "
     "code runs; an import-time side effect here could replace a verifier"),
    ("tools/forge_check.py",
     "selects the fixed scientific regression node ids and builds the pytest "
     "command used by regression312. Weakening this selector could make the "
     "gate pass while exercising less than the pinned regression manifest"),
    ("tools/certification/__init__.py",
     "package initialisation executed before every certification module"),
    ("tools/certification/assert_clean_tree.py",
     "the per-gate proof that a source gate did not modify, add or delete a "
     "repository file; a weaker check lets a gate pass on a mutated checkout "
     "while certify reads a fresh one"),
    ("tools/certification/branch_policy.py",
     "states the merge policy the certificate child's checks rely on and "
     "reports whether the repository enforces it"),
    ("tools/certification/certificate_lineage.py",
     "binds a certificate child to its exact parent and to the certify run "
     "that produced it; without it a stale or hand-assembled certificate with "
     "matching bytes verifies"),
    ("tools/certification/core_certificate.py",
     "the builder and verifier: the digest algorithm, this scope table and "
     "the definition of a verifying certificate"),
    ("tools/certification/core_freeze.py",
     "the Core Freeze V1 verifier the freeze self-checks call, which itself "
     "calls verify_certificate"),
    ("tools/certification/core_freeze_v2.py",
     "the Core Freeze V2 verifier that binds the Hybrid UQ contract and is "
     "executed by the pinned certificate-child freeze self-check; weakening it "
     "would change whether V2 is accepted without changing Hybrid UQ source"),
    ("tools/certification/core_freeze_v3.py",
     "the Core Freeze V3 verifier the pinned certificate-child freeze self-check "
     "executes since V3 superseded the V2 serialization contract; weakening it would "
     "change whether the hardened routed-uncertainty contract is accepted without "
     "changing Hybrid UQ source"),
    ("tools/certification/guard_reach.py",
     "the guard REACH verifier (I-16): it refuses a guard_reach_ledger.json that "
     "is not self-consistent and implements the four static bypass checks the "
     "2026-09-16 re-audit named. A weaker check would let a guard whose reach "
     "nobody states pass as a guard production runs"),
    ("tools/certification/hardening_assurance.py",
     "builds the assurance record from the gates' downloaded evidence and "
     "re-validates it on the child; it is what turns job results into claims"),
    ("tools/certification/skip_admission.py",
     "the committed skip policy and the provider availability probe: it decides, "
     "skip by skip, whether a test that did not run may still count toward a gate. "
     "A broader rule, a weaker probe or a dropped protected-test source would let "
     "a skipped trust test pass as an explained optional-provider skip"),
    ("tests/test_skip_admission.py",
     "hostile specifications that a wrong reason, an available or unknown provider, "
     "an unapproved scope, malformed metadata, a skipped trust test or tampered "
     "skip evidence refuses assurance instead of being admitted"),
    ("tools/certification/local_assurance.py",
     "executes the authoritative local source gates, freezes their evidence "
     "manifest, builds local provenance and performs the final certificate-child "
     "verification before a local result may say SAFE_TO_PUSH"),
    ("tools/certification/api_surface_v4.py",
     "the V4 deep API surface (I-29, R-69): the method signatures and enum "
     "member POSITIONS the frozen snapshot never described, which is why "
     "deleting a method moved neither the V1 nor the V2 digest. A surface "
     "nothing pins is a surface nobody compares"),
    ("tools/certification/core_freeze_v4.py",
     "the Core Freeze V4 verifier (I-29): it proves, difference by difference, "
     "that every change since the V1 surface AS V1 COMMITTED IT is additive, "
     "requires the V3 supersession to be the named refusal rather than any "
     "exception, and re-derives every figure an assurance record asserts. The "
     "audited checks compared the live surface with the live surface"),
    ("tools/certification/mutation_workspace.py",
     "owns pristine seed/worker isolation, complete byte/mode manifests, "
     "restore refusal and target subprocess lifecycle; weakening it allows "
     "contaminated mutation evidence to be credited"),
    ("tools/certification/ownership.py",
     "decides which files of a checkout are repository source for every assurance traversal (seed "
     "population, the impact graph, owned snapshots): tracked files always, untracked files outside "
     "environment roots, symlinks never followed. A weaker rule lets a toolchain tree be scanned or "
     "copied as source, or lets a tracked file hide under an environment-looking path"),
    ("tools/certification/performance_telemetry.py",
     "diagnostic timing helper imported by the local runner and mutation "
     "workspace; timing has no authority, but imported executable helpers "
     "must remain bound to the certified control-plane implementation"),
    ("tools/certification/mutation_startup.py",
     "controls the sealed Python/pytest startup of certified mutation "
     "execution: the interpreter identity check, the forced plugin-autoload "
     "and bytecode policy, and the Formal and V4 pytest invocation flags; "
     "weakening it would let host plugins, startup variables or stale "
     "bytecode shape a mutation verdict"),
    ("tests/test_mutation_workspace.py",
     "hostile specifications of persistent workspace restoration, isolation, "
     "cleanup, attribution preservation and diagnostic telemetry separation"),
    ("tools/certification/formal_xdist_guard.py",
     "records pytest-xdist's structured worker signals for Formal attempts run "
     "with more than one pytest worker and decides whether such an attempt is "
     "admissible; weakening it would let a crashed or lost worker, or a worker "
     "importing the run's own project roots from outside the mutation copy, be "
     "credited as a kill"),
    ("tests/test_formal_xdist.py",
     "hostile specifications that real xdist worker crashes, lost workers and "
     "foreign imports refuse the Formal round instead of earning credit"),
    ("tools/certification/mutation_population.py",
     "the canonical formal mutation population, the shard rule and the "
     "coverage proof; a wrong union with the right count would certify a "
     "mutation family that never ran"),
    ("tests/test_mutation_population_v4.py",
     "the V4 population's own guard, run on every FAST invocation: every folded "
     "mutation must still match the source it names exactly once and change "
     "code. Twenty-five had already gone stale when the round folded them in, "
     "and a stale mutation is a guard verified by nobody whose log still says "
     "KILLED. A certificate that claims a mutation round is claiming this check "
     "ran, so the check is pinned by it"),
    ("tools/certification/mutation_v4_runner.py",
     "the runner for the V4 guard-mutation population (I-30, R-67): it works in "
     "an isolated copy and counts a kill only when the ONE test an entry names "
     "failed, read from that run's JUnit report. The audited runners mutated the "
     "shared checkout and credited any non-zero exit to the guard, so a broken "
     "import read as a guard firing"),
    ("tools/certification/recertification_scope.py",
     "the single classifier deciding which changes require recertification "
     "and which self-checks are deferred to the certificate child"),
)


#: What V2 certifies, and why each part is in.
#:
#: The criterion is deliberately narrow: an area is in when a silent edit to it
#: would change **what a verdict means**, rather than change an answer. A domain
#: solver produces answers and is assured by its own tests; the registry the
#: core reads to decide whether a threshold set is *declared* decides whether a
#: level may be awarded at all, and that is a different kind of thing.
SCOPE: tuple[ScopeArea, ...] = (
    ScopeArea(
        name="core",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/scientific/**/*.py",),
        why=(
            "the Scientific Core's contracts: the records, their invariants and "
            "their refusals. This is what V1 certified and it remains the "
            "centre of the certificate"
        ),
    ),
    ScopeArea(
        name="trust_registry",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/domains/__init__.py",),
        why=(
            "the domain-layer declarations the core verifies against and cannot "
            "see past: SCIENTIFIC_THRESHOLD_DECLARATIONS decides whether a "
            "threshold set is declared, and SCIENTIFIC_ROUTE_DECLARATIONS "
            "decides whether two routes are independent. An edit here turns a "
            "gate that awards nothing into one that awards a level, without "
            "touching a line of the core. One file, and the strongest case for "
            "inclusion outside scientific/"
        ),
    ),
    ScopeArea(
        name="runtime_data",
        classification="RUNTIME_SUPPORT",
        patterns=("src/engcore/data/**/*.py",),
        why=(
            "the plane a ScientificDataReference resolves through. The core "
            "names bulk data by digest and count and never reads it; the "
            "length-then-digest verification that makes that reference worth "
            "anything is here, as is the field container's shape, support and "
            "finiteness enforcement"
        ),
    ),
    ScopeArea(
        name="evidence_identity",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/adequacy/**/*.py",),
        why=(
            "predictive evidence identity and pairing. Two models may only "
            "receive a comparative conclusion if they were assessed against the "
            "same canonical evidence, and this is where that is decided"
        ),
    ),
    ScopeArea(
        name="inference_admission",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/inference/**/*.py",),
        why=(
            "the admission invariant for forward rows: a posterior may only "
            "be built from predictions that were admitted. A trust boundary in "
            "its own right, and one the certified mutation harness exercises"
        ),
    ),
    ScopeArea(
        name="routed_uncertainty",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/hybrid_uq/**/*.py",),
        why=(
            "Core V2: which approximation produced an uncertainty and whether "
            "it may be reported at all. The local-Gaussian validity diagnostics, "
            "the multistart, the router's refusal to use a grid V1 refuses, and "
            "the rule that a refused route emits no numbers each decide what a "
            "reported interval MEANS; a silent edit here turns a refusal into a "
            "precise-looking number"
        ),
    ),
    ScopeArea(
        name="predictive_representation",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/uq/**/*.py",),
        why=(
            "not representation only: posterior_predictive_uq is where the grid "
            "predictive route refuses an under-resolved posterior and refuses to "
            "renormalise mass away from rejected rows, and the certified "
            "routed_uncertainty and evidence_identity areas call it. The main "
            "audit found a collapsed 3x3 grid reported as SUPPORTED with zero "
            "parameter uncertainty through exactly this call, so a silent edit "
            "here changes what a certified interval means"
        ),
    ),
    ScopeArea(
        name="execution_trust",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/execution/**/*.py",),
        why=(
            "the trusted-execution record and the trusted consensus gate decide "
            "whether an execution is reported trusted and whether an artifact-"
            "backed independence claim holds. They were a recertification "
            "trigger without being pinned, so a certificate could verify over "
            "bytes it never measured"
        ),
    ),
    ScopeArea(
        name="credibility_assurance",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/credibility/**/*.py",),
        why=(
            "the whole credibility package. The production hardening round certified its trust-critical "
            "boundary (evidence authority/conflict/lineage, the composite assurance identity and its replay "
            "binding); hostile review F2 found the rest of the package deciding verdicts outside the "
            "certificate -- credibility/evidence.py::derive_verdict is what turns a report into SUPPORTED, "
            "and evidence_basis_of is what says a verdict rests on validation. The package owns those "
            "semantics, so the package is in"
        ),
    ),
    ScopeArea(
        name="assurance_admission",
        classification="CORE_CERTIFIED",
        patterns=(
            "src/engcore/sria/admission.py",
            "src/engcore/sria/assurance/*.py",
            "src/engcore/sria/charter.py",
            "src/engcore/sria/evidence.py",
            "src/engcore/sria/gateway.py",
            "src/engcore/sria/campaign/**/*.py",
            "src/engcore/sria/decision/**/*.py",
        ),
        why=(
            "the only path by which evidence becomes scientific belief: critics, "
            "the Arbiter's verdict, the obligations it evaluates, the admission "
            "authority and the belief gateway. The main audit found assessments "
            "of one subject admitting another, a caller-built obligation set "
            "replacing the charter's, and one critic's check satisfying another "
            "critic's obligation, all green and none mutated. Whatever sria is as "
            "an application, the decision that turns evidence into belief is a "
            "trust boundary of the core. BR-15: the certified stop review takes its Arbiter "
            "decisions, and their order, from the campaign event log (sria/campaign/events.py), "
            "and claims/falsification.py, novelty.py and discovery_passport.py bind verdicts to "
            "the claim and content identity sria/decision/hypotheses.py defines; both packages "
            "are therefore in, as certified_dependency_problems derives"
        ),
    ),
    ScopeArea(
        name="verdict_authority",
        classification="CORE_CERTIFIED",
        patterns=(
            "src/engcore/claims/**/*.py",
            "src/engcore/authority/**/*.py",
            "src/engcore/blindfold/**/*.py",
            "src/engcore/sria/__init__.py",
            "src/engcore/sria/actions.py",
            "src/engcore/sria/domain_pack.py",
            "src/engcore/sria/errors.py",
            "src/engcore/sria/outcomes.py",
            "src/engcore/sria/provenance.py",
            "src/engcore/sria/signatures.py",
            "src/engcore/sria/uncertainty.py",
            "src/engcore/sria/calibration/**/*.py",
            "src/engcore/systems/__init__.py",
            "src/engcore/systems/twin_revision.py",
        ),
        why=(
            "hostile review F2: what a claim's SUPPORTED means was decided outside the certificate. The "
            "claims package owns claim admissibility, criteria grounding (adapters/), the verdict "
            "(claims/verdict.py, claims/assessment.py), the credibility vector and its risk policy; "
            "authority/ owns who may attest evidence (the ledger and its genesis); blindfold/ owns "
            "evidence isolation; and the listed sria modules are the uncertainty-channel vocabulary, "
            "provenance and calibration those decisions read. The boundary is not a hand list: "
            "authority_closure_problems derives the static import closure of the verdict, assessment, "
            "authority and blindfold roots and refuses a certificate whose areas do not cover it, so a "
            "module that starts deciding authority cannot sit outside this area unnoticed. BR-15: "
            "systems/twin_revision.py is not an answer: it defines the context identity twin evidence is "
            "bound to and refuses validation, calibration or measurement evidence on a CANDIDATE twin, "
            "which claims/twin_evidence.py relies on; importing it runs systems/__init__.py"
        ),
    ),
    ScopeArea(
        name="system_runtime_authority",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/system_runtime/**/*.py",),
        why=(
            "hostile review F2, eighth pass: certified claims modules (claims/credibility_vector.py, "
            "claims/attestation.py) read system_runtime records (ApplicabilityReport, NodeReceipt), and the "
            "system runtime decides whether a coupled node succeeded -- including the F5 guard that refuses a "
            "node whose required conservation failed, or whose run executed another graph or plan. A change "
            "there could change what a recorded system result means without moving the certificate"
        ),
    ),
    ScopeArea(
        name="system_runtime_dependencies",
        classification="CORE_CERTIFIED",
        patterns=(
            "src/engcore/scenarios/**/*.py",
            "src/engcore/materials/**/*.py",
            "src/engcore/multiscale/**/*.py",
            "src/engcore/providers/**/*.py",
            "src/engcore/numerical/**/*.py",
            "src/engcore/pde/**/*.py",
            "src/engcore/coupling/**/*.py",
            "src/engcore/spatial/**/*.py",
        ),
        why=(
            "BR-15: what the certified system runtime and multiphysics runtime record as a node result is decided "
            "partly here. scenarios/environment.py refuses to extrapolate a boundary condition, to bridge a gap wider "
            "than the authorized one or to interpolate across a declared discontinuity; materials/properties.py keeps "
            "a datum with no stated uncertainty UNKNOWN and refuses to arbitrate between sources; the multi-timescale "
            "runtime's final slow state, uncertainty included, is committed into system state by "
            "system_runtime/authorities.py, and it decides run status and the context a resume is bound to; "
            "providers/records.py keeps a provider output's missing uncertainty UNKNOWN and a failed run's outputs "
            "unexposed, and providers/catalog.py feeds the preflight's provider version and digest checks; numerical/, "
            "pde/, coupling/ and spatial/ hold the execution records, participant state contracts and the mesh and field "
            "identities those packages compare, resume against and bind a PDE problem's identity to. A change to any of them could turn a missing input or uncertainty into a value "
            "without moving the certificate"
        ),
    ),
    ScopeArea(
        name="harness",
        classification="HARNESS",
        patterns=(
            "tests/mutation_guards.py",
            "tests/test_core_guards.py",
            "tests/test_repair_guidance.py",
            "tests/test_offset_unit_declaration.py",
            "tests/test_core_semantic_invariants.py",
            "tests/hybrid_uq/test_hybrid_uq_trust_boundary.py",
            "tests/test_core_trust_closure.py",
            "tests/domains/battery/test_audit_domains_battery_pulse.py",
            "tests/domains/battery/test_audit_inference_ocv_applicability.py",
            "tests/domains/electrical/test_audit_consensus_dc_scale.py",
            "tests/domains/electrical/test_audit_domains_debye_conductor_class.py",
            "tests/domains/kinetics/test_audit_consensus_cstr_levels.py",
            "tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py",
            "tests/hybrid_uq/test_audit_hybrid_grid_route.py",
            "tests/hybrid_uq/test_audit_hybrid_identifiability.py",
            "tests/hybrid_uq/test_audit_hybrid_local_route.py",
            "tests/hybrid_uq/test_audit_hybrid_predictive.py",
            "tests/hybrid_uq/test_audit_hybrid_records.py",
            "tests/hybrid_uq/test_hybrid_uq_identifiability_predictive.py",
            "tests/hybrid_uq/test_hybrid_uq_local_route.py",
            "tests/hybrid_uq/test_hybrid_uq_records.py",
            "tests/hybrid_uq/test_hybrid_uq_router.py",
            "tests/inference/test_audit_inference_grid_resolution.py",
            "tests/inference/test_audit_inference_heldout_study.py",
            "tests/inference/test_audit_inference_identifiability.py",
            "tests/inference/test_audit_inference_posterior_binding.py",
            "tests/inference/test_audit_inference_split_guards.py",
            "tests/inference/test_grid_resolution_repair.py",
            "tests/mcp/test_audit_domains_electrothermal_transient.py",
            "tests/mcp/test_audit_domains_refused_coupling.py",
            "tests/mcp/test_audit_results_declarations.py",
            "tests/mcp/test_audit_results_validity_binding.py",
            "tests/test_audit_consensus_artifact_authority.py",
            "tests/test_audit_consensus_execution_binding.py",
            "tests/test_audit_consensus_level_issuers.py",
            "tests/test_audit_consensus_resolution_and_floor.py",
            "tests/test_audit_consensus_threshold_authority.py",
            "tests/test_audit_consensus_trusted_record.py",
            "tests/test_audit_results_evaluation.py",
            "tests/test_audit_results_stored_results.py",
            "tests/test_audit_sria_assurance_binding.py",
            "tests/test_audit_sria_claim_binding.py",
            "tests/test_audit_sria_cost_critic.py",
            "tests/test_audit_sria_gateway_history.py",
            "tests/test_audit_sria_obligation_state.py",
            "tests/test_audit_sria_persistence_derivation.py",
            "tests/test_audit_sria_policy_binding.py",
            "tests/test_audit_sria_stop_review_grounds.py",
            "tests/test_audit_sria_trust_root.py",
            # The V4 population (R-67) and the suites its 676 entries name, which a kill
            # in that round is a statement about, plus the support modules all of these
            # import. Derived rather than remembered: `harness_import_closure` computes
            # the closure and `harness_pinning_problems` refuses a scope that does not
            # cover it, which is what makes the next helper a failure instead of a gap.
            "tests/mutation_population_v4.py",
            "tests/domains/battery/battery_cases.py",
            "tests/domains/battery/test_battery_coupling.py",
            "tests/hybrid_uq/false_confidence_cases.py",
            "tests/hybrid_uq/hybrid_synthetic.py",
            "tests/hybrid_uq/test_core_scientific_audit_batch*.py",
            "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py",
            "tests/inference/test_field_observation_spike.py",
            "tests/inference/test_reproducibility_and_evidence.py",
            "tests/inference/test_tcr_heldout_uq.py",
            "tests/issued_levels.py",
            "tests/mcp/test_core_scientific_audit_batch*.py",
            "tests/mcp/test_evidence.py",
            "tests/route_declarations_for_tests.py",
            "tests/test_core_runtime_caches.py",
            "tests/test_core_scientific_audit_batch*.py",
            "tests/test_cross_solver_consensus.py",
            "tests/test_external_oracles.py",
            "tests/test_guard_reach_ledger.py",
            "tests/test_scientific_core.py",
            "tests/test_trusted_consensus_gate.py",
            "tests/scientific/validation_core/*.py",
            "tests/scientific/replay_core/*.py",
            "tests/scientific/verification/*.py",
            "tests/scientific/certification_core/*.py",
            "tests/credibility/evidence_graph/*.py",
            "tests/uq/model_form/*.py",
            "tests/uq/budget/*.py",
            "tests/uq/combined/*.py",
            "tests/execution/orchestration/*.py",
            "tests/execution/test_verification_runner*.py",
            "tests/scientific/knowledge/*.py",
            "tests/scientific/equations/*.py",
            "tests/credibility/evidence_graph/test_knowledge_bridge.py",
            "tests/credibility/test_knowledge_replay_binding.py",
            "tests/credibility/test_assurance_manifest_v2.py",
            "tests/credibility/test_assurance_replay_bundle_v2.py",
        ),
        why=(
            "the mutation harness, every suite in its TARGETS, every suite the V4 "
            "population's entries name, and every module under tests/ that any of "
            "them imports. 'N/N killed' is a statement about these exact bytes: the "
            "same sentence over a weakened suite would be worth nothing, so the "
            "suites are pinned alongside the runner. The helper modules joined in "
            "I-30 (R-68, finding 93): hybrid_synthetic.py was read by ten certified "
            "targets and measured by nothing, and the branch changed it by twelve "
            "lines without moving the certificate. The list is checked against the "
            "derived import closure, because a hand-maintained list is the finding"
        ),
    ),
    ScopeArea(
        name="certification_control",
        classification="CERTIFICATION_CONTROL",
        patterns=(
            ".github/workflows/recertify-hardened-core.yml",
            ".github/workflows/tests.yml",
            "benchmarks/core_freeze_v1/audit/reproduce.py",
            "src/__init__.py",
            "src/engcore/__init__.py",
            "src/engcore/api_snapshot.py",
            "tests/test_core_certificate.py",
            "tests/test_mutation_population_v4.py",
            "tests/test_core_freeze_manifest.py",
            "tests/test_local_assurance.py",
            "tests/test_skip_admission.py",
            "tests/test_mutation_workspace.py",
            "tests/test_formal_xdist.py",
            "tests/scientific_regression/manifest.json",
            "tools/__init__.py",
            "tools/forge_check.py",
            "tools/certification/*.py",
        ),
        why=(
            "the certification control plane: the verifier, the workflows that "
            "run it, the self-checks the certificate child executes and the "
            "helpers they load. A certificate is only as meaningful as the "
            "code that says it verifies, so that code is pinned by the "
            "certificate it validates. Each file states its own reason"
        ),
        file_reasons=CERTIFICATION_CONTROL_FILES,
    ),
    ScopeArea(
        name="runtime_dependencies",
        classification="RUNTIME_ENVIRONMENT",
        patterns=("pyproject.toml",),
        why=(
            "the dependency declaration every source gate installs from "
            "(pip install -e .[dev,mcp,oracles]) and the pytest configuration "
            "every suite runs under. The assurance record's pip-freeze digests "
            "say what was resolved; this pins what was asked for, so a "
            "dependency or test-configuration edit cannot ride on a "
            "certificate measured under the previous one"
        ),
    ),
)

#: Named here rather than left implicit, because a reader's first question about
#: any certificate is what it does *not* cover.
OUT_OF_SCOPE: tuple[tuple[str, str], ...] = (
    ("src/engcore/domains/** (except __init__.py)",
     "scientific models and solvers. They produce answers rather than decide "
     "what a verdict means, and they carry their own assurance — three of them "
     "are byte-pinned by frozen experiments"),
    ("src/engcore/mcp/**, src/engcore/product/**",
     "the outer product/tool transport boundary: a consumer of claims and "
     "credibility, never scientific authority. The natural-language grounding that "
     "decides whether a proposal's criteria are the user's is claims/adapters/**, "
     "inside the verdict_authority area"),
    ("src/engcore/design/**, sria/** (except the assurance/admission chain, the campaign and decision "
     "packages and the modules the verdict_authority area lists), systems/** (except __init__.py and "
     "twin_revision.py), and the provider runner scripts under the top-level providers/ directory",
     "applications built on the core. authority_closure_problems refuses a certificate if the verdict "
     "and authority roots ever import one of them; certified_dependency_problems refuses one that any "
     "certified module imports unless a CERTIFIED_DEPENDENCY_EXCLUSIONS edge states why that importer's use "
     "cannot grant authority"),
    ("tests/** (except the harness area, the two self-check modules and the pinned regression manifest)",
     "assurance for everything above, not part of what is certified. They "
     "still trigger recertification (tools/certification/recertification_scope.py), "
     "because the gates' results are claims about them"),
    ("tests/conftest.py",
     "labels execution tiers only. The certificate child does not trust it to "
     "run the self-checks: it requires every deferred self-check to be "
     "reported PASSED in JUnit, so a hook that skipped one fails the child"),
    ("benchmarks/** (except the freeze probe), experiments/**, certification/**",
     "measurements, frozen artefacts, and the certificate itself — a "
     "certificate whose scope contained its own bytes would need a fixed point"),
    (".github/** (except the two certification workflows), tools/** (except "
     "tools/__init__.py, tools/forge_check.py and tools/certification/*.py)",
     "repository automation that does not decide whether a certificate "
     "verifies. .github/workflows/trust-mutations.yml in particular is an "
     "advisory run of a population the recertify workflow re-executes itself"),
    ("requirements.txt, Dockerfile",
     "not what the gates install from: every gate runs pip install -e on "
     "pyproject.toml, and the Dockerfile copies requirements.txt without "
     "installing it. The reproduce image runs on pushes to main, never in "
     "certification"),
)


class CertificationError(RuntimeError):
    """A certificate could not be built or does not describe this tree."""


# ---------------------------------------------------------------------------
# enumeration and hashing
# ---------------------------------------------------------------------------
def repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """The repository root, found by walking up to the directory holding .git."""
    here = (start or pathlib.Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise CertificationError(
        f"no repository root above {here}: expected a directory holding both "
        f".git and pyproject.toml"
    )


def _excluded(path: pathlib.Path) -> bool:
    return bool(EXCLUDED_DIR_PARTS.intersection(path.parts)) or (
        path.suffix in EXCLUDED_SUFFIXES
    )


def enumerate_area(root: pathlib.Path, area: ScopeArea) -> list[str]:
    """Repository-relative POSIX paths for one area, in canonical order.

    Refuses a symlink rather than following it: what a symlink points at is not
    recorded by a digest of the link, and following one could reach outside the
    tree entirely.
    """
    found: set[str] = set()
    for pattern in area.patterns:
        for path in root.glob(pattern):
            if not path.is_file() or _excluded(path.relative_to(root)):
                continue
            if path.is_symlink():
                raise CertificationError(
                    f"{path.relative_to(root).as_posix()} is a symlink and is in "
                    f"certified scope. A digest of a link does not record what it "
                    f"points at, so this is refused rather than resolved"
                )
            found.add(path.relative_to(root).as_posix())
    return sorted(found, key=lambda text: text.encode("utf-8"))



# ---------------------------------------------------------------------------
# what the certified suites import (R-68)
# ---------------------------------------------------------------------------
#: The support modules under ``tests/`` are not a package: the suites import them by bare name,
#: which pytest makes work by putting their directory on ``sys.path``. So the closure below resolves
#: a bare module name against the files under ``tests/`` and nothing else -- an import of `engcore`
#: or `numpy` is not a test helper and is out of this area by decision.
HARNESS_SEEDS = ("tests/mutation_guards.py",)


def _tests_local_modules(root: pathlib.Path) -> dict[str, str]:
    return {
        path.stem: path.relative_to(root).as_posix()
        for path in sorted((root / "tests").rglob("*.py"))
        if not _excluded(path.relative_to(root))
    }


def _imported_names(path: pathlib.Path) -> set[str]:
    """Every top-level module name ``path`` imports, including imports inside a function.

    Static, and it says so: a helper reached only through ``importlib`` by a computed name is not
    found here. Nothing in the closure does that, and a check that reports what it measured is worth
    more than one that claims a reach it does not have.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_bytes().decode("utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module.split(".")[0])
    return found


def harness_import_closure(root: pathlib.Path) -> list[str]:
    """Every file under ``tests/`` the certified mutation evidence depends on, derived.

    R-68, finding 93: the harness area pinned the SUITES the harness runs and not the modules those
    suites import, so ``tests/hybrid_uq/hybrid_synthetic.py`` was read by ten certified targets and
    measured by nothing -- and the branch changed it by twelve lines without moving the certificate.
    The answer cannot be a longer list, because a hand-maintained list is what the finding is about.

    The seeds are the harness itself, every suite in its ``TARGETS``, and every ``target_test`` the V4
    mutation population names -- the two sets of suites a kill is a statement about. The closure is
    then taken over their ``tests/``-local imports, transitively.
    """
    import runpy  # noqa: PLC0415 - loaded here, as the population tool loads the same two files

    local = _tests_local_modules(root)
    seeds: set[str] = {name for name in HARNESS_SEEDS if (root / name).is_file()}
    harness = root / "tests" / "mutation_guards.py"
    if harness.is_file():
        namespace = runpy.run_path(str(harness), run_name="_harness_closure_probe")
        seeds.update(str(target).replace("\\", "/") for target in namespace.get("TARGETS", ()))
    population = root / "tests" / "mutation_population_v4.py"
    if population.is_file():
        namespace = runpy.run_path(str(population), run_name="_population_closure_probe")
        seeds.update(entry[4].split("::")[0] for entry in namespace.get("POPULATION_V4", ()))
        seeds.add("tests/mutation_population_v4.py")
    closure = {name for name in seeds if (root / name).is_file()}
    queue = sorted(closure)
    while queue:
        current = queue.pop()
        for name in _imported_names(root / current):
            relative = local.get(name)
            if relative is not None and relative not in closure:
                closure.add(relative)
                queue.append(relative)
    return sorted(closure, key=lambda text: text.encode("utf-8"))


def harness_pinning_problems(
    root: pathlib.Path, scope: Sequence[ScopeArea] | None = None
) -> list[str]:
    """Why a scope's HARNESS area does not cover what the certified suites actually read.

    Called from :func:`build_certificate` and :func:`verify_certificate`, so the derivation is part of
    what a certificate means and not only something a test checks.
    """
    areas = tuple(scope if scope is not None else SCOPE)
    pinned: set[str] = set()
    for area in areas:
        if area.classification in ("HARNESS", "CERTIFICATION_CONTROL"):
            pinned.update(enumerate_area(root, area))
    missing = [name for name in harness_import_closure(root) if name not in pinned]
    if not missing:
        return []
    return [
        f"the harness area does not pin {len(missing)} module(s) the certified suites import, so "
        f"'N/N killed' is a statement about bytes no certificate measures: " + ", ".join(missing)
    ]


# ---------------------------------------------------------------------------
# what decides a verdict's meaning (hostile review F2)
# ---------------------------------------------------------------------------
#: The modules where SUPPORTED, admissibility, evidence authority and isolation are decided. Their
#: static import closure inside ``src/engcore`` is what a certificate must cover; the closure is
#: DERIVED, so a module that a verdict starts depending on cannot be left outside scope by omission.
AUTHORITY_ROOTS: tuple[str, ...] = (
    "src/engcore/claims/verdict.py",
    "src/engcore/claims/assessment.py",
    "src/engcore/claims/adapters/nl.py",
    "src/engcore/credibility/evidence.py",
    "src/engcore/authority/**/*.py",
    "src/engcore/blindfold/**/*.py",
)

#: Packages that produce ANSWERS (a solved value, a domain model) rather than decide what an answer
#: is worth. Named, with the reason, rather than silently skipped; the closure never reaches them today.
#: BR-15: systems/ is listed file by file and subpackage by subpackage, because systems/** as a whole was
#: wrong once -- systems/twin_revision.py is an evidence-binding vocabulary, now pinned -- and a systems
#: module a certified module starts importing must be decided, not exempted by its directory.
#: systems/admissibility.py (the F6 mechanism) is deliberately NOT listed: no certified module imports it.
AUTHORITY_CLOSURE_EXEMPT: tuple[tuple[str, str], ...] = (
    ("src/engcore/domains/**", "domain models and solvers: answers, assured by their own suites and frozen pins"),
    ("src/engcore/systems/aerospace/**", "aerospace system packs composed of domain models: answers"),
    ("src/engcore/systems/electrothermal/**", "electrothermal system packs composed of domain models: answers"),
    ("src/engcore/systems/products/**", "product system packs composed of domain models: answers"),
    ("src/engcore/systems/assembly.py", "assembly topology and ownership declarations: product structure, not verdicts"),
    ("src/engcore/systems/multibody.py", "multibody model declarations: answers"),
    ("src/engcore/systems/topology.py", "component and connection topology of a system definition: product structure"),
)

#: Imports the static closure cannot follow: a computed module name, or a walk over a package. Each one in
#: the closure must be declared here with what it can reach and why that reach is acceptable; an
#: undeclared one is a closure problem (third review B1/B2), so a root that starts loading code by name
#: cannot widen what decides a verdict without saying so in the certification control plane.
DYNAMIC_REACH: tuple[tuple[str, str, str], ...] = (
    ("src/engcore/credibility/evidence.py", "src/engcore/domains/**",
     "_declared_models walks engcore.domains only -- where every ScientificModelDefinition is declared -- and "
     "refuses two different definitions under one (model_id, version), so a module cannot shadow a model"),
    ("src/engcore/claims/analysis/__init__.py", "src/engcore/claims/analysis/**",
     "lazy loader of its own submodules, all inside the verdict_authority area"),
    ("src/engcore/scientific/consensus.py", "src/engcore/domains/**",
     "route declarations are read from engcore.domains; a component identity 'py:<module>:<qualname>' is "
     "resolved as named by a declaration, and the declarations' trust registries are pinned in "
     "src/engcore/domains/__init__.py, which is not exempt"),
    ("src/engcore/scientific/results/thresholds.py", "src/engcore/domains/**",
     "threshold declarations are read from engcore.domains; their registry digest is pinned in "
     "src/engcore/domains/__init__.py, which is not exempt"),
    ("src/engcore/scientific/results/validation.py", "src/engcore/domains/**",
     "validation-level declarations are read from engcore.domains, as for thresholds"),
    ("src/engcore/scientific/independence_evidence.py", "src/engcore/domains/**",
     "a route component identity names its module; identities are pinned by the domain trust registries"),
    ("src/engcore/providers/catalog.py", "<external adapter distributions forge_*: the top-level providers/ tree>",
     "default_registry imports `<adapter>.descriptor` for the fixed KNOWN_ADAPTERS names only -- separately "
     "installed distributions, never src/engcore -- and registers one UNAVAILABLE when it cannot be imported. "
     "Adapter code is not certified by this certificate (BR-15 residual): a registered provider is a numerical "
     "executor whose records grant no evidence"),
    ("src/engcore/domainpacks/discovery.py", "<external entry points: nothing in this tree>",
     "discovers EXTERNAL domain packs (installed entry points, FORGE_DOMAIN_PACKS). The registry probe runs with "
     "FORGE_* scrubbed, so the pinned registry is the built-in one; an external pack is never certified by this "
     "certificate"),
)


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


#: Calls that load or run code by a name or a path the static closure cannot follow (fourth review).
_LOADER_CALLS = frozenset({
    "walk_packages", "iter_modules", "resolve_name", "spec_from_file_location", "spec_from_loader",
    "module_from_spec", "exec_module", "load_module", "run_module", "run_path", "entry_points", "load_entry_point",
})
#: Modules whose attributes are loaders: an alias of one, or getattr() on one, is a loader too.
_LOADER_MODULES = frozenset({"importlib", "importlib.util", "importlib.metadata", "pkgutil", "runpy"})


def dynamic_imports(path: pathlib.Path) -> list[int]:
    """Lines where ``path`` loads a module the static closure cannot name.

    ``import_module``/``__import__`` with anything but an absolute string literal; any call in
    :data:`_LOADER_CALLS`; the builtins ``exec``/``compile``/``eval``; ``getattr`` on a loader module; and
    any of these reached through an alias (``from importlib import import_module as load``). A literal
    absolute name is not dynamic: :func:`_engcore_imports` follows it.
    """
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    aliases: dict[str, str] = {}
    modules: set[str] = set()
    builtin_names = {"builtins", "__builtins__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module in _LOADER_MODULES or node.module == "builtins") and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _LOADER_MODULES:
                    modules.add(alias.asname or alias.name.split(".")[0])
                elif alias.name == "builtins":  # BR-15 confirmation review: `import builtins as b; b.exec(...)`
                    builtin_names.add(alias.asname or alias.name)
    modules |= builtin_names  # getattr(builtins, "exec") is a loader lookup like getattr(importlib, ...)
    lines: list[int] = []
    callees = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}

    def loader_name(node: ast.AST) -> bool:
        name = _call_name(node)
        name = aliases.get(name, name) if isinstance(node, ast.Name) else name
        return name in _LOADER_CALLS or name.endswith("import_module") or name == "__import__"

    for node in ast.walk(tree):
        # G0/A1 final review C1: a loader referenced anywhere but as the callee of a call (stored in a container, a
        # default argument, passed along) is called later under another name.
        if isinstance(node, (ast.Attribute, ast.Name)) and id(node) not in callees and loader_name(node):
            lines.append(node.lineno)
        # C1: importlib.__dict__["import_module"] is vars(importlib)["import_module"]
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
                and isinstance(node.value.value, ast.Name) and node.value.value.id in modules):
            lines.append(node.lineno)
        # A loader bound to another name (load = importlib.import_module) is a loader wherever it is later called.
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, (ast.Attribute, ast.Name)):
            bound = _call_name(node.value)
            bound = aliases.get(bound, bound) if isinstance(node.value, ast.Name) else bound
            if bound in _LOADER_CALLS or bound.endswith("import_module") or bound == "__import__":
                lines.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        name = aliases.get(name, name) if isinstance(node.func, ast.Name) else name
        literal = (bool(node.args) and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                   and not node.args[0].value.startswith("."))
        if name in _LOADER_CALLS:
            lines.append(node.lineno)
        elif name.endswith("import_module") or name == "__import__":
            # C1: __import__("engcore", fromlist=[...]) or with a level loads names the static closure never follows
            if not literal or (name == "__import__" and (len(node.args) > 1 or node.keywords)):
                lines.append(node.lineno)
        elif isinstance(node.func, ast.Name) and name in ("exec", "compile", "eval"):
            lines.append(node.lineno)
        elif (isinstance(node.func, ast.Attribute) and name in ("exec", "compile", "eval")
              and isinstance(node.func.value, ast.Name) and node.func.value.id in builtin_names):
            lines.append(node.lineno)  # BR-15 review: builtins.exec(...) is exec(...)
        elif name == "getattr" and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in modules:
            lines.append(node.lineno)
        elif (name == "getattr" and node.args and isinstance(node.args[0], ast.Call)
              and (_call_name(node.args[0].func) == "__import__" or _call_name(node.args[0].func).endswith("import_module"))):
            lines.append(node.lineno)  # BR-15 review: getattr(__import__("importlib"), "import_module")
        elif (isinstance(node.func, ast.Subscript) and isinstance(node.func.value, ast.Call)
              and _call_name(node.func.value.func) == "vars" and node.func.value.args
              and isinstance(node.func.value.args[0], ast.Name) and node.func.value.args[0].id in modules):
            lines.append(node.lineno)  # BR-15 confirmation review: vars(importlib)["import_module"](name)
    return sorted(set(lines))


def _spelled_on_disk(src: pathlib.Path, candidate: pathlib.Path) -> bool:
    """``candidate`` exists under ``src`` with exactly this spelling (BR-15).

    On a case-insensitive filesystem ``results/Uncertainty.py`` "is a file" when ``results/uncertainty.py``
    is, so ``from .results import Uncertainty`` -- a symbol -- named a module that does not exist, and
    which spelling the closure kept depended on set order: the same tree verified or failed by hash seed.
    """
    current = src
    for part in candidate.relative_to(src).parts:
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return False
        current = current / part
    return True


def _engcore_module_file(src: pathlib.Path, module: str) -> pathlib.Path | None:
    base = src.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file() and _spelled_on_disk(src, candidate):
            return candidate
    return None


def _engcore_imports(src: pathlib.Path, path: pathlib.Path) -> set[str]:
    """Every ``engcore`` module ``path`` names, absolute or relative, including imports inside functions."""
    relative = path.relative_to(src).with_suffix("")
    package = list(relative.parts[:-1])
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_bytes().decode("utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names if alias.name != "*")
            star_package = src.joinpath(*module.split("."))
            if any(alias.name == "*" for alias in node.names) and (star_package / "__init__.py").is_file():
                # BR-15 review: `from pkg import *` imports whatever pkg.__all__ names, submodules included;
                # every direct submodule is taken as reached rather than reading __all__.
                found.update(f"{module}.{child.stem if child.suffix else child.name}" for child in sorted(star_package.iterdir())
                             if (child.suffix == ".py" and child.name != "__init__.py") or (child / "__init__.py").is_file())
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            # importlib.import_module("engcore.x") is an import with a literal name: followed like one.
            name = _call_name(node.func)
            if name.endswith("import_module") or name == "__import__":
                found.add(node.args[0].value)
    return {name for name in found if name == "engcore" or name.startswith("engcore.")}


def authority_import_closure(root: pathlib.Path, roots: Sequence[str] | None = None) -> list[str]:
    """The source files the verdict/authority roots reach by static import, transitively.

    Static, and it says so: a module reached only through ``importlib`` with a computed name is not
    found, exactly as for :func:`harness_import_closure`. Each package ``__init__`` on the way to an
    imported module is included, because importing a submodule executes it.
    """
    src = root / "src"
    if not (src / "engcore").is_dir():
        return []
    patterns = AUTHORITY_ROOTS if roots is None else tuple(roots)
    queue = [path for pattern in patterns for path in sorted(root.glob(pattern)) if path.is_file()]
    seen: set[pathlib.Path] = set()
    while queue:
        current = queue.pop()
        if current in seen or _excluded(current.relative_to(root)):
            continue
        seen.add(current)
        for module in _engcore_imports(src, current):
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                target = _engcore_module_file(src, ".".join(parts[:length]))
                if target is not None and target not in seen:
                    queue.append(target)
    return sorted((path.relative_to(root).as_posix() for path in seen), key=lambda text: text.encode("utf-8"))


def authority_closure_problems(root: pathlib.Path, scope: Sequence[ScopeArea] | None = None) -> list[str]:
    """Why ``scope`` does not cover everything the verdict and authority roots import."""
    areas = tuple(scope if scope is not None else SCOPE)
    pinned: set[str] = set()
    for area in areas:
        pinned.update(enumerate_area(root, area))
    closure = authority_import_closure(root)
    missing = [name for name in closure if name not in pinned and not _closure_exempt(name)]
    problems: list[str] = []
    if missing:
        problems.append(
            f"{len(missing)} module(s) the verdict/authority roots import are outside every certified area, so a "
            f"change to them could change what SUPPORTED means without moving the certificate: " + ", ".join(missing)
        )
    declared = {file: reach for file, reach, _ in DYNAMIC_REACH}
    for name in closure:
        lines = dynamic_imports(root / name)
        if lines and name not in declared:
            problems.append(
                f"{name} loads modules by computed name or package walk (line(s) {lines}) and DYNAMIC_REACH does "
                f"not declare what it can reach; the static closure cannot see past it"
            )
    for file, reach, _ in DYNAMIC_REACH:
        if not (root / file).is_file():
            continue
        reached = [str(p.relative_to(root).as_posix()) for p in sorted(root.glob(reach)) if p.is_file() and p.suffix == ".py"]
        uncovered = [n for n in reached if n not in pinned and not _closure_exempt(n) and not _excluded(pathlib.PurePosixPath(n))]
        if uncovered:
            problems.append(f"{file} can reach {len(uncovered)} module(s) by name outside every certified area: "
                            + ", ".join(uncovered[:10]))
    return problems


def _closure_exempt(name: str) -> bool:
    """An exempt package's own ``__init__`` is never exempt: importing any submodule runs it (third review B2)."""
    for pattern, _ in AUTHORITY_CLOSURE_EXEMPT:
        base = pattern.rstrip("*/")
        if name == base + "/__init__.py":
            return False
        if pathlib.PurePosixPath(name).match(pattern) or name.startswith(base + "/"):
            return True
    return False


# ---------------------------------------------------------------------------
# what every certified module imports (BR-15)
# ---------------------------------------------------------------------------
#: The F2 closure starts at the verdict and authority roots. A certified module outside that closure is
#: still certified, and it was importing uncertified code that decides what its result means: the stop
#: review's Arbiter decisions came from sria/campaign/events.py, a falsification verdict's claim identity
#: from sria/decision/hypotheses.py. So the closure of EVERY certified product module (the CORE_CERTIFIED
#: and RUNTIME_SUPPORT areas under src/, and every pinned package __init__ above them) must be pinned,
#: exempt as an answer producer, or a declared EDGE here: (certified importer, imported package, why that
#: importer's use of it cannot grant authority). An edge excuses that importer only; a new certified module
#: importing the same package is refused until it is decided. A declared edge never excuses a verdict or
#: authority root: authority_closure_problems does not read this table.
CERTIFIED_DEPENDENCY_EXCLUSIONS: tuple[tuple[str, str, str], ...] = (
    ("src/engcore/claims/design_memory.py", "src/engcore/design/**",
     "design-search memory: design_memory anchors a search history whose records are classified "
     "search_history_not_evidence into the campaign event chain; no evidence, belief, verdict or stop path reads it. "
     "Residual: DesignHistory's own chain check is not certified, so a truncated search memory is not a certified "
     "refusal"),
)


def _matches(name: str, pattern: str) -> bool:
    base = pattern.rstrip("*/")
    return name == pattern or name == base or name.startswith(base + "/") or pathlib.PurePosixPath(name).match(pattern)


def _dependency_excluded(name: str, importer: str | None = None) -> bool:
    """``name`` is a declared non-authoritative dependency -- of ``importer`` when one is given."""
    return any(_matches(name, imported) and (importer is None or _matches(importer, owner))
               for owner, imported, _ in CERTIFIED_DEPENDENCY_EXCLUSIONS)


#: Area classifications whose files are product code a certificate vouches for. The control plane's
#: own files are pinned for what they verify, not run as part of a certified result -- except a package
#: __init__, which runs whenever anything below it is imported, so every pinned one is a seed too.
_DEPENDENCY_SEED_CLASSES = frozenset({"CORE_CERTIFIED", "RUNTIME_SUPPORT"})


def certified_dependency_problems(root: pathlib.Path, scope: Sequence[ScopeArea] | None = None) -> list[str]:
    """Why ``scope`` does not cover everything its certified modules import (BR-15).

    Static, like every closure here; a computed-name load in a certified module must be declared in
    DYNAMIC_REACH. Traversal stops at a pinned file (itself a seed or control-plane code) and at a declared
    edge, and continues THROUGH exempt answer modules and uncovered ones, so an uncertified module behind an
    exempt one is still reported, and the report names everything behind a gap.
    """
    areas = tuple(scope if scope is not None else SCOPE)
    src = root / "src"
    if not (src / "engcore").is_dir():
        return []
    pinned: set[str] = set()
    seeds: set[str] = set()
    for area in areas:
        files = enumerate_area(root, area)
        pinned.update(files)
        seeds.update(name for name in files if name.startswith("src/engcore/") and name.endswith(".py")
                     and (area.classification in _DEPENDENCY_SEED_CLASSES or name.endswith("/__init__.py")))
    missing: set[str] = set()
    seen: set[str] = set()
    queue = sorted(seeds)
    reach = {file: pattern for file, pattern, _ in DYNAMIC_REACH if pattern.startswith("src/engcore/")}
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in reach:   # G0/A1 final review C2: a declared computed-name load reaches every file it names
            for target in sorted((root / "src" / "engcore").rglob("*.py")):
                name = target.relative_to(root).as_posix()
                if _excluded(target.relative_to(root)) or not _matches(name, reach[current]):
                    continue
                if name in pinned or _dependency_excluded(name, current):
                    continue
                if not _closure_exempt(name):
                    missing.add(name)
                if name not in seen:
                    queue.append(name)
        for module in _engcore_imports(src, root / current):
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                target = _engcore_module_file(src, ".".join(parts[:length]))
                if target is None or _excluded(target.relative_to(root)):
                    continue
                name = target.relative_to(root).as_posix()
                if name in pinned or _dependency_excluded(name, current):
                    continue
                if not _closure_exempt(name):
                    missing.add(name)
                if name not in seen:
                    queue.append(name)
    problems: list[str] = []
    if missing:
        names = sorted(missing, key=lambda text: text.encode("utf-8"))
        problems.append(
            f"{len(names)} module(s) a certified module imports are outside every certified area and are neither "
            f"exempt nor a declared non-authoritative dependency of their importer, so a change to them could "
            f"change a certified result without moving the certificate: " + ", ".join(names)
        )
    declared = {file for file, _, _ in DYNAMIC_REACH}
    for name in sorted(seen):   # C2: every module the closure walks through, not only the seeds
        lines = dynamic_imports(root / name)
        if lines and name not in declared:
            role = "certified module" if name in seeds else "module on a certified module's import path"
            problems.append(
                f"{role} {name} loads modules by computed name or package walk (line(s) {lines}) and "
                f"DYNAMIC_REACH does not declare what it can reach"
            )
    return problems


#: G0/A1 final review C3: what may be TRACKED under src/engcore. CPython prefers an extension module (.so/.pyd) to the
#: .py beside it and runs an unchecked-hash .pyc from __pycache__ without reading the source, so a tracked compiled
#: file could replace pinned source while every digest still matches.
SOURCE_FORMS = (".py", "/py.typed")


def source_form_problems(root: pathlib.Path) -> list[str]:
    """Tracked files under src/engcore that are not Python source (or the py.typed marker)."""
    try:
        tracked = _git(root, "ls-files", "-z", "--", "src/engcore", strip=False).split("\0")
    except Exception as exc:  # noqa: BLE001 - fail closed: without the index nothing is known about the tree
        return [f"cannot list the tracked files under src/engcore: {exc}"]
    bad = sorted(name for name in tracked if name and not name.endswith(SOURCE_FORMS))
    if not bad:
        return []
    return [f"{len(bad)} tracked file(s) under src/engcore are not Python source; an import could run them instead of "
            f"the pinned .py: " + ", ".join(bad)]


# ---------------------------------------------------------------------------
# the production capability registry (hostile review F2, third pass B3)
# ---------------------------------------------------------------------------
#: assess_claim and verify_assessment judge every claim against the production registry: routes and their
#: activation, input roles, required overrides, refinement defaults, perturbable inputs. That registry is
#: assembled in src/engcore/product and the pack registries -- ~100 modules that produce answers and are
#: out of scope. Rather than certify them, a certificate pins what the verdict reads from them: the
#: registry's own declaration digest; for every executor, case builder and oracle provider its name AND
#: the SHA-256 of the source file that defines it (fourth review: a name alone is not code); and the source
#: digest of every domain module that declares a ScientificModelDefinition (validity domains, exclusions).
#: Fifth review: the code those functions reach builds evidence too (product/battery.py assembles the
#: CredibilityEvidenceReport itself), so the static first-party import closure of every executor, case builder
#: and oracle provider is pinned file by file -- stopping only at AUTHORITY_CLOSURE_EXEMPT (domain models and
#: solvers, system compositions: answers, assured by their own suites and frozen pins). A module reached only
#: by a computed name is not seen by this closure, as for the authority closure.
_REGISTRY_PROBE = r"""
import hashlib, importlib, inspect, json, pathlib, pkgutil, sys
src = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(src))
import engcore
if pathlib.Path(engcore.__file__).resolve().parent != src / "engcore":
    raise SystemExit("engcore was imported from " + engcore.__file__ + ", not from the tree being certified")
from engcore.product.capabilities import production_registry
from engcore.scientific.models.definition import ScientificModelDefinition

def source(path):
    path = pathlib.Path(path).resolve()
    try:
        rel = path.relative_to(src.parent).as_posix()
    except ValueError:
        raise SystemExit("code the verdict reads is defined outside the tree being certified: " + str(path))
    return {"source": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

def ident(f):
    if f is None:
        return None
    name = getattr(f, "__module__", "?") + ":" + getattr(f, "__qualname__", type(f).__qualname__)
    try:
        where = inspect.getsourcefile(f)
    except TypeError:
        where = None
    if where is None:
        raise SystemExit("cannot locate the source of " + name)
    return {"name": name, **source(where)}

models = {}
for found in pkgutil.walk_packages(importlib.import_module("engcore.domains").__path__, "engcore.domains."):
    module = importlib.import_module(found.name)  # an import failure fails the probe, never drops a model
    if any(isinstance(value, ScientificModelDefinition) for value in vars(module).values()):
        models[found.name] = source(module.__file__)

registry = production_registry()
print(json.dumps({
    "digest": registry.digest,
    "capabilities": {
        d.capability_id: {
            "digest": d.digest,
            "executor": ident(d.executor),
            "case_builder": ident(d.case_builder),
            "oracle_providers": {r.route_id: ident(getattr(r, "oracle_provider", None)) for r in d.routes},
        }
        for d in registry.declarations
    },
    "model_definition_modules": models,
}, sort_keys=True))
"""

#: The file whose presence says this tree has a production registry to pin.
REGISTRY_ENTRY = "src/engcore/product/capabilities.py"


def production_registry_identity(root: pathlib.Path) -> dict[str, Any] | None:
    """The production registry's declaration digest and code identities, read from the tree at ``root``.

    ``None`` for a tree with no production registry (a synthetic test repository). Runs in a subprocess
    so the tree's ``engcore`` -- and only that one -- is imported; any failure is a CertificationError.
    """
    if not (root / REGISTRY_ENTRY).is_file():
        if (root / "src" / "engcore" / "claims" / "assessment.py").is_file():
            # A tree that assesses claims has a registry; a moved or renamed entry must not drop the pin silently.
            raise CertificationError(f"{REGISTRY_ENTRY} is missing from a tree that assesses claims; the production "
                                     "registry cannot be pinned")
        return None
    # Fourth review: nothing from the environment steers the probe -- no PYTHON*/FORGE*/user-site/cwd entries
    # (-E -s -P, a scratch working directory), and only the tree's own engcore is accepted.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PYTHON", "FORGE"))}
    import tempfile  # noqa: PLC0415 - only the probe needs a scratch directory

    with tempfile.TemporaryDirectory(prefix="forge-registry-probe-") as scratch:
        run = subprocess.run([sys.executable, "-E", "-s", "-P", "-c", _REGISTRY_PROBE, str(root / "src")], cwd=scratch,
                             env=env, capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        raise CertificationError("the production registry could not be read from the tree: "
                                 + (run.stderr.strip().splitlines() or ["no output"])[-1])
    identity = json.loads(run.stdout.strip().splitlines()[-1])
    identity["evidence_code"] = evidence_code_digests(root, identity)
    return identity


def evidence_code_digests(root: pathlib.Path, identity: Mapping[str, Any]) -> dict[str, str]:
    """SHA-256 of the first-party code the registry's executors, case builders and oracle providers reach.

    The static import closure (absolute, relative and literal ``import_module`` names, function-level imports
    included) from each defining file, walked THROUGH the exempt answer packages, and EVERY file reached is
    pinned: an "answers" module (a solver, a matrix assembler) can decide whether a level is earned without
    naming an evidence type. A computed-name load anywhere in the closure must be declared in DYNAMIC_REACH,
    or the registry cannot be pinned.
    """
    src = root / "src"
    seeds: set[str] = set()
    for declaration in identity.get("capabilities", {}).values():
        for item in (declaration.get("executor"), declaration.get("case_builder"),
                     *dict(declaration.get("oracle_providers") or {}).values()):
            if isinstance(item, Mapping) and item.get("source"):
                seeds.add(str(item["source"]))
    queue = [root / name for name in sorted(seeds)]
    seen: set[pathlib.Path] = set()
    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        for module in _engcore_imports(src, current):
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                target = _engcore_module_file(src, ".".join(parts[:length]))
                if target is not None and target not in seen:
                    queue.append(target)
    declared = {file for file, _, _ in DYNAMIC_REACH}
    undeclared = sorted(rel for rel in (p.relative_to(root).as_posix() for p in seen)
                        if rel not in declared and dynamic_imports(root / rel))
    if undeclared:
        raise CertificationError("code the production registry's executors reach loads modules by computed name "
                                 f"without a DYNAMIC_REACH declaration: {undeclared}")
    # Seventh review: pinning only files that NAME an evidence type left the helpers that decide an award (dc/mna.py
    # feeding dc/validation.py's residual check) unpinned. Everything the production executors reach is pinned.
    pinned = list(seen)
    return {path.relative_to(root).as_posix(): file_digest(path)
            for path in sorted(pinned, key=lambda p: p.relative_to(root).as_posix().encode("utf-8"))}


def registry_problems(root: pathlib.Path, certificate: Mapping[str, Any]) -> list[str]:
    """Why the tree's production registry is not the one the certificate pinned."""
    try:
        actual = production_registry_identity(root)
    except CertificationError as exc:
        return [str(exc)]
    stored = (certificate.get("manifest") or {}).get("production_registry")
    if actual is None:
        return [] if stored is None else ["the certificate pins a production registry this tree does not have"]
    if stored is None:
        return ["the certificate does not pin the production registry the verdict reads; it predates the pin"]
    if stored == actual:
        return []
    changed = sorted(
        cid for cid in set(stored.get("capabilities", {})) | set(actual.get("capabilities", {}))
        if stored.get("capabilities", {}).get(cid) != actual.get("capabilities", {}).get(cid)
    )
    stored_code, actual_code = dict(stored.get("evidence_code") or {}), dict(actual.get("evidence_code") or {})
    moved_code = sorted(name for name in set(stored_code) | set(actual_code) if stored_code.get(name) != actual_code.get(name))
    return [f"the production registry changed since certification (capabilities {changed}, evidence code "
            f"{moved_code[:10]}): what a claim is judged against moved without moving the certificate"]


def file_digest(path: pathlib.Path) -> str:
    """SHA-256 over the file's exact bytes. Nothing is decoded or normalized."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def area_digest(entries: Mapping[str, str]) -> str:
    """SHA-256 over ``path + NUL + file digest`` for each entry, in path order."""
    accumulator = hashlib.sha256()
    for relative in sorted(entries, key=lambda text: text.encode("utf-8")):
        accumulator.update(relative.encode("utf-8"))
        accumulator.update(b"\x00")
        accumulator.update(bytes.fromhex(entries[relative]))
    return accumulator.hexdigest()


def aggregate_digest(areas: Mapping[str, str]) -> str:
    """SHA-256 over ``area name + NUL + area digest``, areas in name order."""
    accumulator = hashlib.sha256()
    for name in sorted(areas, key=lambda text: text.encode("utf-8")):
        accumulator.update(name.encode("utf-8"))
        accumulator.update(b"\x00")
        accumulator.update(bytes.fromhex(areas[name]))
    return accumulator.hexdigest()


def build_manifest(
    root: pathlib.Path, scope: Sequence[ScopeArea] | None = None
) -> dict[str, Any]:
    """The full manifest for ``scope`` as it stands in the tree at ``root``.

    ``scope`` resolves to the module's :data:`SCOPE` at call time rather than
    through a default argument, so the table can be substituted — which is what
    the drift tests do to build a synthetic repository rather than experimenting
    on the checkout.
    """
    areas: dict[str, Any] = {}
    for area in SCOPE if scope is None else scope:
        relatives = enumerate_area(root, area)
        if not relatives:
            raise CertificationError(
                f"scope area {area.name!r} matched no files under {root}; an "
                f"area that certifies nothing is a silent hole in the scope"
            )
        _require_file_reasons(area, relatives)
        files = {rel: file_digest(root / rel) for rel in relatives}
        areas[area.name] = {
            "classification": area.classification,
            "patterns": list(area.patterns),
            "why": area.why,
            "file_count": len(files),
            "digest": area_digest(files),
            "files": files,
        }
        if area.file_reasons:
            areas[area.name]["file_reasons"] = dict(area.file_reasons)
    # R-68 (finding 93): a manifest is refused rather than written over a harness area that does not
    # cover what its own suites import. Here, not only in a test, because the claim a certificate
    # makes about the mutation rounds is a claim about these bytes.
    pinning = harness_pinning_problems(root, SCOPE if scope is None else scope)
    # F2: and refused over a scope that leaves part of what decides a verdict's meaning unmeasured.
    pinning += authority_closure_problems(root, SCOPE if scope is None else scope)
    # BR-15: and over a scope whose certified modules import code that decides their meaning unmeasured.
    pinning += certified_dependency_problems(root, SCOPE if scope is None else scope)
    pinning += source_form_problems(root)
    if pinning:
        raise CertificationError("; ".join(pinning))
    manifest = {
        "areas": areas,
        "file_count": sum(a["file_count"] for a in areas.values()),
        "aggregate_digest": aggregate_digest(
            {name: a["digest"] for name, a in areas.items()}
        ),
    }
    registry = production_registry_identity(root)
    if registry is not None:
        manifest["production_registry"] = registry
    return manifest


def _require_file_reasons(area: ScopeArea, relatives: Sequence[str]) -> None:
    """Refuse an area whose per-file reasons and enumerated files disagree."""
    if not area.file_reasons:
        return
    reasons = dict(area.file_reasons)
    if len(reasons) != len(area.file_reasons):
        raise CertificationError(
            f"scope area {area.name!r} gives two reasons for one file"
        )
    unexplained = sorted(set(relatives) - set(reasons))
    stale = sorted(set(reasons) - set(relatives))
    empty = sorted(path for path, why in reasons.items() if not why.strip())
    if unexplained or stale or empty:
        raise CertificationError(
            f"scope area {area.name!r} requires a reason for every file it "
            f"certifies: unexplained {unexplained}, reasons for files it does "
            f"not enumerate {stale}, empty reasons {empty}. A file in the "
            f"control plane without a reason is a file nobody decided to trust"
        )


def scope_table(scope: Sequence[ScopeArea] | None = None) -> dict[str, dict[str, Any]]:
    """What decides coverage, per area: its classification and its patterns.

    Reasons are deliberately not part of it. A reason is prose about coverage;
    the patterns ARE the coverage.
    """
    return {
        area.name: {
            "classification": area.classification,
            "patterns": list(area.patterns),
        }
        for area in (SCOPE if scope is None else scope)
    }


def scope_problems(
    certificate: Mapping[str, Any], scope: Sequence[ScopeArea] | None = None
) -> list[str]:
    """Why a stored certificate was not written under ``scope`` (default :data:`SCOPE`).

    A certificate is verified against the patterns it recorded, which is right
    for reading an old certificate and wrong for trusting one: a certificate
    written before an area existed verifies byte-for-byte while saying nothing
    about that area. This names the difference so a verifier can refuse it.
    Both the manifest and ``scope.in`` are compared, because either alone can
    be edited to agree with the table while the other does not.
    """
    expected = scope_table(scope)
    problems: list[str] = []
    manifest_areas = (certificate.get("manifest") or {}).get("areas") or {}
    recorded = {
        name: {
            "classification": stored.get("classification"),
            "patterns": list(stored.get("patterns") or ()),
        }
        for name, stored in manifest_areas.items()
    }
    declared = {
        str(entry.get("area")): {
            "classification": entry.get("classification"),
            "patterns": list(entry.get("patterns") or ()),
        }
        for entry in ((certificate.get("scope") or {}).get("in") or ())
    }
    for label, actual in (("manifest.areas", recorded), ("scope.in", declared)):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            name for name in set(expected) & set(actual)
            if expected[name] != actual[name]
        )
        if missing or extra or changed:
            problems.append(
                f"certificate {label} was not written under the current scope: "
                f"missing areas {missing}, areas no longer in scope {extra}, "
                f"areas whose classification or patterns differ {changed}"
            )
    return problems


def v1_compatible_core_digest(root: pathlib.Path) -> str:
    """The V1 algorithm, reproduced exactly, over ``src/engcore/scientific``.

    Paths relative to *that root* rather than to the repository, which is the
    one difference from :func:`area_digest`. Recorded so continuity with V1 is
    a number a reader can check rather than a claim in prose.
    """
    base = root / "src" / "engcore" / "scientific"
    accumulator = hashlib.sha256()
    for path in sorted(
        p for p in base.rglob("*.py") if "__pycache__" not in p.parts
    ):
        accumulator.update(path.relative_to(base).as_posix().encode())
        accumulator.update(b"\x00")
        accumulator.update(hashlib.sha256(path.read_bytes()).digest())
    return accumulator.hexdigest()


# ---------------------------------------------------------------------------
# repository identity
# ---------------------------------------------------------------------------
def _git(root: pathlib.Path, *args: str, strip: bool = True) -> str:
    """Run git and return its stdout.

    ``strip`` is a parameter rather than always-on because ``status
    --porcelain`` encodes the index and worktree states in the **first two
    columns**, and one of them is very often a space. Stripping the output
    silently removes that space from the first line only, and every path parsed
    from it then loses its first character — which is how this function spent
    its first draft reporting an uncommitted file as ``ools/...``.
    """
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise CertificationError(f"git {' '.join(args)} failed: {exc}") from exc
    if done.returncode != 0:
        raise CertificationError(
            f"git {' '.join(args)} failed: {done.stderr.strip()}"
        )
    return done.stdout.strip() if strip else done.stdout


def _porcelain_paths(output: str) -> list[str]:
    """The paths in ``git status --porcelain`` output, columns intact.

    A rename is reported as ``R  old -> new``; the new name is the one that
    exists in the tree, so that is the one recorded.
    """
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip().strip('"'))
    return sorted(paths)


def repository_identity(root: pathlib.Path) -> dict[str, Any]:
    """The commit a certificate is about, and whether the tree was clean."""
    dirty = _git(root, "status", "--porcelain", strip=False)
    return {
        "commit": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not dirty.strip(),
        "dirty_paths": _porcelain_paths(dirty),
    }


def environment() -> dict[str, Any]:
    """Facts about where this ran. Metadata: no comparison depends on them."""
    packages: dict[str, str] = {}
    for name in ("numpy", "scipy", "pint", "pytest"):
        try:
            module = __import__(name)
        except Exception:  # pragma: no cover - a missing package is a fact too
            packages[name] = "absent"
        else:
            packages[name] = getattr(module, "__version__", "unknown")
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def build_certificate(
    root: pathlib.Path,
    *,
    allow_dirty: bool = False,
    assurance: Mapping[str, Any] | None = None,
    certification_id: str = "FORGE-CORE-V2",
    notes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a certificate for the tree at ``root``.

    Refuses a dirty tree unless ``allow_dirty``: a certificate names a commit,
    and one built from uncommitted edits describes a tree nobody else can check
    out. The escape hatch exists for diagnosis and marks what it produces.
    """
    identity = repository_identity(root)
    if not identity["clean"] and not allow_dirty:
        raise CertificationError(
            "refusing to certify a dirty tree: "
            f"{len(identity['dirty_paths'])} uncommitted path(s), first "
            f"{identity['dirty_paths'][:3]}. A certificate names a commit, and "
            f"one built from uncommitted edits describes a tree nobody can "
            f"check out. Commit first, or pass --allow-dirty for a diagnostic "
            f"certificate that says so in its own diagnostic field"
        )
    manifest = build_manifest(root)
    return {
        "schema": CERTIFICATE_SCHEMA,
        "certification_id": certification_id,
        "diagnostic": not identity["clean"],
        "generator": {"tool": TOOL_ID, "version": TOOL_VERSION},
        "repository": identity,
        "environment": environment(),
        "scope": {
            "in": [
                {
                    "area": area.name,
                    "classification": area.classification,
                    "patterns": list(area.patterns),
                    "why": area.why,
                    **(
                        {"file_reasons": dict(area.file_reasons)}
                        if area.file_reasons
                        else {}
                    ),
                }
                for area in SCOPE
            ],
            "out": [{"area": name, "why": why} for name, why in OUT_OF_SCOPE],
        },
        "digest_algorithm": {
            "hash": "sha256",
            "per_file": "sha256(exact file bytes)",
            "per_area": "sha256( path_utf8 + 0x00 + file_digest_bytes, in path order )",
            "aggregate": "sha256( area_name_utf8 + 0x00 + area_digest_bytes, in name order )",
            "path_form": "repository-relative, POSIX separators",
            "ordering": "sorted by UTF-8 encoded path bytes",
            "line_endings": "not normalized; exact bytes are hashed",
            "excluded": ["**/__pycache__/**", "*.pyc", "*.pyo"],
            "symlinks": "refused in scope",
            "implemented_by": TOOL_ID,
        },
        "manifest": manifest,
        "v1_continuity": {
            "v1_certificate": "certification/current_core_v1.json",
            "v1_algorithm_recovered": True,
            "v1_algorithm_source": (
                "certification/current_core_v1.json -> "
                "verification.how_to_reproduce_the_certified_tree"
            ),
            "v1_core_digest_at_its_own_commit": (
                "82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507"
            ),
            "v1_compatible_core_digest_now": v1_compatible_core_digest(root),
            "note": (
                "V2 area digests use repository-relative paths where V1 used "
                "paths relative to src/engcore/scientific, so the two are not "
                "comparable by construction. The field above recomputes the core "
                "tree the V1 way against this tree, so the continuity between "
                "the two certificates is a number rather than a claim"
            ),
        },
        "assurance": dict(assurance or {}),
        "notes": dict(notes or {}),
    }


# ---------------------------------------------------------------------------
# verify  --  reads the stored certificate; never rebuilds expectations
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AreaDrift:
    """What moved in one area, by path."""

    area: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    expected_digest: str
    actual_digest: str

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.modified) and (
            self.expected_digest == self.actual_digest
        )


@dataclass(frozen=True)
class VerificationResult:
    """Whether the tree is the certified tree, and if not, precisely how not."""

    ok: bool
    areas: tuple[AreaDrift, ...]
    expected_aggregate: str
    actual_aggregate: str
    commit_expected: str
    commit_actual: str
    commit_matches: bool
    clean_tree: bool
    problems: tuple[str, ...]

    def render(self) -> str:
        lines: list[str] = []
        for drift in self.areas:
            if drift.clean:
                continue
            lines.append(f"AREA {drift.area}")
            for label, paths in (
                ("ADDED", drift.added),
                ("REMOVED", drift.removed),
                ("MODIFIED", drift.modified),
            ):
                for path in paths:
                    lines.append(f"  {label}: {path}")
            if drift.expected_digest != drift.actual_digest:
                lines.append(f"  expected area digest: {drift.expected_digest}")
                lines.append(f"  actual area digest:   {drift.actual_digest}")
        for problem in self.problems:
            lines.append(f"PROBLEM: {problem}")
        if self.expected_aggregate != self.actual_aggregate:
            lines.append(f"expected aggregate: {self.expected_aggregate}")
            lines.append(f"actual aggregate:   {self.actual_aggregate}")
        if not lines:
            lines.append("certificate matches the tree")
        return "\n".join(lines)


def verify_certificate(
    root: pathlib.Path,
    certificate: Mapping[str, Any],
    *,
    require_clean: bool = True,
    require_commit: bool = True,
    require_current_scope: bool = True,
) -> VerificationResult:
    """Compare the tree at ``root`` against a **stored** certificate.

    Every expected value is read from ``certificate``. Nothing here calls
    :func:`build_certificate`, and no expectation is recomputed from the tree
    being checked — a verifier that regenerated its own expectations would
    compare the tree to itself and pass for any tree at all.

    Files are enumerated from the certificate's recorded patterns rather than
    from :data:`SCOPE`, so a certificate written under an older scope is checked
    against the scope it was written under -- and, unless
    ``require_current_scope`` is false, then REFUSED for not being written under
    the current one. Byte agreement over an old scope is agreement about less
    than the verifier now certifies; that is a diagnosis, not a verification.
    The comparison is against the :data:`SCOPE` table, never against the tree.
    """
    problems: list[str] = []
    schema = str(certificate.get("schema", ""))
    if schema != CERTIFICATE_SCHEMA:
        problems.append(
            f"certificate schema is {schema!r} and this verifier implements "
            f"{CERTIFICATE_SCHEMA!r}; refusing to compare fields that may not "
            f"mean the same thing"
        )
        return VerificationResult(
            ok=False, areas=(), expected_aggregate="", actual_aggregate="",
            commit_expected="", commit_actual="", commit_matches=False,
            clean_tree=False, problems=tuple(problems),
        )

    manifest = certificate.get("manifest") or {}
    stored_areas: Mapping[str, Any] = manifest.get("areas") or {}
    if not stored_areas:
        problems.append("certificate carries no manifest areas")
    if require_current_scope:
        problems.extend(scope_problems(certificate))
        # F2: the current scope must still cover what the verdict and authority roots import.
        problems.extend(authority_closure_problems(root))
        # BR-15: and what every certified module imports.
        problems.extend(certified_dependency_problems(root))
        problems.extend(source_form_problems(root))
        # F2, third pass: and the production registry the verdict reads is the one certified.
        problems.extend(registry_problems(root, certificate))

    drifts: list[AreaDrift] = []
    actual_area_digests: dict[str, str] = {}
    for name, stored in sorted(stored_areas.items()):
        area = ScopeArea(
            name=name,
            classification=stored.get("classification", ""),
            patterns=tuple(stored.get("patterns") or ()),
            why="",
        )
        stored_files: Mapping[str, str] = stored.get("files") or {}
        try:
            present = enumerate_area(root, area)
        except CertificationError as exc:
            problems.append(str(exc))
            present = []
        actual_files = {rel: file_digest(root / rel) for rel in present}

        added = tuple(sorted(set(actual_files) - set(stored_files)))
        removed = tuple(sorted(set(stored_files) - set(actual_files)))
        modified = tuple(
            sorted(
                rel
                for rel in set(stored_files) & set(actual_files)
                if stored_files[rel] != actual_files[rel]
            )
        )
        actual = area_digest(actual_files)
        actual_area_digests[name] = actual
        drifts.append(
            AreaDrift(
                area=name,
                added=added,
                removed=removed,
                modified=modified,
                expected_digest=str(stored.get("digest", "")),
                actual_digest=actual,
            )
        )
        stored_count = stored.get("file_count")
        if stored_count is not None and stored_count != len(stored_files):
            problems.append(
                f"area {name!r} records file_count {stored_count} and lists "
                f"{len(stored_files)} files; the certificate disagrees with itself"
            )

    expected_aggregate = str(manifest.get("aggregate_digest", ""))
    actual_aggregate = aggregate_digest(actual_area_digests)

    repository = certificate.get("repository") or {}
    commit_expected = str(repository.get("commit", ""))
    try:
        identity = repository_identity(root)
        commit_actual = identity["commit"]
        clean_tree = bool(identity["clean"])
    except CertificationError as exc:  # pragma: no cover - no git available
        problems.append(str(exc))
        commit_actual, clean_tree = "", False

    commit_matches = bool(commit_expected) and commit_expected == commit_actual
    if require_commit and not commit_matches:
        problems.append(
            f"certificate names commit {commit_expected or '<none>'} and HEAD is "
            f"{commit_actual or '<unknown>'}"
        )
    if require_clean and not clean_tree:
        problems.append(
            "the working tree has uncommitted changes, so what is being verified "
            "is not any commit"
        )
    if certificate.get("diagnostic"):
        problems.append(
            "this certificate was built with --allow-dirty and is marked "
            "diagnostic; it does not certify a commit"
        )

    ok = (
        not problems
        and all(drift.clean for drift in drifts)
        and expected_aggregate == actual_aggregate
    )
    return VerificationResult(
        ok=ok,
        areas=tuple(drifts),
        expected_aggregate=expected_aggregate,
        actual_aggregate=actual_aggregate,
        commit_expected=commit_expected,
        commit_actual=commit_actual,
        commit_matches=commit_matches,
        clean_tree=clean_tree,
        problems=tuple(problems),
    )


def load_certificate(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_certificate(path: pathlib.Path, certificate: Mapping[str, Any]) -> None:
    """Write deterministically: sorted keys, two-space indent, LF, trailing LF."""
    payload = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build, verify or list the Core certificate.",
    )
    parser.add_argument("--build", action="store_true", help="write a certificate")
    parser.add_argument("--verify", action="store_true", help="check the tree against one")
    parser.add_argument("--manifest", action="store_true", help="print the manifest")
    parser.add_argument(
        "--certificate",
        default="certification/current_core_v2.json",
        help="path to the certificate (default: %(default)s)",
    )
    parser.add_argument("--assurance", help="JSON file of assurance results to embed")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--require-commit",
        action="store_true",
        help=(
            "also require HEAD to be the commit the certificate names. Off by "
            "default because a certificate is committed as a child of the "
            "commit whose tree it certifies, so HEAD is normally that child; "
            "the content comparison is unaffected, since the certificate file "
            "is outside certified scope"
        ),
    )
    parser.add_argument(
        "--any-scope",
        action="store_true",
        help=(
            "diagnose a certificate written under an older scope table without "
            "refusing it for that reason. Never used by CI: a certificate that "
            "only verifies with this flag does not certify the current scope"
        ),
    )
    args = parser.parse_args(argv)

    root = repo_root(pathlib.Path.cwd() / "x")
    certificate_path = root / args.certificate

    if args.manifest:
        print(json.dumps(build_manifest(root), indent=2, sort_keys=True))
        return 0

    if args.build:
        assurance = (
            json.loads((root / args.assurance).read_text(encoding="utf-8"))
            if args.assurance
            else None
        )
        certificate = build_certificate(
            root, allow_dirty=args.allow_dirty, assurance=assurance
        )
        write_certificate(certificate_path, certificate)
        print(f"wrote {args.certificate}")
        print(f"  files      {certificate['manifest']['file_count']}")
        print(f"  aggregate  {certificate['manifest']['aggregate_digest']}")
        print(f"  commit     {certificate['repository']['commit']}")
        return 0

    if args.verify:
        if not certificate_path.exists():
            print(f"no certificate at {args.certificate}", file=sys.stderr)
            return 2
        result = verify_certificate(
            root,
            load_certificate(certificate_path),
            require_clean=not args.allow_dirty,
            require_commit=args.require_commit,
            require_current_scope=not args.any_scope,
        )
        print(result.render())
        if not args.require_commit:
            relation = (
                "HEAD is the certified commit"
                if result.commit_matches
                else f"certified commit {result.commit_expected[:12]}, "
                     f"HEAD {result.commit_actual[:12]}"
            )
            print(f"commit: {relation}")
        print("OK" if result.ok else "FAILED")
        return 0 if result.ok else 1

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
