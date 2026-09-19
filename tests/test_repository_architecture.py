"""Repository-level dependency rules for the non-Core scientific-intelligence stack."""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore"


def _sibling_imports(package: str) -> list[tuple[pathlib.Path, str]]:
    root = SRC / package
    found: list[tuple[pathlib.Path, str]] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        depth = len(path.relative_to(root).parts) - 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) >= 2 and parts[0] == "engcore":
                        found.append((path, parts[1]))
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    parts = node.module.split(".")
                    if len(parts) >= 2 and parts[0] == "engcore":
                        found.append((path, parts[1]))
                elif node.level > depth + 1 and node.module:
                    found.append((path, node.module.split(".")[0]))
    return found


def test_claims_never_depends_on_mcp_transport():
    offenders = [str(p.relative_to(SRC)) for p, sibling in _sibling_imports("claims") if sibling == "mcp"]
    assert not offenders, "claims -> mcp is a layering inversion:\n  " + "\n  ".join(offenders)


def test_credibility_is_transport_independent():
    forbidden = {"mcp", "claims", "design", "domains", "systems"}
    offenders = [
        f"{p.relative_to(SRC)} -> {sibling}"
        for p, sibling in _sibling_imports("credibility")
        if sibling in forbidden
    ]
    assert not offenders, "credibility reaches an upper/non-authoritative layer:\n  " + "\n  ".join(offenders)


def test_legacy_mcp_credibility_imports_are_identity_preserving():
    from engcore.credibility.evidence import CredibilityEvidenceReport as canonical_report
    from engcore.credibility.sria_bridge import CredibilityReportCritic as canonical_critic
    from engcore.mcp.evidence import CredibilityEvidenceReport as legacy_report
    from engcore.mcp.sria_bridge import CredibilityReportCritic as legacy_critic
    assert legacy_report is canonical_report
    assert legacy_critic is canonical_critic


def test_claim_reorganization_keeps_legacy_import_identity():
    from engcore.claims.analysis.sensitivity import SensitivityReport as canonical_sensitivity
    from engcore.claims.sensitivity import SensitivityReport as legacy_sensitivity
    from engcore.claims.analysis.challenge import ChallengeReport as canonical_challenge
    from engcore.claims.challenge import ChallengeReport as legacy_challenge
    from engcore.claims.governance.policy import DecisionContext as canonical_context
    from engcore.claims.policy import DecisionContext as legacy_context
    from engcore.claims.replay.bundle import BundleStatus as canonical_bundle
    from engcore.claims.bundle import BundleStatus as legacy_bundle

    assert legacy_sensitivity is canonical_sensitivity
    assert legacy_challenge is canonical_challenge
    assert legacy_context is canonical_context
    assert legacy_bundle is canonical_bundle
