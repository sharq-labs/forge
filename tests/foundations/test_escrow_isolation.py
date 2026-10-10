"""Big Rock 2 (2G): a genuine isolated deployment -- or, where the host cannot build one, an honest refusal.

No skip: on a host that can create namespaces and switch uid (root, unshare, setpriv) the hostile proposer runs in the
Discovery domain and EVERY check must hold, establishing OS_ISOLATION_BOUNDARY_VERIFIED; anywhere else the launcher
must refuse and the status must stay SECURITY_BOUNDARY_NOT_PROVEN.  Neither branch can report a container or host
boundary.
"""

from __future__ import annotations

import pytest

from engcore.blindfold.isolation import (
    BOUNDARY_LEVELS,
    IsolatedEscrow,
    isolation_support,
    run_isolation_demo,
)


def test_the_isolated_deployment_reports_exactly_what_it_established(tmp_path):
    ok, why = isolation_support()
    report = run_isolation_demo(tmp_path / "iso")
    assert report["security_boundary_status"] in BOUNDARY_LEVELS
    assert report["security_boundary_status"] not in ("CONTAINER_BOUNDARY_VERIFIED", "HOST_BOUNDARY_VERIFIED")
    if not ok:
        assert report == {"security_boundary_status": "SECURITY_BOUNDARY_NOT_PROVEN", "isolation_available": False, "reason": why}
        with pytest.raises(RuntimeError, match="unavailable"):
            IsolatedEscrow(tmp_path / "store")
        return
    assert report["security_boundary_status"] == "OS_ISOLATION_BOUNDARY_VERIFIED", report["checks"]
    assert all(report["checks"].values()) and report["attacks_succeeded"] == [] and report["secrets_readable"] == []
    assert {"read_truth_path_0", "traverse_truth_path_0", "environment_has_secrets", "read_other_process_environ",
            "network_connect_out", "campaign_id_substitution", "universe_id_substitution", "credential_replay",
            "accept_replayed_old_response", "over_query_beyond_budget", "malformed_requests_accepted",
            "score_with_observe_capability"} <= set(report["attacks_run"])
    assert min(report["files_scanned_by_discovery"]) > 0                  # it really looked
    assert report["checks"]["launcher_verified_discovery_domain_run1"] and report["checks"]["launcher_verified_discovery_domain_run2"]
    assert len(report["escrow_key_id"]) == 64 and len(report["checks_digest"]) == 64   # bound to THIS escrow, these checks


def test_the_leak_detector_catches_a_planted_partial_copy(tmp_path):                               # checkpoint B M-5
    """Positive control: a world-readable PARTIAL copy of the journal must be found (canary substring) and must make
    the demo report NOT_PROVEN -- otherwise its clean result would prove nothing."""
    ok, _why = isolation_support()
    report = run_isolation_demo(tmp_path / "iso", leak_control=True)
    assert report["security_boundary_status"] == "SECURITY_BOUNDARY_NOT_PROVEN"
    if not ok:
        return
    assert report["checks"]["no_escrow_secret_readable"] is False
    assert any(s.startswith("canary in /tmp/forge-leak-control-") for s in report["secrets_readable"])
