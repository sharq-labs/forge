"""Which changes require hardened-core recertification -- decided in one place.

    python -m tools.certification.recertification_scope classify \\
        --event pull_request --base <sha> --head <sha> [--github-output FILE]
    python -m tools.certification.recertification_scope explain <path> ...
    python -m tools.certification.recertification_scope self-checks --format node-ids
    python -m tools.certification.recertification_scope verify-junit <junit.xml>
    python -m tools.certification.recertification_scope gate --workflow tests \\
        --mode <mode> --event <event> --needs-json '<toJSON(needs)>'

WHY THIS IS PYTHON AND NOT A PATH FILTER
---------------------------------------
Ownership used to be written twice: as a GitHub ``on.pull_request.paths``
filter in the recertify workflow and as a shell ``case`` in the Tests workflow.
Neither list contained ``src/engcore/domains/__init__.py``,
``src/engcore/data/**``, ``src/engcore/adequacy/**`` or
``src/engcore/inference/**`` -- four areas the certificate itself certifies. A
change to the registry that decides whether a threshold set is declared would
have run the ordinary suite and merged with the old certificate. The two
wildcard dialects (GitHub's ``**`` and bash's ``*``, which does cross ``/``)
also meant that "the lists agree" was not a checkable statement.

Now both workflows call :func:`classify`, which derives its triggers from
:data:`tools.certification.core_certificate.SCOPE` at call time, so a scope
area cannot be added without also becoming a recertification trigger.

THE MATCHING SEMANTICS, EXACTLY
-------------------------------
Paths are repository-relative with POSIX separators, compared case-sensitively
(Git paths are). A pattern is split on ``/`` and matched segment by segment:

* ``**`` matches zero or more whole segments;
* a ``**`` that is the LAST segment matches one or more segments -- any file
  below that directory;
* any other segment is an :func:`fnmatch.fnmatchcase` pattern, so ``*`` and
  ``?`` never cross a ``/``.

For every pattern in ``SCOPE`` this agrees with :meth:`pathlib.Path.glob`, which
is how the certificate enumerates files; ``tests/test_recertification_scope.py``
checks that against a real directory tree rather than asserting it.

Triggers are WIDER than scope, never narrower. A scope pattern is widened at
its first wildcard segment to ``<prefix>/**``: ``src/engcore/scientific/**/*.py``
triggers on any file below ``src/engcore/scientific/``, because a data file or a
``py.typed`` beside certified modules can change what they do without being in
the manifest. Paths outside scope that still decide what a gate's PASS means
(the stored certificate, the suites, the trust-mutation population and the
dependency manifest) are :data:`ADDITIONAL_TRIGGERS`, each with its reason.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping, Sequence

from tools.certification import core_certificate
from tools.certification.core_certificate import ScopeArea, repo_root

CERTIFICATE_PATH = "certification/current_core_v2.json"

#: The subject the certify job writes. It SELECTS the lightweight path; it does
#: not grant trust. A commit carrying it must also have the certificate-child
#: shape (one parent, only the certificate changed), and the child jobs then
#: verify lineage and provenance before anything is believed.
CERTIFICATE_CHILD_SUBJECT = "certification: recertify hardened core"

#: Ownership modes, as both workflows read them.
FULL_SUITE = "full_suite"            # a push or a manual run: the normal suite
ORDINARY = "ordinary"                # a pull request that touches nothing certified
RECERTIFY_SOURCE = "recertify_source"  # a pull request that must be recertified
CERTIFICATE_CHILD = "certificate_child"  # the certify job's certificate-only child
MODES = (FULL_SUITE, ORDINARY, RECERTIFY_SOURCE, CERTIFICATE_CHILD)


@dataclass(frozen=True)
class Trigger:
    """A named reason a changed path requires recertification."""

    name: str
    patterns: tuple[str, ...]
    why: str


#: Paths outside the certificate's scope whose change still has to be measured
#: again before a certificate may be believed. Evaluated and chosen, not
#: collected: see :data:`EVALUATED_AND_EXCLUDED` for what was left out and why.
ADDITIONAL_TRIGGERS: tuple[Trigger, ...] = (
    Trigger(
        "stored_certificate",
        (CERTIFICATE_PATH,),
        "a certificate may only change in a certificate-only child written by "
        "the certify job; any other edit to it is replaced by a builder-produced "
        "one after the gates run again",
    ),
    Trigger(
        "trusted_execution_runtime",
        (
            "src/engcore/execution/**",
            "src/engcore/extensions.py",
            "src/engcore/uq/cross_domain.py",
        ),
        "the trust-boundary runtime the trust-hardening mutation population "
        "mutates and its suites exercise; 'survived 0' is a claim about these "
        "bytes",
    ),
    Trigger(
        "assurance_suites",
        ("tests/**",),
        "every source gate's result is a claim about the suites it ran. A "
        "changed or deleted test changes what FAST, SCIENTIFIC and each "
        "mutation kill mean, whether or not it is pinned by the certificate",
    ),
    Trigger(
        "trust_hardening_population",
        ("benchmarks/trust_hardening/**",),
        "the trust-hardening mutation population and its runner, re-executed "
        "by the trust_mutations gate",
    ),
    Trigger(
        "dependency_manifest",
        ("pyproject.toml",),
        "every gate runs pip install -e .[dev,mcp,oracles] from this file, and "
        "pytest reads its configuration from it: a dependency bound, an extra "
        "or a pythonpath change alters the runtime the certificate was measured "
        "under without touching certified source",
    ),
)

#: Files that were evaluated as dependency or runtime inputs and deliberately
#: NOT made triggers. Recorded so the next reader argues with a reason rather
#: than rediscovers a gap.
EVALUATED_AND_EXCLUDED: tuple[tuple[str, str], ...] = (
    ("requirements.txt",
     "no gate installs from it. Every workflow installs from pyproject.toml; "
     "the Dockerfile copies it into the image and installs nothing from it"),
    ("Dockerfile",
     "builds the reproduce image, which runs only on pushes to main and never "
     "in a source gate or the certify job"),
    (".github/workflows/trust-mutations.yml",
     "an advisory standalone run. The recertify workflow re-executes the same "
     "population itself, so the certificate never rests on this workflow"),
)

#: The certificate/freeze self-checks. On a source commit they read the
#: PREVIOUS certificate, which by construction does not describe the new tree,
#: so the source gates deselect exactly these and the certificate child runs
#: exactly these. One list, so the two sides cannot drift.
CERTIFICATE_SELF_CHECKS: tuple[str, ...] = (
    "tests/test_core_certificate.py::test_the_certificate_describes_this_tree",
    "tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully",
    "tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1",
    "tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies",
    # I-29 (R-65, finding 89): the checks that compare the tree against a PINNED API ARTIFACT of the
    # previous freeze. A freeze changes those artifacts, so on the source commit of a recertifying
    # change every one of them reads the artifact of the tree BEFORE the change -- which is the same
    # construction as the four above, and is why finding 89 says recertification is impossible
    # without a control-plane change: nineteen of these failed for fifty-five batches and no source
    # gate could go green. They are deselected in the source gates and run by the certificate child,
    # which requires each to be reported PASSED in JUnit, so deferring is not skipping.
    "tests/test_core_api_snapshot.py::test_the_public_api_matches_the_pinned_snapshot",
    "tests/test_core_api_snapshot.py::test_parameter_kinds_and_defaults_are_unchanged",
    "tests/test_core_api_snapshot.py::test_enum_members_and_values_are_unchanged",
    "tests/test_core_api_snapshot.py::test_public_dataclass_fields_keep_their_order",
    "tests/test_core_api_snapshot.py::test_every_default_factory_is_identified_by_name",
    "tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes",
    "tests/test_core_freeze_policy.py::test_the_policy_states_the_real_frozen_digest",
    "tests/test_core_freeze_v2_manifest.py::test_the_v2_frozen_api_surface_is_superseded_additively",
    "tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks",
    "tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree",
    "tests/test_core_freeze_v3_manifest.py::test_the_identity_references_are_refused_in_a_fresh_process_too",
    "tests/test_core_freeze_v3_manifest.py::test_the_command_line_verifier_agrees_with_the_function",
    "tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract",
    "tests/test_core_freeze_v4_manifest.py::test_the_command_line_verifier_agrees_with_the_function",
    "tests/test_core_v2_api_snapshot.py::test_the_live_v2_frozen_surface_matches_the_pinned_snapshot",
    "tests/test_core_v2_api_snapshot.py::test_the_live_v2_full_surface_matches_the_pinned_snapshot",
    "tests/test_core_v2_compatibility.py::test_the_v1_surface_is_the_v1_contract_plus_only_additive_changes",
    "tests/test_core_v2_compatibility.py::test_every_v1_frozen_entry_is_byte_identical_inside_the_v2_surface",
)


class OwnershipError(RuntimeError):
    """The change cannot be classified, so nothing may run as if it had been."""


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------
def _is_wild(segment: str) -> bool:
    return any(ch in segment for ch in "*?[")


def match(pattern: str, path: str) -> bool:
    """Does repository-relative ``path`` match ``pattern``? See the module docstring."""
    return _match(tuple(pattern.split("/")), tuple(path.split("/")))


@lru_cache(maxsize=4096)
def _match(pattern: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        if not rest:
            return len(parts) >= 1
        return any(_match(rest, parts[index:]) for index in range(len(parts) + 1))
    if not parts:
        return False
    return fnmatch.fnmatchcase(parts[0], head) and _match(rest, parts[1:])


def widen(pattern: str) -> str:
    """The trigger for a scope pattern: truncated at its first wildcard to ``/**``."""
    segments = pattern.split("/")
    for index, segment in enumerate(segments):
        if _is_wild(segment):
            return "/".join([*segments[:index], "**"])
    return pattern


def scope_triggers(scope: Sequence[ScopeArea] | None = None) -> tuple[Trigger, ...]:
    """One trigger per certificate scope area, read from ``SCOPE`` at call time."""
    areas = core_certificate.SCOPE if scope is None else scope
    return tuple(
        Trigger(
            f"certified:{area.name}",
            tuple(dict.fromkeys(widen(pattern) for pattern in area.patterns)),
            f"in certificate scope area {area.name!r} ({area.classification})",
        )
        for area in areas
    )


#: Where the two mutation populations live, relative to the repository root.
FORMAL_MUTATION_HARNESS = "tests/mutation_guards.py"
TRUST_MUTATION_POPULATION = "benchmarks/trust_hardening/audit/mutations.py"


def _formal_mutation_targets(source: str) -> tuple[str, ...]:
    """Files named by ``MUTATIONS`` in the formal harness, read without running it."""
    import ast

    tree = ast.parse(source)
    for node in tree.body:
        target = getattr(node, "target", None)
        targets = [target] if target is not None else list(getattr(node, "targets", ()))
        if any(isinstance(t, ast.Name) and t.id == "MUTATIONS" for t in targets):
            entries = ast.literal_eval(node.value)
            # A spec may name a scope inside the file: ``path::qualname``.
            return tuple(entry[1].split("::", 1)[0] for entry in entries)
    raise OwnershipError(f"{FORMAL_MUTATION_HARNESS} defines no MUTATIONS")


def _trust_mutation_targets(source: str) -> tuple[str, ...]:
    """Files named by ``Mutation(...)`` entries in the trust population."""
    import ast

    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Mutation"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            found.append(node.args[1].value)
    if not found:
        raise OwnershipError(f"{TRUST_MUTATION_POPULATION} defines no Mutation entries")
    return tuple(found)


@lru_cache(maxsize=4)
def _mutation_targets(root: str) -> tuple[str, ...]:
    base = pathlib.Path(root)
    formal = _formal_mutation_targets(
        (base / FORMAL_MUTATION_HARNESS).read_text(encoding="utf-8-sig")
    )
    trust = _trust_mutation_targets(
        (base / TRUST_MUTATION_POPULATION).read_text(encoding="utf-8-sig")
    )
    return tuple(sorted(set(formal) | set(trust)))


def mutation_target_triggers(root: pathlib.Path | None = None) -> tuple[Trigger, ...]:
    """Every file a certified mutation population mutates is a trigger.

    A certificate that reports "N/N killed" is a claim about the guards at the
    lines those mutations remove. Before this trigger, 26 formal mutations
    targeted files that were neither in scope nor a trigger, so a pull request
    editing only one of those guards was classified ordinary and the
    certificate still verified. Derived from the populations at call time, so
    a new mutation cannot name a file outside recertification.
    """
    targets = _mutation_targets(str((root or repo_root()).resolve()))
    return (
        Trigger(
            "mutation_targets",
            targets,
            "a file a certified mutation population mutates: the kill count in "
            "the certificate is a claim about the guards in these bytes",
        ),
    )


def triggers(scope: Sequence[ScopeArea] | None = None) -> tuple[Trigger, ...]:
    return (*scope_triggers(scope), *ADDITIONAL_TRIGGERS, *mutation_target_triggers())


def recertification_reasons(
    path: str, scope: Sequence[ScopeArea] | None = None
) -> tuple[str, ...]:
    """The names of every trigger ``path`` hits. Empty means ordinary."""
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return tuple(
        trigger.name
        for trigger in triggers(scope)
        if any(match(pattern, normalized) for pattern in trigger.patterns)
    )


def requires_recertification(path: str, scope: Sequence[ScopeArea] | None = None) -> bool:
    return bool(recertification_reasons(path, scope))


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def _git(root: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape",
    )
    if done.returncode != 0:
        raise OwnershipError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _rev(root: pathlib.Path, ref: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _names(output: str) -> set[str]:
    return {name for name in output.split("\0") if name}


def changed_paths(root: pathlib.Path, base: str, head: str) -> tuple[str, ...]:
    """Every path a pull request can be said to change, over-approximated.

    The union of the direct diff (base tip to head) and the pull request's own
    diff (merge base to head). Either alone misses a case: the direct diff hides
    a path both sides changed identically, and the merge-base diff hides a path
    only the base changed that the head's tree still disagrees with. Extra paths
    only ever cause extra recertification.
    """
    merge_base = _git(root, "merge-base", base, head).strip()
    if not merge_base:
        raise OwnershipError(f"{base} and {head} share no history; refusing to guess")
    direct = _names(_git(root, "diff", "--name-only", "--no-renames", "-z", base, head))
    own = _names(_git(root, "diff", "--name-only", "--no-renames", "-z", merge_base, head))
    return tuple(sorted(direct | own))


def certificate_child_problems(root: pathlib.Path, head: str) -> list[str]:
    """Why ``head`` is not a well-formed certificate-only child. Empty means it is.

    Shape only. Lineage (the certificate names this exact parent) and
    provenance (the certify job for that parent produced these bytes) are
    :mod:`tools.certification.certificate_lineage`'s job.
    """
    problems: list[str] = []
    subject = _git(root, "log", "-1", "--format=%s", head).strip()
    if subject != CERTIFICATE_CHILD_SUBJECT:
        problems.append(
            f"subject is {subject!r}, not the reserved {CERTIFICATE_CHILD_SUBJECT!r}"
        )
    parents = _git(root, "rev-list", "--parents", "-n", "1", head).split()[1:]
    if len(parents) != 1:
        problems.append(
            f"a certificate child has exactly one parent; {head} has {len(parents)}"
        )
        return problems
    fields = [item for item in _git(
        root, "diff", "--name-status", "--no-renames", "-z", parents[0], head
    ).split("\0") if item]
    entries = list(zip(fields[0::2], fields[1::2]))
    if entries != [("M", CERTIFICATE_PATH)] and entries != [("A", CERTIFICATE_PATH)]:
        shown = ", ".join(f"{status} {path}" for status, path in entries) or "<none>"
        problems.append(
            f"a certificate child adds or modifies {CERTIFICATE_PATH} and nothing "
            f"else; this one changes: {shown}"
        )
    return problems


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ownership:
    """Who owns the assurance for one workflow event, and why."""

    event: str
    mode: str
    head: str = ""
    base: str = ""
    source_commit: str = ""
    certificate_commit: str = ""
    changed: tuple[str, ...] = ()
    reasons: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def outputs(self) -> dict[str, str]:
        """The values both workflows read from ``$GITHUB_OUTPUT``."""
        return {
            "mode": self.mode,
            "recertification": {
                RECERTIFY_SOURCE: "source",
                CERTIFICATE_CHILD: "certificate_child",
            }.get(self.mode, "not_required"),
            "delegate_to_recertify": "true" if self.mode == RECERTIFY_SOURCE else "false",
            "certificate_child": "true" if self.mode == CERTIFICATE_CHILD else "false",
            "source_sha": self.source_commit,
            "certificate_sha": self.certificate_commit,
        }

    def render(self) -> str:
        lines = [f"event {self.event}: {self.mode}"]
        if self.mode == CERTIFICATE_CHILD:
            lines.append(
                f"certificate-only child {self.certificate_commit} of source "
                f"{self.source_commit}; lineage and provenance are verified by "
                f"the child jobs"
            )
        for path, names in sorted(self.reasons.items()):
            lines.append(f"  RECERTIFY {path}: {', '.join(names)}")
        if self.mode == ORDINARY:
            lines.append(
                f"  {len(self.changed)} changed path(s), none certified or "
                f"trust-sensitive: the normal Tests workflow owns this change"
            )
        return "\n".join(lines)


def classify(
    root: pathlib.Path,
    *,
    event: str,
    head: str | None = None,
    base: str | None = None,
    scope: Sequence[ScopeArea] | None = None,
) -> Ownership:
    """Classify one workflow event. Raises :class:`OwnershipError` rather than guess."""
    if event != "pull_request":
        return Ownership(event=event, mode=FULL_SUITE)
    if not head or not base:
        raise OwnershipError("a pull_request classification needs --head and --base")
    head_sha, base_sha = _rev(root, head), _rev(root, base)

    subject = _git(root, "log", "-1", "--format=%s", head_sha).strip()
    if subject == CERTIFICATE_CHILD_SUBJECT:
        problems = certificate_child_problems(root, head_sha)
        if problems:
            raise OwnershipError(
                "the reserved recertification subject is used by a commit that "
                "is not a certificate-only child: " + "; ".join(problems)
            )
        parent = _git(root, "rev-parse", f"{head_sha}^").strip()
        return Ownership(
            event=event, mode=CERTIFICATE_CHILD, head=head_sha, base=base_sha,
            source_commit=parent, certificate_commit=head_sha,
            changed=(CERTIFICATE_PATH,),
        )

    changed = changed_paths(root, base_sha, head_sha)
    reasons = {
        path: names
        for path in changed
        if (names := recertification_reasons(path, scope))
    }
    return Ownership(
        event=event,
        mode=RECERTIFY_SOURCE if reasons else ORDINARY,
        head=head_sha, base=base_sha,
        source_commit=head_sha if reasons else "",
        changed=changed, reasons=reasons,
    )


# ---------------------------------------------------------------------------
# the deferred self-checks, verified by result rather than by exit code
# ---------------------------------------------------------------------------
def _junit_key(node_id: str) -> tuple[str, str]:
    module, _, name = node_id.partition("::")
    return module.removesuffix(".py").replace("/", "."), name


def junit_problems(
    xml_bytes: bytes, expected: Sequence[str] = CERTIFICATE_SELF_CHECKS
) -> list[str]:
    """Why a JUnit report does not show EXACTLY ``expected``, each one passed.

    Pytest exits 0 when a test is skipped, so an exit code cannot tell "the
    certificate describes this tree" from "a hook skipped the test that asks".
    Every expected node must appear once with no failure, error or skip, and
    nothing else may appear.
    """
    try:
        document = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        return [f"the JUnit report does not parse: {exc}"]
    seen: dict[tuple[str, str], list[str]] = {}
    for case in document.iter("testcase"):
        key = (case.get("classname", ""), case.get("name", ""))
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = child.tag
        seen.setdefault(key, []).append(outcome)
    wanted = {_junit_key(node): node for node in expected}
    problems: list[str] = []
    for key, node in sorted(wanted.items()):
        outcomes = seen.get(key)
        if not outcomes:
            problems.append(f"{node}: not reported")
        elif outcomes != ["passed"]:
            problems.append(f"{node}: {', '.join(outcomes)}")
    unexpected = sorted(set(seen) - set(wanted))
    if unexpected:
        problems.append(
            "unexpected test cases in a self-check run: "
            + ", ".join(f"{cls}::{name}" for cls, name in unexpected)
        )
    return problems


# ---------------------------------------------------------------------------
# aggregate gates -- the checks branch protection should require
# ---------------------------------------------------------------------------
#: A required status check that is SKIPPED counts as passing on GitHub. Every
#: job in both workflows is conditional, so requiring any one of them lets a
#: head through on the path where that job does not run -- requiring only
#: ``verify_certificate_child`` passes a core source commit whose certify job
#: failed, because on a source commit that job is skipped. Each workflow
#: therefore ends in an unconditional gate job that knows which jobs had to
#: succeed for the mode it was classified in, and branch protection requires
#: the gates.
RECERTIFY_SOURCE_GATES = (
    "fast311", "fast312", "scientific312", "campaign312", "regression312",
    "formal_mutations_0", "formal_mutations_1", "formal_mutations_2",
    "formal_mutations_3", "trust_mutations",
)
RECERTIFY_JOBS = ("classify", *RECERTIFY_SOURCE_GATES, "certify", "verify_certificate_child")
TESTS_ORDINARY_JOBS = ("repo-layout", "fast", "mutations", "scientific")
TESTS_JOBS = ("scope", *TESTS_ORDINARY_JOBS, "certificate-child")


def _results(needs: Mapping[str, Any], names: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    results: dict[str, str] = {}
    problems: list[str] = []
    for name in names:
        entry = needs.get(name)
        if not isinstance(entry, Mapping) or "result" not in entry:
            problems.append(f"job {name!r} is not among the gate's needs")
            continue
        results[name] = str(entry["result"])
    return results, problems


def _require(results: Mapping[str, str], names: Sequence[str], state: str) -> list[str]:
    return [
        f"job {name!r} is {results.get(name, '<absent>')}, expected {state}"
        for name in names
        if results.get(name) != state
    ]


def recertification_gate_problems(recertification: str, needs: Mapping[str, Any]) -> list[str]:
    """Why the recertify workflow's gate must fail. Empty means it passes."""
    results, problems = _results(needs, RECERTIFY_JOBS)
    if problems:
        return problems
    problems += _require(results, ("classify",), "success")
    others = [name for name in RECERTIFY_JOBS if name != "classify"]
    if recertification == "not_required":
        problems += _require(results, others, "skipped")
    elif recertification == "source":
        problems += _require(
            results,
            (*RECERTIFY_SOURCE_GATES, "certify", "verify_certificate_child"),
            "success",
        )
    elif recertification == "certificate_child":
        problems += _require(results, ("verify_certificate_child",), "success")
    else:
        problems.append(f"unknown recertification mode {recertification!r}")
    return problems


def tests_gate_problems(mode: str, needs: Mapping[str, Any], *, event: str) -> list[str]:
    """Why the Tests workflow's gate must fail. Empty means it passes."""
    results, problems = _results(needs, TESTS_JOBS)
    if problems:
        return problems
    problems += _require(results, ("scope", "repo-layout"), "success")
    if mode in (FULL_SUITE, ORDINARY):
        problems += _require(results, ("fast", "mutations", "scientific"), "success")
    elif mode == RECERTIFY_SOURCE:
        # The ordinary suite is deliberately not run here: the recertify
        # workflow's gate owns this head, and requiring both gates is what
        # stops this branch from passing on its own.
        problems += _require(results, ("fast", "mutations", "scientific", "certificate-child"), "skipped")
    elif mode == CERTIFICATE_CHILD:
        problems += _require(results, ("certificate-child",), "success")
    else:
        problems.append(f"unknown ownership mode {mode!r}")
    if event == "pull_request" and mode == FULL_SUITE:
        problems.append("a pull_request event can never be classified full_suite")
    return problems


# ---------------------------------------------------------------------------
def _write_outputs(path: str | None, outputs: Mapping[str, str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    one = commands.add_parser("classify")
    one.add_argument("--event", required=True)
    one.add_argument("--head")
    one.add_argument("--base")
    one.add_argument("--github-output")

    explain = commands.add_parser("explain")
    explain.add_argument("paths", nargs="+")

    checks = commands.add_parser("self-checks")
    checks.add_argument("--format", choices=("node-ids", "deselect"), required=True)

    junit = commands.add_parser("verify-junit")
    junit.add_argument("report")

    gate = commands.add_parser("gate")
    gate.add_argument("--workflow", choices=("recertify", "tests"), required=True)
    gate.add_argument("--mode", required=True)
    gate.add_argument("--event", default="pull_request")
    gate.add_argument("--needs-json", required=True)

    args = parser.parse_args(argv)
    root = repo_root(pathlib.Path.cwd() / "x")

    if args.command == "classify":
        try:
            ownership = classify(root, event=args.event, head=args.head, base=args.base)
        except OwnershipError as exc:
            print(f"OWNERSHIP ERROR: {exc}", file=sys.stderr)
            return 1
        print(ownership.render())
        _write_outputs(args.github_output, ownership.outputs())
        return 0

    if args.command == "explain":
        for path in args.paths:
            names = recertification_reasons(path)
            print(f"{'RECERTIFY' if names else 'ordinary '} {path}"
                  + (f"  ({', '.join(names)})" if names else ""))
        return 0

    if args.command == "self-checks":
        for node in CERTIFICATE_SELF_CHECKS:
            print(f"--deselect\n{node}" if args.format == "deselect" else node)
        return 0

    if args.command == "verify-junit":
        problems = junit_problems(pathlib.Path(args.report).read_bytes())
        for problem in problems:
            print(f"SELF-CHECK PROBLEM: {problem}")
        print("OK" if not problems else "FAILED")
        return 0 if not problems else 1

    needs = json.loads(args.needs_json)
    if args.workflow == "recertify":
        problems = recertification_gate_problems(args.mode, needs)
    else:
        problems = tests_gate_problems(args.mode, needs, event=args.event)
    for name, entry in sorted(needs.items()):
        print(f"  {name}: {entry.get('result') if isinstance(entry, Mapping) else entry}")
    for problem in problems:
        print(f"GATE PROBLEM: {problem}")
    print(f"{args.workflow} gate ({args.mode}): {'PASS' if not problems else 'FAIL'}")
    return 0 if not problems else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
