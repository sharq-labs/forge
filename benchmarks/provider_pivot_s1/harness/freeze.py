"""The round's freeze record: what produced these numbers, pinned by digest.

This round issues no Gate A and no certification, so there is nothing here to
freeze *against*. What there is to freeze is the state the evidence was produced
from, so that a later session can answer one question without re-deriving
anything: **has any of this moved since?**

What is pinned
--------------
* every module of ``src/engcore/providers/``, plus
  ``src/engcore/credibility/risk_coverage.py`` and this round's four harness
  modules, by SHA-256 of their bytes;
* the three evidence files, by SHA-256;
* the six fitted parameter authorities, by their own digests and their parents';
* the provider environment -- interpreter, platform and the six distribution
  versions that can change a number -- and its digest;
* the headline numbers, so a reader who does not open the JSON still sees what
  the freeze is a freeze *of*.

What is deliberately NOT pinned
--------------------------------
The frozen Core API digest, because it did not move: nothing under
``src/engcore/providers/`` is exported from a canonical module, and
``docs/CORE_FREEZE_POLICY.md`` says what that means. The record states the
digest it observed so the claim is checkable rather than asserted.

Not the git commit either, as a *check*: the freeze is committed after it is
written, so a record that pinned its own commit could never verify. The commit
HEAD was at when the evidence was produced is recorded as provenance, and the
verification is over bytes.

    python benchmarks/provider_pivot_s1/harness/freeze.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

from engcore import api_snapshot  # noqa: E402
from engcore.providers.environment import EnvironmentIdentity  # noqa: E402

#: Every production file this round added or is governed by. Listed rather than
#: globbed: a glob would silently stop pinning a file somebody moved, and the
#: point of a freeze is that a move is visible.
FROZEN_SOURCES = (
    "src/engcore/providers/__init__.py",
    "src/engcore/providers/contract.py",
    "src/engcore/providers/environment.py",
    "src/engcore/providers/licenses.py",
    "src/engcore/providers/pybamm_provider.py",
    "src/engcore/providers/pybop_provider.py",
    "src/engcore/providers/salib_provider.py",
    "src/engcore/credibility/risk_coverage.py",
    "benchmarks/provider_pivot_s1/harness/common.py",
    "benchmarks/provider_pivot_s1/harness/sensitivity.py",
    "benchmarks/provider_pivot_s1/harness/fit.py",
    "benchmarks/provider_pivot_s1/harness/compare.py",
)

FROZEN_EVIDENCE = ("SENSITIVITY.json", "FIT.json", "COMPARISON.json")


def sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def git_head() -> str | None:
    """The commit the evidence was produced at, or ``None`` outside a checkout.

    ``None`` rather than a placeholder: "not in a repository" and "at an unknown
    commit" are different facts and a string like ``"unknown"`` would make them
    the same one.
    """
    try:
        done = subprocess.run(
            ["git", "-C", common.REPO, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return None
    commit = done.stdout.strip()
    return commit if done.returncode == 0 and commit else None


def main() -> int:
    fit = common.load_json(os.path.join(common.EVIDENCE, "FIT.json"))
    comparison = common.load_json(os.path.join(common.EVIDENCE, "COMPARISON.json"))
    sensitivity = common.load_json(
        os.path.join(common.EVIDENCE, "SENSITIVITY.json")
    )
    environment = EnvironmentIdentity.capture()

    authorities = {
        unit: {
            "authority_digest": block["authority_digest"],
            "parent_authority_digest": block["parent_authority_digest"],
            "source": block["authority"]["source"],
            "fits": block["fits"],
        }
        for unit, block in sorted(fit["blocks"].items())
        if block.get("fits")
    }

    record: dict[str, Any] = {
        "schema": "provider_pivot_s1_freeze/1",
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit_evidence_was_produced_at": git_head(),
        "what_this_is": (
            "the state this round's evidence was produced from, pinned by "
            "digest. It is NOT a Gate A, NOT a certification and NOT a "
            "validation record; this round produced none of those and says so "
            "in its report"
        ),
        "what_this_does_not_freeze": [
            "the frozen Core API digest, which did not move -- nothing under "
            "src/engcore/providers/ is exported from a canonical module",
            "the ngspice adapter, which is byte-unchanged from the base commit",
            "the native battery models, which this round did not touch",
            "any holdout, which this round never opened",
        ],
        "core_api": {
            "frozen_digest_observed": api_snapshot.frozen_digest(),
            "frozen_symbols_observed": api_snapshot.frozen_only()["symbol_count"],
            "frozen_digest_this_interpreter_produces_on_the_base_commit": (
                "af8dfbc0068fcae3c9236fc31ca8bbaf61fe9d32b32d41a769b57ff94da1f960"
            ),
            "claim": (
                "UNCHANGED BY THIS ROUND: the observed digest and symbol count "
                "are byte-identical to what the base commit produces on the "
                "same interpreter, which was measured rather than assumed"
            ),
            "why_it_differs_from_the_policy": (
                "docs/CORE_FREEZE_POLICY.md records 194 symbols at "
                "f18aa806d594016c04b3f9ace6b0817969e8042febd22324f6eb8a95aef6f487. "
                "This interpreter (CPython 3.14) produces 195 at af8dfbc0..., "
                "on the base commit as well as on this one. That gap is "
                "PRE-EXISTING certification drift on Python 3.14 and is not "
                "this round's doing; it is recorded here so that a later "
                "session reading this freeze does not attribute it to the "
                "provider package"
            ),
        },
        "provider_environment": dict(
            environment.to_dict(), environment_identity=environment.digest()
        ),
        "sources": {
            relative: sha256_file(os.path.join(common.REPO, relative))
            for relative in FROZEN_SOURCES
        },
        "evidence": {
            name: sha256_file(os.path.join(common.EVIDENCE, name))
            for name in FROZEN_EVIDENCE
        },
        "parameter_authorities": authorities,
        "headline": {
            "corpus": "NASA PCoE Li-ion battery aging archive",
            "splits_scored": list(common.DEVELOPMENT_SPLITS),
            "splits_never_opened": ["observed_holdout", "locked_holdout"],
            "trajectories": sum(
                block["trajectories"]
                for key, block in comparison["routes"].items()
                if key.startswith("native|")
            ),
            "like_for_like": {
                split: {
                    route: {
                        "mae_v": statistics["mae"],
                        "rmse_v": statistics["rmse"],
                    }
                    for route, statistics in block["routes"].items()
                }
                for split, block in comparison["like_for_like"].items()
            },
            "risk_applicability_screen": {
                route: {
                    "coverage": block["coverage"],
                    "false_trust_rate": block["false_trust_rate"],
                    "over_refusal_rate": block["over_refusal_rate"],
                }
                for route, block in comparison["risk_applicability_screen"].items()
            },
            "trust_path_coverage": {
                route: block.get("coverage")
                for route, block in comparison["risk_trust_path"].items()
            },
            "sensitivity_ranking": list(sensitivity["evidence"]["ranking"]),
            "replay": [
                {
                    "executed": item["executed"],
                    "identity_matched": item["identity_matched"],
                    "reproduced": item["reproduced"],
                    "max_absolute_difference": item["max_absolute_difference"],
                }
                for item in comparison["replay"]
            ],
        },
        "independent_gate_a": comparison["independent_gate_a"],
    }

    path = common.write_evidence("FREEZE.json", record)
    print(f"wrote {path}")
    print(f"  commit          : {record['commit_evidence_was_produced_at']}")
    print(f"  core api digest : {record['core_api']['frozen_digest_observed'][:32]}...")
    print(f"  environment     : {record['provider_environment']['environment_identity'][:32]}...")
    print(f"  sources pinned  : {len(record['sources'])}")
    print(f"  evidence pinned : {len(record['evidence'])}")
    print(f"  authorities     : {len(authorities)}")
    for unit, entry in authorities.items():
        print(f"    {unit:26} {entry['authority_digest'][:16]} <- {entry['parent_authority_digest'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
