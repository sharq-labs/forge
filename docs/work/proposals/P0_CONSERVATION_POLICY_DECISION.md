# P0 global conservation admission — exact proposal, owner approved; applied

Patch P0_EXACT_GLOBAL_CONSERVATION.patch was applied after exact-patch review and explicit owner approval. It builds on the authorized M1C0.2.0 declaration correction. This is a scientific admission-policy change and requires explicit owner approval under this task. No physical coefficient, rtol, atol, model ID, realization key, discovery pin, schema reader, certificate or historical bundle is changed by this proposal.

## Mathematical contract

For shared face powers F and inward boundary powers b, each backward-Euler FV row obeys C_i*(Tnew_i-Told_i)=dt*(F_left-F_right+p_i+b_i). Pairing the same interior face once positively and once negatively cancels it from the global sum. Thus D=ΣC_i*(Tnew_i-Told_i), B=dt*(b0+b1), S=dt*Σp_i, R=D-B-S. BE/spatial truncation affects solution accuracy, not permission for nonzero discrete conservation loss.

Current global floor64*eps*dt*Σ(|A||T|+|rhs|) counts conductance times absolute temperature. Uniform fixed-domain conductance scalesN and there areN rows, producingN² even when all actual face fluxes vanish. It is a local matrix backward-error scale, not a physical global conservation budget. It can hide a physically fixed leak under refinement.

## Exact proposed global policy

F(x)=Fraction.from_float(float(x)) treats each finite represented SI value exactly. Compute D,B,S and X=max(Σ|C_i*(Tnew_i-Told_i)|,dt*(|b0|+|b1|+Σ|p_i|)) in rational arithmetic. Admit globally only if abs(D-B-S)<=F(atol)+F(rtol)*X. No floating-point gate-evaluation floor is needed because this comparison and all its arithmetic are exact. Positive declared atol/rtol remain unchanged; this does not impose exact equality. Finite subnormal inputs remain exactly represented. An overflowing/nonfinite floating diagnostic refuses rather than granting an infinite budget.

This is NOT an error bound on SuperLU, physical coefficients, model discrepancy, measurements or the solution. Those uncertainties remain unchanged/UNKNOWN where unknown. High-Fourier solver drift with small row residual may be unresolved and refused if it violates the declared conservation requirement; conductance never inflates the independent global budget.

## Local diagnostic and receipts

Retain the existing local balance diagnostic and its existing64*eps matrix-based allowance, as a separate additional condition. Its large allowance can never admit a step rejected by the exact global gate. Do not claim a global arithmetic bound proves local residual accuracy. Explicitly refuse nonfinite exchange/local residual/arithmetic/allowance.

Existing binding conservation_allowance_J and exchange fields become rounded displays of the exact global values; conservation_arithmetic_floor_J=0.0 means exact arithmetic in this gate, NOT zero scientific uncertainty. Add exact rational balance/allowance strings, policy identifier exact_represented_inputs_global/1, and separately labelled local allowance/floor. These material binding entries move future execution/step identities; historical records remain unchanged. The model and authorized realization IDs/versions stay unchanged. Source-derived provider build digest changes as for any code correction. No reader/public record schema change is introduced.

## Compatibility and limitations

This deliberately tightens formerly false global admissions and changes future binding identity. It preserves declared physical tolerances and local criterion, and needs owner approval before implementation. It evaluates represented inputs, not their physical truth. Boundary Dirichlet reaction remains reconstructed from the discrete row, not independent measured flux. Exact rational work costs O(N) operations with variable-size integers; record bounded timings, no speedup claim. Unresolvable solves may refuse rather than receive an inflated global tolerance. Verify output/report distinctions explicitly.

## Required verification

Actual M1C solver cases atN=4,16,32,64,128,256,512; uniform/nonuniform/heterogeneous states; sources and prescribed flux; datum and timestep shifts; fixed meaningful leaks; rounded/high-Fourier stress; nonfinite/overflow. Independent Fraction balance checks from registered capacities and geometric capacities; full original M1C manufactured/refinement tests; M1A/M1B integration; discovery/claims/compatibility and authorized fixed regression. No experimental-validation or certification claim follows.

Independent numerical reviewer recommends this exact-arithmetic global approach because it avoids unproven fsum/underflow multipliers and keeps solver error distinct. Final exact-patch review requested before application. Owner may approve exact proposal or leave policy blocked; no automatic approval inferred from the M1C identity decision.

Exact-patch independent review: no BLOCKER/MAJOR; two MINOR comments applied to the proposal only (local-only source commentary; explicit overflow/finite refusal for rounded display conversion). The owner subsequently approved the exact reviewed proposal, and git apply --check plus git apply succeeded.
