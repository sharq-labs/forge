"""Put the challenge package on the path for this directory only."""

import pathlib
import sys

import pytest

BLIND_V2 = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BLIND_V2))


@pytest.fixture(autouse=True)
def _isolate_falsification_peeker_from_shared_checkout(request):
    """Run the frozen peeker proof outside the repository under xdist.

    ``challenge.audit`` is a frozen artifact and must stay byte-identical to the
    sealed Blind V2 challenge. Its falsification helper intentionally creates a
    temporary Python module next to the challenge package. During parallel test
    execution a repo-wide scanner can enumerate that file immediately before
    the helper removes it, yielding a FileNotFoundError unrelated to either
    trust check.

    Keep the frozen function and frozen test unchanged. For that one test only,
    redirect the module's package roots to an isolated temporary ``challenge``
    package. The original helper still writes the same peeker, and the original
    AST, transitive, string, and fresh-interpreter runtime audits still have to
    catch it; the shared checkout is simply no longer mutated.
    """
    if request.node.name != "test_the_audit_catches_a_module_that_peeks":
        return

    monkeypatch = request.getfixturevalue("monkeypatch")
    tmp_path = request.getfixturevalue("tmp_path")

    import challenge.audit as audit

    root = tmp_path / "blind-v2-falsification"
    package = root / "challenge"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(audit, "BLIND_V2", root)
    monkeypatch.setattr(audit, "PACKAGE", package)
