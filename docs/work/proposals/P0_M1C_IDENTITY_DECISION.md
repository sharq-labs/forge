# P0 M1C declaration decision — pending owner approval

Exact proposed patch: P0_M1C_REALIZATION_0_2.patch. APPLIED after explicit owner approval in this session and independent read-only exact-patch review.

Reuse the existing authoritative `CONDUCTION_1D_TRANSIENT` identifier (`thermal:transient_conduction_1d`) from conduction1d_schemes.py; declare it as the provided capability of the implemented nonuniform FV/backward-Euler realization. Keep the physical MODEL id and version0.1.0 unchanged. Move the realization version0.1.0 ->0.2.0 to make the corrected material declaration explicit; implementation reference is already0.2.0.

The currently committed realization is invalid and cannot be serialized by normal construction. Correcting it changes realization serialization, context/configuration/problem/step identity and source-derived provider build digest. No valid baseline digest for that invalid realization is fabricated. Existing historical artifacts are preserved; old realization references must not silently resolve to the corrected0.2.0 realization. No existing reader/schema is changed, and no bundle is regenerated.

Scientific capability wording already exists; no new capability identifier or claims/planning reachability is introduced. The realization still declares no sourced applicability limits and stays UNVALIDATED. The complete-domain-walk refusal and realization guard are retained.

This proposal addresses the root cause of the missing report in the claims suites: credibility requires a complete domain model index; M1C import currently fails and stops report construction. It does not repair replay verification of repeated refusals, a separate defect.

OD-31 count19 ->20 remains a separate decision. Do not modify tests/test_core_guards.py or certification/current_core_v2.json as part of applying this patch. Execute discovery after authorization and report its actual inventory. Later OD-3 required on final source; not authorized now.

Required owner decision: approve this exact capability declaration and realization0.2.0 identity transition, or keep it blocked. Conservation-policy replacement is a separate decision and is not authorized by this identity proposal.
