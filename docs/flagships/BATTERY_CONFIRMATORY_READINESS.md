# Battery blind confirmatory campaign — readiness for owner approval

Big Rocks campaign, Rock 3. This record is generated from `flagships/forge_flagships/battery_blind.py` (`readiness()`),
and `flagships/tests/test_battery_blind_readiness.py` fails if the digests below drift from the code.
**No confirmatory campaign has been run, and none will be without the owner's explicit approval.**

## Gate record

```text
PREREGISTRATION_DIGEST: eeda5704b3ed4ad3f1ce0d6d6d10857952b7f79a585c944c0e060c01af7fb701
PREREGISTRATION_STATE: DRAFT revision 1 (validated; NOT frozen in a production authority ledger)
HYPOTHESIS_REGISTRY_DIGEST: 43425dceb8580cd94d704cc356435cb164ce9e4a4069bc736de5d0b53187f2e5
FALSIFIER_ANCHOR: NONE (no real falsifier sealed; see REAL_FALSIFIERS_NOT_SEALED)
PRIOR_ART_SNAPSHOT_DIGEST: cfa1b0bf1812b869fcc8afaae143cc5fd0564e11e1624e106a30360d628b2f86
DATASET_ADAPTER_STATUS: IMPLEMENTED (DatasetManifest + ExposureGate + verify_discipline; exercised on synthetic data); confirmatory dataset NOT DESIGNATED
CONFIRMATORY_DATA_EXPOSED: NO
RED_TEAM_PLAN_DIGEST: dfe02dcd8e5548ece23b4553b8360e0f8766ca1733168c9092c6adca755def4f
RED_TEAM_SPACE_DIGEST: 1b81ce7cae0e77c5367fc03fd4b6547a33bfe7e53d110239b46565b645931182
MULTIPLICITY_BUDGET: {"confirmatory_query_budget": 32, "max_admitted_hypotheses": 4, "max_generated_hypotheses": 16} (digest16 c673ca04aa1b37d7)
BLINDFOLD / ESCROW ROUTE: confirmatory rows released one at a time through ExposureGate -> DurableCampaign ExposureAuthority (journaled, signed, owner-approved, discipline re-derived from the ledger); escrow-hosted isolated data authority: NOT WIRED for battery rows
KIRKALDY_2024: NOT MET (unchanged; its observed holdout is exploratory now)
BATTERY_READINESS: NOT_READY(CONFIRMATORY_DATASET_NOT_DESIGNATED; REAL_FALSIFIERS_NOT_SEALED; PRIOR_ART_NOT_SYSTEMATIC; PRODUCTION_AUTHORITY_NOT_PROVISIONED; DATA_AUTHORITY_ROUTE_NOT_WIRED)
```

## READINESS_BLOCKERS

1. **CONFIRMATORY_DATASET_NOT_DESIGNATED** — no confirmatory dataset is named or digest-pinned; the owner designates it (CONFIRMATORY_REQUIREMENTS) and a DatasetManifest is registered before anything else
2. **REAL_FALSIFIERS_NOT_SEALED** — real predictions need the exploratory fit on the Kirkaldy archives (outside this container) at the owner-designated confirmatory conditions; nothing real is sealed, so FALSIFIER_ANCHOR is empty
3. **PRIOR_ART_NOT_SYSTEMATIC** — the prior-art snapshot is the designer's recall with unverified citations; a systematic search is required before any novelty statement beyond the dry run
4. **PRODUCTION_AUTHORITY_NOT_PROVISIONED** — no production-profile authority ledger, operator-held root key or OWNER issuer exists for the real campaign (the dry run used a TEST-profile ledger with ephemeral keys)
5. **DATA_AUTHORITY_ROUTE_NOT_WIRED** — the confirmatory rows must be held by a data authority outside the proposer's process; the ExposureGate is that release point, but no escrow-hosted (isolated) battery data authority is deployed yet

## Hypothesis set (registered before any exposure)

