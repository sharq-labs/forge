"""The ngspice version probe names a provider only when the probe succeeded.

Review finding B4: ``NgspiceInvocation.probe_version`` read the banner without
looking at the exit status, so a process that printed ``ngspice-42`` and then
exited non-zero still produced a SolverIdentity; and a timed-out probe escaped
as ``subprocess.TimeoutExpired`` rather than as a provider failure. The rule is
now the provider catalog's executable-probe rule: exit 0 or no identity.

Every provider here is a one-line Python process, so these run without the
real ngspice and stay in the FAST tier.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from engcore.domains.electrical import ngspice as ng

BANNER = (
    "print('******'); "
    "print('** ngspice-42 : Circuit level simulation program')"
)


def _invocation(script: str, timeout: float = 20.0) -> ng.NgspiceInvocation:
    return ng.NgspiceInvocation(
        command=(sys.executable, "-c", script), timeout_seconds=timeout
    )


def _no_identity(invocation: ng.NgspiceInvocation, error: type[Exception]):
    solver = ng.NgspiceDCSolver(invocation=invocation)
    with pytest.raises(error) as caught:
        solver.identity
    # Nothing was cached: a later read probes again rather than reusing a
    # version the failed probe printed.
    assert solver._version is None
    return caught.value


@pytest.mark.parametrize("code", [1, 2, 3, 255])
def test_a_plausible_banner_with_a_non_zero_exit_forms_no_identity(code) -> None:
    invocation = _invocation(f"import sys; {BANNER}; sys.exit({code})")
    with pytest.raises(ng.NgspiceExecutionFailure, match=f"exited {code}"):
        invocation.probe_version()
    _no_identity(invocation, ng.NgspiceExecutionFailure)


def test_a_timed_out_probe_is_a_provider_failure_not_a_subprocess_error() -> None:
    invocation = _invocation(f"import time; {BANNER}; time.sleep(60)", timeout=1.0)
    error = _no_identity(invocation, ng.NgspiceExecutionFailure)
    assert isinstance(error, ng.NgspiceProviderError)
    assert not isinstance(error, subprocess.TimeoutExpired)
    assert "did not return" in str(error)


def test_a_missing_executable_is_unavailable() -> None:
    invocation = ng.NgspiceInvocation(
        command=("forge-no-such-ngspice-executable-b4",), timeout_seconds=5.0
    )
    _no_identity(invocation, ng.NgspiceUnavailable)


def test_a_clean_exit_with_a_banner_names_the_provider() -> None:
    solver = ng.NgspiceDCSolver(invocation=_invocation(BANNER))
    identity = solver.identity
    assert identity.version == "42"
    assert identity.solver_id == ng.NGSPICE_SOLVER_ID
    assert identity.backend == "ngspice"


@pytest.mark.parametrize("script", [
    "print('ngspice version unknown')",
    "print('')",
    "import sys; sys.stderr.write('** ngspice-42 : on stderr only\\n')",
])
def test_a_clean_exit_without_a_recognisable_banner_forms_no_identity(script) -> None:
    _no_identity(_invocation(script), ng.NgspiceExecutionFailure)
