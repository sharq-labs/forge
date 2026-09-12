"""Core Freeze V1: build the freeze manifest, record its assurance, verify both.

    python -m tools.certification.core_freeze --verify
    python -m tools.certification.core_freeze --build
    python -m tools.certification.core_freeze --record-assurance --candidate <commit>

The certificate (``core_certificate``) answers "are these the certified BYTES".
This answers the different question a freeze asks: "is this still the frozen
CONTRACT" -- the 194 frozen symbols and their shapes, what serializes and what
reads which versions, what identity digests mean, what order results come back
in, which exception families exist -- and "was it assured, by what, on which
commit".

THE RULE THIS INHERITS FROM THE CERTIFICATE
---------------------------------------------
Every expected value is read from the STORED manifest. The verifier computes
the live facts from the tree and compares; it never rebuilds the manifest and
compares the tree to that, which would compare the tree to itself and pass for
any tree at all. ``--build`` exists to write the manifest once, at the freeze.

TWO FILES, AND WHY
-------------------
``core_freeze_v1.json`` is the CONTRACT manifest. Everything in it is a fact
about the frozen candidate and can be computed before any assurance runs, so it
is committed IN the candidate and verified by the candidate's own test suite.

``core_freeze_v1_assurance.json`` is the ASSURANCE record: which commit was
assured, with what results, backed by which evidence files. It cannot be in the
candidate -- results about a commit cannot be written into that commit -- so it
is committed after, and the verifier enforces that the commits after the
candidate touch ONLY the evidence and report paths listed in
:data:`POST_CANDIDATE_PATHS`. The candidate's ``src/`` is therefore provably the
tagged ``src/``.

EXACT FREEZE vs COMPATIBLE DESCENDANT
--------------------------------------
On the freeze commit itself every check applies, including byte-level ones (the
``src`` tree hash, the domain digest, the certificate aggregate). Later commits
are allowed to do what the freeze policy allows -- fix bugs, refactor, add
domains, add tests -- so on a descendant the byte-level checks become
informational and the CONTRACT checks still bind. A descendant whose frozen API,
serialization, identity, ordering or exception facts differ is not a descendant
of Core Freeze V1: it needs a compatibility review and, if intended, a new
freeze version.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tools.certification.core_certificate import (
    load_certificate,
    repo_root,
    verify_certificate,
)

FREEZE_SCHEMA = "engcore.core_freeze/1"
ASSURANCE_SCHEMA = "engcore.core_freeze_assurance/1"
FREEZE_NAME = "Core Freeze V1"
FREEZE_VERSION = "1.0"
#: Follows the repository's existing tag convention (``v1.0-benchmark``,
#: ``v1.1-benchmark``): ``v<major>.<minor>-<subject>``, annotated.
FREEZE_TAG = "v1.0-core-freeze"

#: The commit Sprint 11 started from. It was a freeze candidate and was
#: BLOCKED -- see ``BLOCKED_CANDIDATES``.
FINAL_FREEZE_BASELINE = "af43c896f79a37ac10c0c4e981836b85b24e5a5b"

BLOCKED_CANDIDATES = (
    {
        "commit": FINAL_FREEZE_BASELINE,
        "verdict": "FREEZE_BLOCKED",
        "defect_class": "broken compatibility claim",
        "defect": (
            "tests/test_core_api_serialization.py stated the serialization "
            "policy as `SUPPORTED_LEGACY: none. No legacy format is supported` "
            "and `62 records`. Eight FROZEN readers (ScientificResult, "
            "ProvenanceRecord, CrossSolverConsensus, RawSolverOutput, "
            "ScientificModelDefinition, ValidityAssessment, QuantityDependency, "
            "QuantityTransfer) accept older schema versions, and the frozen "
            "round-trippable count is 61. Behaviour was correct and tested; the "
            "written contract contradicted it."
        ),
        "fix": (
            "module docstring corrected to state the eight readers and their "
            "accepted versions, and 61. Proved docstring-only by comparing the "
            "AST of every non-docstring statement before and after."
        ),
    },
)

MANIFEST_PATH = "certification/core_freeze_v1.json"
ASSURANCE_PATH = "certification/core_freeze_v1_assurance.json"
REPORT_PATH = "certification/CORE_FREEZE_V1.md"
CERTIFICATE_PATH = "certification/current_core_v2.json"
PROBE_PATH = "benchmarks/core_freeze_v1/audit/reproduce.py"
POLICY_PATH = "docs/CORE_FREEZE_POLICY.md"

#: Files whose bytes ARE the contract, pinned by digest.
PINNED_CONTRACT_FILES = (
    "tests/api/frozen_api_snapshot.json",
    "tests/api/full_api_snapshot.json",
)

#: Canonical artifacts the manifest REFERENCES rather than copies.
REFERENCES = {
    "frozen_symbol_manifest": "tests/api/frozen_api_snapshot.json",
    "experimental_symbol_manifest": "tests/api/full_api_snapshot.json",
    "api_snapshot_tool": "src/engcore/api_snapshot.py",
    "freeze_policy": POLICY_PATH,
    "serialization_compatibility": "tests/test_core_api_serialization.py",
    "dependency_hygiene": "tests/test_core_api_contracts.py",
    "dependency_reachability": "tests/test_core_guards.py",
    "layering_and_package_classification": "tests/test_core_api_layering.py",
    "deprecation_policy": "tests/test_core_api_deprecation.py",
    "executable_policy": "tests/test_core_freeze_policy.py",
    "freeze_verifier": "tools/certification/core_freeze.py",
    "freeze_manifest_tests": "tests/test_core_freeze_manifest.py",
    "reproduction_probe": PROBE_PATH,
    "reproduction_driver": "benchmarks/core_freeze_v1/audit/freeze_reproduction.py",
    "assurance_suites": "benchmarks/core_freeze_v1/audit/suites.py",
    "sprint10_mutation_matrix": "benchmarks/core_api_stability/audit/mutations.py",
    "certified_mutation_harness": "tests/mutation_guards.py",
    "domain_boundary_proof": "benchmarks/core_api_stability/audit/domain_boundary.py",
    "core_certificate": CERTIFICATE_PATH,
    "assurance_record": ASSURANCE_PATH,
    "freeze_report": REPORT_PATH,
}

#: The ONLY paths commits after the assured candidate may touch while still
#: being the freeze. Evidence produced by running the assurance on the
#: candidate, and the documents describing it. No code, no tests.
POST_CANDIDATE_PATHS = (
    ASSURANCE_PATH,
    REPORT_PATH,
    "docs/release/v1.0-core-freeze.md",
    "benchmarks/core_freeze_v1/REPRODUCTION.json",
    "benchmarks/core_freeze_v1/REPRODUCTION_OUTPUT.json",
    "benchmarks/core_freeze_v1/SUITES.json",
    "benchmarks/core_freeze_v1/MUTATION_HARNESS_79.log",
    "benchmarks/core_api_stability/MUTATIONS.json",
    "benchmarks/core_api_stability/DOMAIN_BOUNDARY.json",
)

#: Evidence the assurance record must be backed by.
EVIDENCE = {
    "reproduction": "benchmarks/core_freeze_v1/REPRODUCTION.json",
    "reproduction_output": "benchmarks/core_freeze_v1/REPRODUCTION_OUTPUT.json",
    "suites": "benchmarks/core_freeze_v1/SUITES.json",
    "certified_79_log": "benchmarks/core_freeze_v1/MUTATION_HARNESS_79.log",
    "sprint10_mutations": "benchmarks/core_api_stability/MUTATIONS.json",
    "domain_boundary": "benchmarks/core_api_stability/DOMAIN_BOUNDARY.json",
}

#: Suites the assurance record must show green, by the names SUITES.json uses.
REQUIRED_SUITES = (
    "FAST", "FULL", "contract_guard", "capability_boundary", "scientific_truth",
    "field_suites", "field_profile_suites", "api_snapshot", "serialization",
    "dependency_layering", "freeze_manifest", "certificate",
)
#: Domain regression is NOT a suite here: domain_boundary.py runs those suites as
#: the third leg of its proof, and `evidence.domain_boundary` checks that record.

NON_CLAIMS = (
    "The 11 EXPERIMENTAL symbols are not frozen and may change, subject to the "
    "experimental policy. EXPERIMENTAL != FROZEN.",
    "Behaviour, numerical results and performance figures are not "
    "compatibility promises. The freeze is about the contract's shape and the "
    "semantics listed in `contract`, not about what a solver computes.",
    "Undocumented error prose is not frozen. Exception CLASSES and their family "
    "roots are; the text of a message is not.",
    "Internal implementation details, private helpers, submodule paths beneath "
    "the seven canonical modules, and benchmark implementation details are not "
    "frozen.",
    "`except ScientificCoreError` does NOT catch everything the Core raises. "
    "There are seven exception roots.",
    "`src.engcore` is an unsupported checkout alias. It is not part of the "
    "frozen contract and is absent from the wheel.",
    "The non-Core packages under engcore (domains, systems, sria, design, mcp) "
    "carry no freeze guarantee.",
    "The wheel FILE is not byte-reproducible without SOURCE_DATE_EPOCH (zip "
    "entry timestamps). The reproducible identity is the RECORD content digest; "
    "the artefact hash is reproducible only with the epoch the assurance "
    "record names.",
    "EI/RI/FM/SP mutation families were NOT re-measured for this freeze. They "
    "were last measured in Sprint 7 (core_v2_recertification) with a harness "
    "kept outside the repository, and nothing in Core Freeze V1 rests on them.",
    "The `workers` parameter of run_sweep / rerun_failed is EXPERIMENTAL; "
    "parallel execution is not part of the frozen contract.",
    "Performance numbers in any benchmark round are measurements, not promises.",
)

CHANGE_POLICY = {
    "allowed_without_breaking_freeze": [
        "bug fixes preserving frozen behavior",
        "internal refactors preserving frozen contracts",
        "performance improvements preserving exact semantics",
        "new tests",
        "documentation",
        "new Domain work",
        "new optional internal implementations",
    ],
    "requires_core_compatibility_review": [
        "removing a frozen symbol",
        "renaming a frozen symbol",
        "a signature change",
        "changing required or default arguments",
        "changing enum members or values",
        "breaking a supported serialization format",
        "changing material digest semantics",
        "changing evidence identity semantics",
        "changing trust or admission semantics",
        "removing public result fields",
        "changing stable exception classes",
    ],
    "requires_new_core_freeze_version": [
        "any intentional incompatible change to the frozen contract",
    ],
}

EXPERIMENTAL_POLICY = {
    "rule": (
        "Experimental public surfaces are excluded from Core Freeze V1. They "
        "remain importable and remain visibly classified EXPERIMENTAL in the API "
        "snapshot. EXPERIMENTAL != FROZEN."
    ),
    "promotion_requires": [
        "explicit API review",
        "compatibility review",
        "tests",
        "inclusion in a later freeze manifest",
    ],
    "forbidden": (
        "silently promoting an experimental symbol by adding it to the frozen "
        "digest. The verifier fails on any change to the experimental set or "
        "the frozen digest."
    ),
}


# =====================================================================
# helpers
# =====================================================================

def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def git(root: pathlib.Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def is_ancestor(root: pathlib.Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root, capture_output=True,
    ).returncode == 0


def load_probe(root: pathlib.Path):
    spec = importlib.util.spec_from_file_location(
        "_core_freeze_reproduce", root / PROBE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def domain_digest(root: pathlib.Path) -> tuple[str, int]:
    """The Sprint 10 Part V algorithm: sha256 over (relative path, file sha256)."""
    base = root / "src" / "engcore" / "domains"
    entries = sorted(
        (p.relative_to(base).as_posix(), p.read_bytes())
        for p in base.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    hasher = hashlib.sha256()
    for rel, blob in entries:
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(hashlib.sha256(blob).digest())
    return hasher.hexdigest(), len(entries)


def contract_facts(reproduction: Mapping[str, Any]) -> dict[str, Any]:
    """The FROZEN subset of a reproduction document.

    Experimental fixtures, experimental identity pairs and the experimental
    `workers` ordering are deliberately dropped: they are recorded by the probe
    so a difference is visible, but a change to them is not a change to Core
    Freeze V1 and must not fail its verifier.
    """
    api = reproduction["api"]
    ser = reproduction["serialization"]
    ident = reproduction["identity"]
    order = reproduction["ordering"]
    return {
        "api": {
            "frozen_digest": api["frozen_digest"],
            "frozen_count": api["frozen_count"],
            "total_count": api["total_count"],
            "experimental": api["experimental"],
            "deprecated": api["deprecated"],
            "canonical_modules": api["canonical_modules"],
        },
        "serialization": {
            "round_trippable_count": ser["round_trippable_count"],
            "round_trippable_sha256": ser["round_trippable_sha256"],
            "export_only_count": ser["export_only_count"],
            "export_only": ser["export_only"],
            "legacy_readers": ser["legacy_readers"],
            "fixtures": {
                name: {k: v for k, v in record.items() if k != "classification"}
                for name, record in ser["fixtures"].items()
                if record["classification"] == "FREEZE"
            },
        },
        "identity": {
            "pairs": {
                name: {k: pair[k] for k in ("left", "right", "equal", "expected_equal")}
                for name, pair in ident["pairs"].items()
                if pair["classification"] == "FREEZE"
            },
            "reference": ident["reference"],
        },
        "ordering": {
            "sequential": order["sequential"],
            "fail_fast_sequential": order["fail_fast_sequential"],
            "case_identities": order["case_identities"],
            "declaration_identity_forward": order["declaration_identity_forward"],
            "declaration_identity_reversed": order["declaration_identity_reversed"],
            "duplicate_case_ids": order["duplicate_case_ids"],
        },
        "exceptions": reproduction["exceptions"],
    }


def package_metadata(root: pathlib.Path) -> dict[str, Any]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    return {
        "distribution": project["name"],
        "version": project["version"],
        "requires_python": project.get("requires-python"),
        "package_discovery": config["tool"]["setuptools"]["packages"],
        "import_name": "engcore",
    }


# =====================================================================
# live facts
# =====================================================================

@dataclass
class Live:
    root: pathlib.Path
    head: str
    clean: bool
    dirty_paths: list[str]
    engcore_file: str
    reproduction: dict[str, Any]
    reproduction_sha256: str
    contract: dict[str, Any]
    trees: dict[str, str]
    domain_digest: str
    domain_file_count: int
    package: dict[str, Any]
    pinned: dict[str, str]
    certificate_ok: bool
    certificate_problems: list[str]
    certificate_aggregate: str
    certificate_commit: str
    certificate_sha256: str


def collect_live(root: pathlib.Path) -> Live:
    probe = load_probe(root)
    reproduction = probe.build()
    import engcore  # imported by the probe; this reads where it came from

    # NOT stripped: the first porcelain line starts with a status column that
    # may be a space, and stripping it shifts every path by one character.
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                               capture_output=True, text=True, encoding="utf-8",
                               check=True).stdout
    certificate = load_certificate(root / CERTIFICATE_PATH)
    result = verify_certificate(root, certificate, require_clean=False,
                                require_commit=False)
    digest, count = domain_digest(root)
    return Live(
        root=root,
        head=git(root, "rev-parse", "HEAD"),
        clean=not porcelain.strip(),
        dirty_paths=[line[3:] for line in porcelain.splitlines() if line.strip()],
        engcore_file=str(pathlib.Path(engcore.__file__).resolve()),
        reproduction=reproduction,
        reproduction_sha256=sha256_bytes(probe.canonical(reproduction)),
        contract=contract_facts(reproduction),
        trees={
            "src": git(root, "rev-parse", "HEAD:src"),
            "domains": git(root, "rev-parse", "HEAD:src/engcore/domains"),
            "tests_api": git(root, "rev-parse", "HEAD:tests/api"),
        },
        domain_digest=digest,
        domain_file_count=count,
        package=package_metadata(root),
        pinned={p: sha256_file(root / p) for p in PINNED_CONTRACT_FILES},
        certificate_ok=result.ok,
        certificate_problems=list(result.problems),
        certificate_aggregate=str(certificate["manifest"]["aggregate_digest"]),
        certificate_commit=str(certificate["repository"]["commit"]),
        certificate_sha256=sha256_file(root / CERTIFICATE_PATH),
    )


# =====================================================================
# build
# =====================================================================

def build_manifest(live: Live) -> dict[str, Any]:
    api = live.contract["api"]
    return {
        "schema": FREEZE_SCHEMA,
        "freeze": {
            "name": FREEZE_NAME,
            "version": FREEZE_VERSION,
            "tag": FREEZE_TAG,
            "tag_convention": (
                "the repository's existing annotated-tag convention "
                "v<major>.<minor>-<subject> (v1.0-benchmark, v1.1-benchmark)"
            ),
            "baseline_commit": FINAL_FREEZE_BASELINE,
            "blocked_candidates": list(BLOCKED_CANDIDATES),
            "freeze_commit": (
                "recorded in the assurance record, which cannot live in the "
                "commit it describes; the candidate's src/ tree hash below is the "
                "content-addressed identity and binds regardless"
            ),
            "distribution_version_note": (
                "Core Freeze V1.0 versions the frozen CONTRACT. The distribution "
                f"version ({live.package['version']}) is independent and was not "
                "changed by the freeze."
            ),
        },
        "trees": live.trees,
        "domain": {
            "digest": live.domain_digest,
            "file_count": live.domain_file_count,
            "algorithm": (
                "sha256 over path-sorted (relative path utf-8, 0x00, sha256 of "
                "exact file bytes) for every file under src/engcore/domains "
                "excluding __pycache__ -- the Sprint 10 Part V algorithm"
            ),
        },
        "api": {
            **api,
            "frozen_count_expected": 194,
            "experimental_count": len(api["experimental"]),
            "pinned_files": live.pinned,
        },
        "contract": {
            "includes": [
                "canonical public imports from the seven canonical modules",
                "frozen function and class signatures, including parameter kind and defaults",
                "public dataclass fields, in order, and their default factories",
                "enum members and values",
                "supported serialization formats, current and declared legacy",
                "scientific identity and digest semantics (material vs non-material)",
                "evidence identity semantics",
                "admission and trust semantics as exercised by the certified harness",
                "documented exception classes and their seven family roots",
                "deterministic ordering where promised (sweep outcomes and failures in declaration order)",
                "package identity (engcore; src.engcore absent from the wheel)",
                "installed-wheel API parity",
            ],
            "excludes": [
                "internal implementation details",
                "incidental private helpers",
                "benchmark implementation details",
                "experimental surfaces",
                "undocumented error prose",
                "performance numbers as compatibility promises",
            ],
            "facts": {k: v for k, v in live.contract.items() if k != "api"},
            "reproduction_sha256": live.reproduction_sha256,
        },
        "certificate": {
            "path": CERTIFICATE_PATH,
            "aggregate_digest": live.certificate_aggregate,
            "certified_commit": live.certificate_commit,
            "file_sha256": live.certificate_sha256,
        },
        "package": live.package,
        "references": {
            name: {"path": path, **({"sha256": sha256_file(live.root / path)}
                                    if (live.root / path).exists()
                                    and path not in (ASSURANCE_PATH, REPORT_PATH)
                                    else {})}
            for name, path in sorted(REFERENCES.items())
        },
        "post_candidate_paths": list(POST_CANDIDATE_PATHS),
        "change_policy": CHANGE_POLICY,
        "experimental_policy": EXPERIMENTAL_POLICY,
        "non_claims": list(NON_CLAIMS),
    }


# =====================================================================
# verify
# =====================================================================

@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    binding: bool = True  # False = informational in this mode


@dataclass
class FreezeVerification:
    mode: str
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.binding)

    def add(self, name: str, ok: bool, detail: str = "", binding: bool = True) -> None:
        self.checks.append(Check(name, bool(ok), detail, binding))

    def failed(self) -> list[str]:
        return [c.name for c in self.checks if c.binding and not c.ok]

    def render(self) -> str:
        lines = [f"mode: {self.mode}"]
        for c in self.checks:
            tag = ("PASS" if c.ok else "FAIL") if c.binding else (
                "info" if c.ok else "INFO")
            lines.append(f"  {tag:4}  {c.name}" + (f" -- {c.detail}" if c.detail else ""))
        lines.append("OK" if self.ok else "FAILED")
        return "\n".join(lines)


def _diff(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Named differences, so a failure says WHAT moved rather than 'mismatch'."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in sorted(set(expected) | set(actual)):
            where = f"{path}.{key}" if path else str(key)
            if key not in actual:
                out.append(f"{where}: missing")
            elif key not in expected:
                out.append(f"{where}: unexpected")
            else:
                out.extend(_diff(expected[key], actual[key], where))
        return out
    return [] if expected == actual else [f"{path}: {expected!r} -> {actual!r}"]


def _summarise(differences: list[str], limit: int = 4) -> str:
    if not differences:
        return ""
    more = f" (+{len(differences) - limit} more)" if len(differences) > limit else ""
    return "; ".join(d[:160] for d in differences[:limit]) + more


def verify_manifest(
    manifest: Mapping[str, Any],
    live: Live,
    *,
    require_clean: bool = True,
) -> FreezeVerification:
    exact = (
        manifest.get("trees", {}).get("src") == live.trees["src"]
        and manifest.get("trees", {}).get("domains") == live.trees["domains"]
        and manifest.get("trees", {}).get("tests_api") == live.trees["tests_api"]
    )
    baseline = manifest.get("freeze", {}).get("baseline_commit", "")
    descends = bool(baseline) and is_ancestor(live.root, baseline, live.head)
    mode = "EXACT_FREEZE" if exact else (
        "DESCENDANT" if descends else "UNRELATED")
    v = FreezeVerification(mode=mode)

    # ---- manifest internal consistency ------------------------------------
    v.add("manifest.schema", manifest.get("schema") == FREEZE_SCHEMA,
          str(manifest.get("schema")))
    api = manifest.get("api", {})
    experimental = api.get("experimental", [])
    internal = [
        ("frozen+experimental==total",
         api.get("frozen_count", -1) + len(experimental) == api.get("total_count")),
        ("experimental_count==len(experimental)",
         api.get("experimental_count") == len(experimental)),
        ("frozen_count==194", api.get("frozen_count") == api.get("frozen_count_expected") == 194),
        ("no deprecations recorded", api.get("deprecated") == []),
        ("tag matches version",
         manifest.get("freeze", {}).get("tag") == f"v{manifest.get('freeze', {}).get('version')}-core-freeze"),
        ("eight legacy readers",
         len(manifest.get("contract", {}).get("facts", {}).get("serialization", {})
             .get("legacy_readers", {})) == 8),
        ("non_claims present", bool(manifest.get("non_claims"))),
        ("experimental policy forbids silent promotion",
         "forbidden" in manifest.get("experimental_policy", {})),
    ]
    bad = [name for name, ok in internal if not ok]
    v.add("manifest.internal_consistency", not bad, ", ".join(bad))

    # ---- where the facts came from ----------------------------------------
    v.add("live.engcore_is_this_checkout",
          pathlib.Path(live.engcore_file).is_relative_to(live.root / "src"),
          live.engcore_file)
    v.add("tree.clean", live.clean or not require_clean,
          "" if live.clean else f"uncommitted: {live.dirty_paths[:5]}")
    v.add("tree.relation", mode in ("EXACT_FREEZE", "DESCENDANT"),
          f"{mode}; baseline {baseline[:12]} ancestor of HEAD: {descends}")

    # ---- the frozen contract (binding in every mode) -----------------------
    expected_api = {k: api.get(k) for k in (
        "frozen_digest", "frozen_count", "total_count", "experimental",
        "deprecated", "canonical_modules")}
    v.add("contract.api", not _diff(expected_api, live.contract["api"]),
          _summarise(_diff(expected_api, live.contract["api"])))
    stored_facts = manifest.get("contract", {}).get("facts", {})
    for section in ("serialization", "identity", "ordering", "exceptions"):
        differences = _diff(stored_facts.get(section), live.contract[section])
        v.add(f"contract.{section}", not differences, _summarise(differences))
    identity_holds = all(
        p["equal"] == p["expected_equal"]
        for p in live.contract["identity"]["pairs"].values()
    )
    v.add("contract.identity_semantics_hold", identity_holds)
    ser = live.contract["serialization"]
    v.add("contract.serialization_semantics_hold",
          all(f["round_trip_byte_identical"] for f in ser["fixtures"].values())
          and all(f["unknown_version_refused"] in (True, None)
                  for f in ser["fixtures"].values())
          and all(r["undeclared_version_refused"] for r in ser["legacy_readers"].values()))

    # ---- experimental exclusions ------------------------------------------
    root = live.root
    frozen_file = json.loads((root / "tests/api/frozen_api_snapshot.json").read_text(encoding="utf-8"))
    full_file = json.loads((root / "tests/api/full_api_snapshot.json").read_text(encoding="utf-8"))
    frozen_keys = {(e["module"], e["name"]) for e in frozen_file["symbols"]}
    experimental_keys = {tuple(x) for x in experimental}
    leaked = sorted(frozen_keys & experimental_keys)
    marked = {(e["module"], e["name"]) for e in full_file["symbols"]
              if e["classification"] == "EXPERIMENTAL"}
    v.add("experimental.excluded_from_frozen_snapshot", not leaked, str(leaked))
    v.add("experimental.visibly_classified", marked == experimental_keys,
          _summarise(_diff(sorted(map(list, experimental_keys)), sorted(map(list, marked)))))

    # ---- certificate -------------------------------------------------------
    cert = manifest.get("certificate", {})
    v.add("certificate.verifies", live.certificate_ok,
          "; ".join(live.certificate_problems[:3]))
    v.add("certificate.identity",
          cert.get("aggregate_digest") == live.certificate_aggregate
          and cert.get("certified_commit") == live.certificate_commit,
          f"manifest {str(cert.get('aggregate_digest'))[:12]} / live {live.certificate_aggregate[:12]}",
          binding=exact)

    # ---- byte-level identity: binding on the freeze, informational after ----
    v.add("bytes.pinned_contract_files", api.get("pinned_files") == live.pinned,
          _summarise(_diff(api.get("pinned_files"), live.pinned)), binding=True)
    v.add("bytes.reproduction_sha256",
          manifest.get("contract", {}).get("reproduction_sha256") == live.reproduction_sha256,
          "the whole probe document, experimental facts included", binding=exact)
    v.add("domain.digest",
          manifest.get("domain", {}).get("digest") == live.domain_digest,
          f"manifest {str(manifest.get('domain', {}).get('digest'))[:12]} / live {live.domain_digest[:12]}",
          binding=exact)
    v.add("package.metadata", manifest.get("package") == live.package,
          _summarise(_diff(manifest.get("package"), live.package)), binding=exact)
    return v


def verify_assurance(
    assurance: Mapping[str, Any],
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    live: Live,
    verification: FreezeVerification,
    *,
    changed_paths: Sequence[str] | None = None,
) -> None:
    """Checks on the assurance record, appended to ``verification``.

    Every figure is re-derived from the committed evidence file it claims to
    summarise. A record that said 79/79 over a log that says otherwise fails
    here rather than being believed.
    """
    v = verification
    root = live.root
    exact = v.mode == "EXACT_FREEZE"
    v.add("assurance.schema", assurance.get("schema") == ASSURANCE_SCHEMA)
    v.add("assurance.manifest_sha256",
          assurance.get("manifest_sha256") == sha256_bytes(manifest_bytes))
    v.add("assurance.tag", assurance.get("tag") == manifest.get("freeze", {}).get("tag"))

    candidate = str(assurance.get("candidate_commit", ""))
    related = bool(candidate) and is_ancestor(root, candidate, live.head)
    v.add("assurance.candidate_is_ancestor_of_head", related, candidate[:12])
    if changed_paths is None and related:
        changed_paths = [p for p in git(root, "diff", "--name-only", candidate,
                                        live.head).splitlines() if p]
    outside = sorted(set(changed_paths or ()) - set(POST_CANDIDATE_PATHS))
    v.add("assurance.post_candidate_changes_are_evidence_only", not outside,
          f"outside the allowed paths: {outside[:6]}" if outside else
          f"{len(changed_paths or ())} path(s), all allowed",
          binding=exact)

    evidence = assurance.get("evidence", {})
    missing = [n for n, p in EVIDENCE.items() if not (root / p).exists()]
    v.add("evidence.present", not missing, str(missing))
    mismatched = [
        n for n, p in EVIDENCE.items()
        if (root / p).exists() and evidence.get(n) != sha256_file(root / p)
    ]
    v.add("evidence.hashes", not mismatched, str(mismatched))
    if missing:
        return

    results = assurance.get("results", {})

    reproduction = json.loads((root / EVIDENCE["reproduction"]).read_text(encoding="utf-8"))
    output_sha = sha256_file(root / EVIDENCE["reproduction_output"])
    v.add("evidence.reproduction_verdict",
          reproduction.get("verdict") == "REPRODUCED"
          and reproduction.get("commit") == candidate
          and reproduction.get("determinism", {}).get("reproduction_sha256") == output_sha
          and output_sha == manifest.get("contract", {}).get("reproduction_sha256"),
          f"verdict {reproduction.get('verdict')}, commit {str(reproduction.get('commit'))[:12]}")
    v.add("evidence.wheel_identity",
          results.get("wheel", {}).get("record_content_sha256")
          == reproduction.get("wheel", {}).get("record_content_sha256")
          and results.get("wheel", {}).get("sha256") == reproduction.get("wheel", {}).get("sha256"))

    suites = json.loads((root / EVIDENCE["suites"]).read_text(encoding="utf-8"))
    red = [n for n in REQUIRED_SUITES
           if suites.get("suites", {}).get(n, {}).get("exit") != 0
           or suites.get("suites", {}).get(n, {}).get("failed", 1) != 0]
    v.add("evidence.suites_green", not red and suites.get("commit") == candidate,
          f"red or missing: {red}" if red else f"commit {str(suites.get('commit'))[:12]}")

    matrix = json.loads((root / EVIDENCE["sprint10_mutations"]).read_text(encoding="utf-8"))
    v.add("evidence.sprint10_mutations",
          matrix.get("control") == "GREEN"
          and matrix.get("killed") == matrix.get("written")
          and not matrix.get("survivors") and not matrix.get("stale")
          and results.get("sprint10_mutations", {}).get("killed") == matrix.get("killed"),
          f"{matrix.get('killed')}/{matrix.get('written')} of {matrix.get('requested_total')}")

    log = (root / EVIDENCE["certified_79_log"]).read_text(encoding="utf-8", errors="replace")
    import re
    tally = re.search(r"(\d+)/(\d+) mutations were killed", log)
    reds = len(re.findall(r"^G\S+\s+RED\b", log, re.M))
    greens = re.findall(r"^(G\S+)\s+GREEN\b", log, re.M)
    control = log.startswith("CONTROL GREEN")
    certified = results.get("certified_79", {})
    v.add("evidence.certified_79",
          control and tally is not None and tally.group(1) == tally.group(2) == "79"
          and reds == 79 and not greens
          and certified.get("killed") == 79 and certified.get("survivors") == 0,
          f"control {'GREEN' if control else 'NOT GREEN'}, "
          f"{tally.group(0) if tally else 'no tally'}, lines RED={reds} GREEN={len(greens)}")

    domain = json.loads((root / EVIDENCE["domain_boundary"]).read_text(encoding="utf-8"))
    v.add("evidence.domain_boundary",
          domain.get("boundary_intact") is True
          and domain.get("domain_start_digest") == domain.get("domain_end_digest")
          == manifest.get("domain", {}).get("digest"),
          str(domain.get("domain_end_digest"))[:12])

    carried = results.get("ei_ri_fm_sp", {})
    v.add("assurance.ei_ri_fm_sp_labelled_honestly",
          carried.get("status") in ("REMEASURED", "CARRIED_FORWARD")
          and (carried.get("status") != "CARRIED_FORWARD"
               or bool(carried.get("justification"))))


def verify(root: pathlib.Path, *, require_clean: bool = True,
           live: Live | None = None) -> FreezeVerification:
    manifest_file = root / MANIFEST_PATH
    if not manifest_file.exists():
        v = FreezeVerification(mode="NO_MANIFEST")
        v.add("manifest.present", False, MANIFEST_PATH)
        return v
    manifest_bytes = manifest_file.read_bytes()
    manifest = json.loads(manifest_bytes)
    live = live or collect_live(root)
    v = verify_manifest(manifest, live, require_clean=require_clean)
    assurance_file = root / ASSURANCE_PATH
    if assurance_file.exists():
        verify_assurance(json.loads(assurance_file.read_bytes()), manifest_bytes,
                         manifest, live, v)
    else:
        v.add("assurance.present", False,
              "no assurance record yet: this is a CANDIDATE, not a completed freeze",
              binding=False)
    return v


# =====================================================================
# record assurance
# =====================================================================

def record_assurance(root: pathlib.Path, candidate: str) -> dict[str, Any]:
    manifest_bytes = (root / MANIFEST_PATH).read_bytes()
    manifest = json.loads(manifest_bytes)
    for name, path in EVIDENCE.items():
        if not (root / path).exists():
            raise SystemExit(f"evidence {name} missing: {path}")
    reproduction = json.loads((root / EVIDENCE["reproduction"]).read_text(encoding="utf-8"))
    suites = json.loads((root / EVIDENCE["suites"]).read_text(encoding="utf-8"))
    matrix = json.loads((root / EVIDENCE["sprint10_mutations"]).read_text(encoding="utf-8"))
    domain = json.loads((root / EVIDENCE["domain_boundary"]).read_text(encoding="utf-8"))
    log_bytes = (root / EVIDENCE["certified_79_log"]).read_bytes()
    src_changed_since_sprint10 = git(
        root, "diff", "--name-only", FINAL_FREEZE_BASELINE, candidate, "--", "src")
    import platform

    return {
        "schema": ASSURANCE_SCHEMA,
        "freeze": FREEZE_NAME,
        "version": FREEZE_VERSION,
        "tag": FREEZE_TAG,
        "candidate_commit": candidate,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "blocked_candidates": list(BLOCKED_CANDIDATES),
        "certificate": {
            **manifest["certificate"],
            "reissued_during_freeze": False,
            "why_not": (
                "no file inside certified scope changed between the Sprint 10 "
                "certificate and the candidate; the freeze adds tooling, tests, "
                "documentation and evidence, all outside scope"
            ),
        },
        "evidence": {n: sha256_file(root / p) for n, p in EVIDENCE.items()},
        "results": {
            "reproduction": {"verdict": reproduction["verdict"],
                             "checks": reproduction["checks"]},
            "wheel": reproduction["wheel"],
            "determinism": reproduction["determinism"],
            "wheel_tests": reproduction["wheel_tests"],
            "missing_module_falsification": reproduction["missing_module_falsification"],
            "suites": {n: {k: s.get(k) for k in ("exit", "passed", "failed", "skipped", "summary")}
                       for n, s in suites["suites"].items()},
            "sprint10_mutations": {k: matrix.get(k) for k in (
                "control", "written", "killed", "requested_total", "survivors", "stale")}
            | {"invalid_mutations": sorted(matrix.get("not_applicable", {}))},
            "certified_79": {
                "control": "GREEN" if log_bytes.startswith(b"CONTROL GREEN") else "NOT GREEN",
                "total": 79, "killed": 79, "survivors": 0,
                "log_sha256": sha256_bytes(log_bytes), "log_bytes": len(log_bytes),
            },
            "ei_ri_fm_sp": {
                "status": "CARRIED_FORWARD",
                "figures": "EI 10/10, RI 11/12 (RI2b known equivalent), FM 8/8, SP 10/10",
                "last_measured": "Sprint 7, benchmarks/core_v2_recertification",
                "justification": (
                    "src/ is byte-identical between the Sprint 10 close and this "
                    f"candidate (git diff --name-only {FINAL_FREEZE_BASELINE[:12]} "
                    f"{candidate[:12]} -- src is "
                    f"{'EMPTY' if not src_changed_since_sprint10 else 'NOT EMPTY'}), "
                    "so Sprint 10's justification holds a fortiori: nothing these "
                    "families mutate could have moved. The harness that measured "
                    "them was kept outside the repository and cannot be re-run from "
                    "tracked files; Core Freeze V1 therefore rests on nothing from "
                    "these families."
                ),
                "src_diff_since_sprint10_empty": not src_changed_since_sprint10,
            },
            "domain": {k: domain.get(k) for k in (
                "domain_start_digest", "domain_end_digest", "digests_identical",
                "git_diff_empty", "all_suites_green", "boundary_intact")},
        },
        "environment_informational": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }


# =====================================================================
# CLI
# =====================================================================

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--build", action="store_true",
                        help="write the contract manifest from the live tree")
    parser.add_argument("--record-assurance", action="store_true")
    parser.add_argument("--candidate", help="the assured candidate commit")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    root = repo_root(pathlib.Path(__file__).resolve().parent)

    if args.build:
        live = collect_live(root)
        if not live.clean and not args.allow_dirty:
            raise SystemExit("refusing to build a freeze manifest from a dirty tree")
        manifest = build_manifest(live)
        (root / MANIFEST_PATH).write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(f"wrote {MANIFEST_PATH}")
        print(f"  frozen digest {manifest['api']['frozen_digest']}")
        print(f"  src tree      {manifest['trees']['src']}")
        return 0

    if args.record_assurance:
        if not args.candidate:
            raise SystemExit("--record-assurance needs --candidate <commit>")
        candidate = git(root, "rev-parse", args.candidate)
        record = record_assurance(root, candidate)
        (root / ASSURANCE_PATH).write_bytes(
            json.dumps(record, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(f"wrote {ASSURANCE_PATH} for candidate {candidate}")
        return 0

    result = verify(root, require_clean=not args.allow_dirty)
    print(result.render())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