| id | statement | note |
|---|---|---|
| `bat-h0-arrhenius-linear` | fade = k q exp(-Ea/R (1/T - 1/Tref)) -- the Kirkaldy probe law, kept as the reference competitor | the NOT MET reference: re-tested only as a competitor, never re-scored on its observed holdout |
| `bat-h1-two-mechanism` | fade = q [A1 exp(-B1 (1/T - 1/Tref)) + A2 exp(+B2 (1/T - 1/Tref))] -- SEI above, plating below | non-monotone temperature dependence (a minimum of the fade rate inside the window) |
| `bat-h2-power-law` | fade = B q^z exp(-Ea/R (1/T - 1/Tref)) | sub-linear throughput dependence (z selected by the pre-registered FidelityGraph screen) |
| `bat-h3-sqrt-plus-cold-plating` | fade = a q^0.5 exp(-Ea/R (1/T - 1/Tref)) + b q exp(-g T) | SEI (sqrt) plus plating that grows exponentially as T falls |

Each is a canonical `Hypothesis` (kind EQUATION, PROPOSED), with parameters UNKNOWN until fitted on exploratory data,
and a structure digest from the fade-family canonicalizer `forge.battery.fade_family/1`. That canonicalizer abstracts
every constant, exponents included, so `q^0.5` and `q^0.8` are the same family for the novelty check.

## What the pre-registration fixes (`real_preregistration()`)

All 21 required sections are present (`engcore.claims.preregistration.REQUIRED_SECTIONS`). The confirmatory dataset
is named by **requirements only** (`TO_BE_DESIGNATED_BY_OWNER`, identity `null`); the constructor refuses any
`values` / `observations` / `rows` / … key under it. The Kirkaldy 2024 archives are listed as **EXPLORATORY ONLY**:
BIG 14 opened both, so the observed holdout cannot be reused as confirmatory data, and its NOT MET stays.

Falsification: `prediction_deviation`, k = 3. The resolution is
`min(0.25 |predicted|, max(1.2 k sqrt(u_pred^2 + u_obs_declared^2), 0.004))`, and a falsifier is sealed only where
`k sqrt(u_pred^2 + u_obs_declared^2) <= resolution`. A hypothesis that cannot reach any resolution is declared
UNTESTABLE before exposure, with its reason. It is never dropped silently and never scored.

## Dry run (SYNTHETIC battery-like data, TEST-profile ledger; never the confirmatory holdout)

The dry run goes Hypothesis → DurableCampaign ExposureAuthority + DatasetManifest/ExposureGate → sealed falsifiers →
multiplicity → FidelityGraph screen with a false-elimination audit → owner approval → confirmatory release through the
gate → adjudication → Red Team → issuer-bound credibility (test mode) → one Discovery Passport per hypothesis.

```text
discipline:             CONFIRMATORY
statuses:               {"bat-h0-arrhenius-linear": "surviving", "bat-h1-two-mechanism": "surviving", "bat-h2-power-law": "surviving", "bat-h3-sqrt-plus-cold-plating": "proposed"}
falsifiers sealed:      {"bat-h0-arrhenius-linear": 2, "bat-h1-two-mechanism": 2, "bat-h2-power-law": 2, "bat-h3-sqrt-plus-cold-plating": 0}
fidelity link admitted: True (power-law exponent selected on exploratory data: z = 0.975)
multiplicity family:    4
counts_as_discovery:    {"bat-h0-arrhenius-linear": false, "bat-h1-two-mechanism": false, "bat-h2-power-law": false, "bat-h3-sqrt-plus-cold-plating": false}
```

What the dry run shows about the design:

- The synthetic confirmatory points (drive cycle at 15 / 32 °C, 500 / 900 Ah) do **not** discriminate h0–h2. All three
  survive their sealed falsifiers, so a SURVIVING status from this design would say little. Before approval, the real
  confirmatory design needs conditions where the competing hypotheses' predictions differ by more than the resolution
  (for example colder cells and higher throughput).
- h3 is declared UNTESTABLE before exposure: its exploratory fit cannot reach the pre-registered resolution.
- The Red Team FALSIFIES every hypothesis's threshold claim at the edge of the attack space, where model routes
  disagree. That is agreement of models, not a measurement, and it blocks the credibility requirement as it should.
- No passport counts as a discovery: the run is a dry run and the ledger is a TEST profile.

## Owner decision required

Approval needs, in order:

1. designate and digest-pin the confirmatory dataset;
2. provision the production authority ledger (operator-held root, an OWNER issuer separate from the campaign's
   EXPOSURE issuer);
3. run the exploratory fit on the Kirkaldy archives and seal real falsifiers at the designated conditions;
4. replace the prior-art recall with a systematic search;
5. sign the `confirmatory_approval` record for exactly the frozen pre-registration digest and the manifest digest.

Until then, the state is the NOT_READY above.
