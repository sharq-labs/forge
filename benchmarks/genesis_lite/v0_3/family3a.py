"""Genesis-lite v0.3 D5, family 3a (BR-D5-RUNTIME-01; owner approval of 3a with a declared root launch, 2026-10-21):
the client side of the rootful crun per-card runtime. It starts a card only through the root helper.

The spike (``docs/discovery/GENESIS_LITE_V0_3_D5_RUNTIME_SELECTION_SPIKE.md``) selected one fresh rootful crun 1.14.1
container per card, inside the formal WSL2 VM. The card's ``/dev`` is a private tmpfs built for that card, holding
mknod'd ``null``, ``zero`` and ``full`` only; the other three nodes of :data:`.device_contract.DEVICES` are absent.
This module holds:

* :class:`RuntimeConfig`: the typed runtime configuration. Identity values that have not been measured on the formal
  machine are :data:`UNPINNED` and block; nothing is defaulted. The policy fields cannot be widened.
* :class:`Family3aLauncher` and :class:`CardSpec`: the launcher interface. A card names one of :data:`ENTRYPOINTS`,
  never a command line.
* :class:`RootHelper`: the strict root-helper contract. Its only input is a validated helper request
  (:func:`helper_request`); it has no argv, command, shell or script field. :class:`WslRootHelper` reaches the
  low-level helper (:mod:`.family3a_helper`, pinned by its sha256) through the declared root launch; where that launch
  does not exist, :class:`UnimplementedRootHelper` refuses every call as :data:`ROOT_HELPER_NOT_IMPLEMENTED`.
* Device Contract v2 and the versioned evidence schema (:data:`EVIDENCE_SCHEMA`), with a validator that re-derives
  every node's result from raw records (:func:`validate_evidence`) and never trusts a stored verdict.
* :func:`pre_admission` (ordered, stops at the first failing stage, never sees a root or a registry) and
  :func:`execution_readiness` (fail closed).

Device Contract v2, per node of BLOCKER 1's scope:

* ``null``, ``zero``, ``full``: PRIVATE_TO_CARD when, in every card, the node is a character device with its exact
  major:minor and mode 0666 on that card's own ``/dev`` tmpfs (never the host devtmpfs), and its ctime and mtime fall
  inside the card's own launch window. Cards are separated by at least :data:`COARSE_CLOCK_NS`, so a node left by an
  earlier card cannot pass. In every selected-bit trial the decoder must not see the encoder's timestamp (the
  :data:`DETECTOR`). The same detector on the deliberately shared-tmpfs control (:data:`POWER_CONTROL`) must recover
  every bit. **Identity never uses st_dev/st_ino equality across cards:** sequential cards reuse them.
* the other three: ABSENT when, in every card, they are missing from ``/dev`` and open and stat give ENOENT.
* every card: no devtmpfs mount and no mount from the host devtmpfs (which also catches a mask bound from the host
  ``/dev/null``), no shared or slave propagation, and a walk that finds no device node.

What is NOT claimed: nothing here is D5 evidence. Synthetic records pass the validator; no card has run. D5 stays
NOT_PROVEN, and BLOCKER 1 stays open until a declared detector and pinned MEASURED evidence close it in
:mod:`.readiness`. This module is not yet on the formal path (:func:`.formal.deployment_problems`) and is not in the
preregistration's ``V0_3_FILES``.

    python -m benchmarks.genesis_lite.v0_3.family3a      # read-only: prints execution_readiness()
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping, Protocol

from . import device_contract, isolation

DEPLOYMENT = "rootful_crun_per_card"
CONFIG_SCHEMA = "forge.genesis_lite.v0_3/family3a_runtime_config/1"
HELPER_REQUEST_SCHEMA = "forge.genesis_lite.v0_3/family3a_helper_request/1"
HELPER_RESULT_SCHEMA = "forge.genesis_lite.v0_3/family3a_helper_result/1"
EVIDENCE_SCHEMA = "forge.genesis_lite.v0_3/family3a_evidence/1"
DEVICE_CONTRACT = "forge.genesis_lite.v0_3/stateless_device/2"
#: BLOCKER 1's mechanism (spike section 2): utimensat(UTIME_NOW) by an encoder card, stat by a fresh decoder card
DETECTOR = "utimensat_timestamp_selected_bit/1"
UNPINNED = "UNPINNED"
RUNTIME_NAME, RUNTIME_VERSION = "crun", "1.14.1"
#: the owner's declared operator action (spike section 6, stop condition S6)
ROOT_LAUNCH = "wsl.exe -u root"

# ---- statuses and reasons -------------------------------------------------------------------------------------------
READY, BLOCKED = "READY_FOR_FAMILY_3A_EXECUTION", "BLOCKED_WITH_PRECISE_EVIDENCE"
ADMISSIBLE, REFUSED = "ADMISSIBLE", "REFUSED"
PASS, CHECK_BLOCKED, NOT_REACHED = "PASS", "BLOCKED", "NOT_REACHED"
MEASURED, NOT_MEASURED = "MEASURED", "NOT_MEASURED_BY_CURRENT_DETECTOR"     # readiness's evidence types
PRIVATE_TO_CARD, ABSENT_RESULT, NOT_CLOSED = "PRIVATE_TO_CARD", "ABSENT", "NOT_CLOSED"
ROOT_HELPER_NOT_IMPLEMENTED = "ROOT_HELPER_NOT_IMPLEMENTED"
ROOT_HELPER_FAILED = "ROOT_HELPER_FAILED"
CONFIG_UNPINNED, CONFIG_INVALID = "CONFIG_UNPINNED", "CONFIG_INVALID"
SPEC_INVALID = "SPEC_INVALID"
HELPER_REQUEST_INVALID, HELPER_RESULT_INVALID = "HELPER_REQUEST_INVALID", "HELPER_RESULT_INVALID"
HELPER_IDENTITY_MISMATCH, EVIDENCE_IDENTITY_MISMATCH = "HELPER_IDENTITY_MISMATCH", "EVIDENCE_IDENTITY_MISMATCH"
EVIDENCE_SCHEMA_STALE, EVIDENCE_MALFORMED = "EVIDENCE_SCHEMA_STALE", "EVIDENCE_MALFORMED"
EVIDENCE_COLLECTION_FAILED = "EVIDENCE_COLLECTION_FAILED"
STORED_VERDICT_NOT_EVIDENCE = "STORED_VERDICT_NOT_EVIDENCE"
CLEANUP_EVIDENCE_MISSING, CLEANUP_RESIDUE = "CLEANUP_EVIDENCE_MISSING", "CLEANUP_RESIDUE"
POSITIVE_CONTROL_MISSING, POSITIVE_CONTROL_NO_POWER = "POSITIVE_CONTROL_MISSING", "POSITIVE_CONTROL_NO_POWER"
DEVICE_NOT_CARD_PRIVATE, DEVICE_PRESENT_NOT_ABSENT = "DEVICE_NOT_CARD_PRIVATE", "DEVICE_PRESENT_NOT_ABSENT"
HOST_DEVICE_REACHABLE, MOUNT_PROPAGATION_SHARED = "HOST_DEVICE_REACHABLE", "MOUNT_PROPAGATION_SHARED"
UNDECLARED_DEVICE_ENTRY, DEVICE_EVIDENCE_INCOMPLETE = "UNDECLARED_DEVICE_ENTRY", "DEVICE_EVIDENCE_INCOMPLETE"
CHANNEL_RECOVERED = "CHANNEL_RECOVERED"

# ---- the policy (spike section 6.1), from the device contract's one authority ----------------------------------------
ADMITTED = tuple(p for p, (_rdev, _gid, kind) in device_contract.DEVICES.items() if kind in ("null", "zero", "full"))
ABSENT = tuple(p for p in device_contract.DEVICES if p not in ADMITTED)
CGROUP_ALLOW = tuple(device_contract.DEVICES[p][0] for p in ADMITTED)
DEV_OPTIONS = ("ro", "nosuid", "noexec")
ROOTFS_PROPAGATION = "rprivate"
PERM = 0o666
#: tmpfs's coarse clock put node stamps up to ~5 ms before the launch (spike section 2): the lower slack of a node's
#: ctime, and the least gap between consecutive cards, so a node left by an earlier card can never pass
COARSE_CLOCK_NS = 10_000_000
#: the decoder's guard band before the encoder's end (spike section 2)
GUARD_NS = 10_000_000
MIN_TRIALS_PER_BIT = 12
MIN_CONTROL_TRIALS_PER_BIT = 4
POWER_CONTROL = "power_control_shared_device_tmpfs"
CARD = "card"
MODES = (CARD, POWER_CONTROL)
#: the only programs a card may run, by name; the helper maps a name to the file in the kept tree
ENTRYPOINTS = {"proposer_host": "benchmarks/genesis_lite/proposer_host.py",
               "container_probe": "benchmarks/genesis_lite/v0_3/container_probe.py"}
CARD_ENV = {"PYTHONDONTWRITEBYTECODE": "1"}
#: where the helper binds the kept FORGE tree and venv in every card; a card argument must lie under one of them
KEPT_ROOTS = ("/forge/tree", "/forge/venv")
MAX_ARGS, MAX_TIMEOUT_S = 16, 3600.0
CLEAN = {"mounts": 0, "card_dirs": 0, "containers": 0, "cgroups": 0, "processes": 0}
STAGES = ("config", "helper", "identity", "evidence", "validation")
IDENTITY_KEYS = ("runtime_name", "runtime_version", "runtime_sha256", "kernel_release", "image_digest",
                 "rootfs_tree_sha256", "seccomp_sha256", "helper_sha256", "root_launch")
SHA_KEYS = ("runtime_sha256", "rootfs_tree_sha256", "seccomp_sha256", "helper_sha256")
CARD_ID = re.compile(r"gl3a-[0-9a-f]{8,32}")
ABS_ARG = re.compile(r"/[A-Za-z0-9._/-]*")
HEX64 = re.compile(r"[0-9a-f]{64}")
DEVICE_ID = re.compile(r"[0-9]+:[0-9]+")
DOC_KEYS = ("schema", "deployment", "device_contract", "detector", "config_sha256", "identity", "cards", "trials",
            "controls", "residue")
#: fields that would carry a verdict: a verdict is re-derived, never read
VERDICT_KEYS = ("verified", "status", "verdict", "boundary_findings", "validation", "result")
Problem = tuple[str, str]


def name_of(path: str) -> str:
    return path.rsplit("/", 1)[1]


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---- the typed runtime configuration --------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class RuntimeConfig:
    """One family-3a runtime: its identity pins and its fixed policy. No field has a default."""

    runtime_name: str
    runtime_version: str
    runtime_sha256: str
    kernel_release: str
    image_digest: str
    rootfs_tree_sha256: str
    seccomp_sha256: str
    helper_sha256: str
    root_launch: str
    admitted: tuple[str, ...]
    absent: tuple[str, ...]
    cgroup_allow: tuple[str, ...]
    dev_options: tuple[str, ...]
    rootfs_propagation: str
    capabilities: tuple[str, ...]
    read_only_rootfs: bool
    no_new_privileges: bool
    user_namespace: bool
    masks_from_card_tmpfs: bool

    def to_dict(self) -> dict[str, Any]:
        values = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        return {"schema": CONFIG_SCHEMA, **{k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}}

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_mapping(cls, doc: Any) -> RuntimeConfig:
        """Strict: exactly the schema and every field, nothing else (ValueError otherwise)."""
        names = [f.name for f in dataclasses.fields(cls)]
        if not isinstance(doc, Mapping) or set(doc) != {"schema", *names} or doc["schema"] != CONFIG_SCHEMA:
            raise ValueError("a family-3a runtime config needs exactly its schema and every field")
        return cls(**{n: tuple(doc[n]) if isinstance(doc[n], list) else doc[n] for n in names})


#: the four digests, MEASURED on the formal machine on 2026-10-21 by the installed helper's ``identity`` through the
#: declared root launch (twice, and again after a fresh re-extraction of the rootfs; crun also by ``sha256sum``):
#: ``/usr/bin/crun`` 1.14.1; the rootfs tree (family3a_helper.tree_digest) extracted from ``podman export`` of the
#: pinned image (export tar sha256 7d1ab3c8..., the spike's instance again) plus the two kept mount points; Podman's
#: /usr/share/containers/seccomp.json reduced to OCI form for this kernel; family3a_helper.py itself. A change to any
#: of them, the helper file included, needs a new measurement and a new pin
RUNTIME_SHA256 = "bd8ad7e7798edd5a857476c33bbef463b8b60ca2db43d7feb77698a703060c84"
ROOTFS_TREE_SHA256 = "d1b07cbc8c0456c634b09cc254a570437c9eb76b543503ecf9056c8f37a7d900"
SECCOMP_SHA256 = "0c424aa4fafb3002b7b3f3c8075e943aea48c81864ca60bfa267aab6164d8df0"
HELPER_SHA256 = "661d765c0b2c787df84db69118b99bf397a34825a927dd5b70e26439f62a89b4"
PINNED_CONFIG = RuntimeConfig(
    runtime_name=RUNTIME_NAME, runtime_version=RUNTIME_VERSION, runtime_sha256=RUNTIME_SHA256,
    kernel_release=isolation.KERNEL_RELEASE, image_digest=isolation.IMAGE_DIGEST, rootfs_tree_sha256=ROOTFS_TREE_SHA256,
    seccomp_sha256=SECCOMP_SHA256, helper_sha256=HELPER_SHA256, root_launch=ROOT_LAUNCH, admitted=ADMITTED,
    absent=ABSENT,
    cgroup_allow=CGROUP_ALLOW, dev_options=DEV_OPTIONS, rootfs_propagation=ROOTFS_PROPAGATION, capabilities=(),
    read_only_rootfs=True, no_new_privileges=True, user_namespace=True, masks_from_card_tmpfs=True)
_POLICY = {"runtime_name": RUNTIME_NAME, "runtime_version": RUNTIME_VERSION, "kernel_release": isolation.KERNEL_RELEASE,
           "image_digest": isolation.IMAGE_DIGEST, "root_launch": ROOT_LAUNCH, "admitted": ADMITTED, "absent": ABSENT,
           "cgroup_allow": CGROUP_ALLOW, "dev_options": DEV_OPTIONS, "rootfs_propagation": ROOTFS_PROPAGATION,
           "capabilities": (), "read_only_rootfs": True, "no_new_privileges": True, "user_namespace": True,
           "masks_from_card_tmpfs": True}


def config_problems(config: Any) -> list[Problem]:
    """Why ``config`` cannot drive a family-3a card: an unpinned identity, or any field off the declared policy."""
    if not isinstance(config, RuntimeConfig):
        return [(CONFIG_INVALID, f"not a RuntimeConfig: {type(config).__name__}")]
    problems = []
    for key in SHA_KEYS:
        value = getattr(config, key)
        if value == UNPINNED:
            problems.append((CONFIG_UNPINNED, f"{key} is not measured on the formal machine yet"))
        elif not isinstance(value, str) or not HEX64.fullmatch(value):
            problems.append((CONFIG_INVALID, f"{key} {value!r} is not a sha256"))
    for key, want in _POLICY.items():
        value = getattr(config, key)
        if value != want or type(value) is not type(want):
            problems.append((CONFIG_INVALID, f"{key} is {value!r}, not the declared {want!r}"))
    return problems


def identity_problems(config: RuntimeConfig, ident: Any) -> list[Problem]:
    """The helper's measured identity against the pins: every key, exactly; UNPINNED never matches."""
    if not isinstance(ident, Mapping) or set(ident) != set(IDENTITY_KEYS):
        got = sorted(ident) if isinstance(ident, Mapping) else ident
        return [(HELPER_IDENTITY_MISMATCH, f"the helper reported {got!r}, not exactly {list(IDENTITY_KEYS)}")]
    return [(HELPER_IDENTITY_MISMATCH, f"{k}: the helper measured {ident[k]!r}, pinned {getattr(config, k)!r}")
            for k in IDENTITY_KEYS if getattr(config, k) == UNPINNED or ident[k] != getattr(config, k)]


# ---- the card spec and the helper request ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class CardSpec:
    """ONE card: a fresh id, a named entrypoint, its arguments (absolute kept-tree paths only), its environment."""

    card_id: str
    entrypoint: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_s: float


def spec_problems(spec: Any) -> list[Problem]:
    if not isinstance(spec, CardSpec):
        return [(SPEC_INVALID, f"not a CardSpec: {type(spec).__name__}")]
    problems = []
    if not isinstance(spec.card_id, str) or not CARD_ID.fullmatch(spec.card_id):
        problems.append((SPEC_INVALID, f"card id {spec.card_id!r}"))
    if spec.entrypoint not in ENTRYPOINTS:
        problems.append((SPEC_INVALID, f"entrypoint {spec.entrypoint!r} is not one of {sorted(ENTRYPOINTS)}"))
    args = spec.args if isinstance(spec.args, tuple) else None
    if args is None or len(args) > MAX_ARGS or (spec.entrypoint == "container_probe" and args):
        problems.append((SPEC_INVALID, f"arguments {spec.args!r}"))
    for arg in args or ():
        if (not isinstance(arg, str) or not ABS_ARG.fullmatch(arg) or ".." in arg.split("/")
                or not any(arg == root or arg.startswith(root + "/") for root in KEPT_ROOTS)):
            problems.append((SPEC_INVALID, f"argument {arg!r} is not an absolute path under {KEPT_ROOTS}"))
    env = spec.env if isinstance(spec.env, tuple) else None
    if env is None or any(not isinstance(p, tuple) or len(p) != 2 or CARD_ENV.get(p[0]) != p[1] for p in env):
        problems.append((SPEC_INVALID, f"environment {spec.env!r} (only {CARD_ENV})"))
    t = spec.timeout_s
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 < t <= MAX_TIMEOUT_S:
        problems.append((SPEC_INVALID, f"timeout {t!r}"))
    return problems


def helper_request(config: RuntimeConfig, spec: CardSpec, *, mode: str = CARD) -> dict[str, Any]:
    """The helper's whole input for one card. It holds no command: the helper builds the OCI spec itself."""
    return {"schema": HELPER_REQUEST_SCHEMA, "mode": mode, "config_sha256": config.digest(),
            "card": {"card_id": spec.card_id, "entrypoint": spec.entrypoint, "args": list(spec.args),
                     "env": dict(spec.env), "timeout_s": spec.timeout_s}}


def helper_request_problems(request: Any, config: RuntimeConfig) -> list[Problem]:
    """What the helper must refuse: anything but exactly a request of :func:`helper_request` for ``config``."""
    if not isinstance(request, Mapping) or set(request) != {"schema", "mode", "config_sha256", "card"}:
        return [(HELPER_REQUEST_INVALID, "not exactly schema, mode, config_sha256 and card")]
    problems = []
    if request["schema"] != HELPER_REQUEST_SCHEMA or request["mode"] not in MODES:
        problems.append((HELPER_REQUEST_INVALID, f"schema {request['schema']!r} or mode {request['mode']!r}"))
    if request["config_sha256"] != config.digest():
        problems.append((HELPER_REQUEST_INVALID, "made for another runtime config"))
    card = request["card"]
    if not isinstance(card, Mapping) or set(card) != {"card_id", "entrypoint", "args", "env", "timeout_s"}:
        return [*problems, (HELPER_REQUEST_INVALID, "the card is not exactly id, entrypoint, args, env and timeout")]
    if not isinstance(card["args"], list) or not isinstance(card["env"], Mapping):
        return [*problems, (HELPER_REQUEST_INVALID, "malformed arguments or environment")]
    spec = CardSpec(card["card_id"], card["entrypoint"], tuple(card["args"]), tuple(card["env"].items()),
                    card["timeout_s"])
    problems += [(HELPER_REQUEST_INVALID, detail) for _reason, detail in spec_problems(spec)]
    if request["mode"] == POWER_CONTROL and spec.entrypoint != "container_probe":
        problems.append((HELPER_REQUEST_INVALID, "the power control runs the container probe only"))
    return problems


def _cleanup_problems(value: Any, where: str) -> list[Problem]:
    if not isinstance(value, Mapping) or set(value) != set(CLEAN) or not all(_int(v) and v >= 0
                                                                             for v in value.values()):
        return [(CLEANUP_EVIDENCE_MISSING, f"{where}: no complete cleanup record")]
    left = {k: v for k, v in value.items() if v}
    return [(CLEANUP_RESIDUE, f"{where}: residue {left}")] if left else []


def _window(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, Mapping) or not _int(value.get("start_ns")) or not _int(value.get("end_ns")):
        return None
    return (value["start_ns"], value["end_ns"]) if value["start_ns"] < value["end_ns"] else None


def helper_result_problems(result: Any, request: Mapping[str, Any]) -> list[Problem]:
    keys = {"schema", "card_id", "mode", "exit_code", "window", "cleanup"}
    if not isinstance(result, Mapping):
        return [(HELPER_RESULT_INVALID, "no result"), (CLEANUP_EVIDENCE_MISSING, "no cleanup record")]
    problems = [] if "cleanup" in result else [(CLEANUP_EVIDENCE_MISSING, "the helper reported no cleanup")]
    if set(result) - keys or not {"schema", "card_id", "mode", "exit_code", "window"} <= set(result):
        return [*problems, (HELPER_RESULT_INVALID, f"fields {sorted(result)}")]
    if (result["schema"] != HELPER_RESULT_SCHEMA or result["card_id"] != request["card"]["card_id"]
            or result["mode"] != request["mode"] or not _int(result["exit_code"]) or _window(result["window"]) is None):
        problems.append((HELPER_RESULT_INVALID, "schema, card, mode, exit code or window"))
    if "cleanup" in result:
        problems += _cleanup_problems(result["cleanup"], request["card"]["card_id"])
    return problems


# ---- the strict root-helper contract and the launcher interface ------------------------------------------------------
class RootHelperUnavailable(RuntimeError):
    """The root helper cannot serve this call; ``reason`` says why."""

    def __init__(self, reason: str, detail: str) -> None:  # noqa: D107
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


class Family3aRefused(RuntimeError):
    """A family-3a card may not start, or its result is not evidence. ``problems``: (reason, detail) pairs."""

    def __init__(self, problems: Iterable[Problem]) -> None:  # noqa: D107
        self.problems = list(problems)
        self.reasons = {r for r, _ in self.problems}
        super().__init__("; ".join(f"{r}: {d}" for r, d in self.problems))


class CardHandle(Protocol):
    """One running card: its pipes, and the helper's final record (window and cleanup) once the card exits."""

    stdin: Any
    stdout: Any

    def wait(self, timeout: float) -> Mapping[str, Any]: ...


class RootHelper(Protocol):
    """The root helper contract. A conforming helper is a separately reviewed program, pinned by
    :attr:`RuntimeConfig.helper_sha256`, launched by the declared operator action (:data:`ROOT_LAUNCH`). It
    MUST:

    * report its measured identity as exactly :data:`IDENTITY_KEYS`: crun version and binary digest, kernel release,
      image digest, exported rootfs tree digest, seccomp profile digest, its own digest and the root launch;
    * take nothing but a request that :func:`helper_request_problems` accepts, and refuse anything else;
    * perform only the fixed per-card steps of spike section 6.1, never a caller's command: one private tmpfs per
      card holding mknod'd null, zero and full and an empty mask file; ``/dev`` bound ro, nosuid, noexec; no crun
      ``maskedPaths`` for files; ``rootfsPropagation: rprivate``; a user-namespace mapping, empty capability sets and
      no_new_privs; the pinned seccomp profile; a device cgroup allowing only :data:`CGROUP_ALLOW`; a read-only
      rootfs; then the request's entrypoint from the kept tree. In :data:`POWER_CONTROL` mode, and only there, one
      device tmpfs is shared by the control's cards;
    * clean up after every card and report the window and the residue counts of :data:`CLEAN` (all zero, or it is
      not a clean card)."""

    def identity(self) -> Mapping[str, Any]: ...

    def start(self, request: Mapping[str, Any]) -> CardHandle: ...


class UnimplementedRootHelper:
    """The helper wherever the declared root launch does not exist: every call fails closed as
    :data:`ROOT_HELPER_NOT_IMPLEMENTED`."""

    _why = ("the declared root launch (wsl.exe -u root) is not available in this process; a card never falls back "
            "to another runtime")

    def identity(self) -> Mapping[str, Any]:
        raise RootHelperUnavailable(ROOT_HELPER_NOT_IMPLEMENTED, self._why)

    def start(self, request: Mapping[str, Any]) -> CardHandle:
        raise RootHelperUnavailable(ROOT_HELPER_NOT_IMPLEMENTED, self._why)


#: the formal WSL2 VM and the helper's installed copy (installed by the operator; see family3a_helper.py)
WSL_DISTRO = "Ubuntu-24.04"
HELPER_FILE = pathlib.Path(__file__).with_name("family3a_helper.py")
HELPER_INSTALLED = "/var/lib/forge-f3a/helper.py"
RESULT_PREFIX = "F3A-RESULT "
IDENTITY_TIMEOUT_S = 900.0


def wsl_argv(*operation: str) -> list[str]:
    """The declared root launch (:data:`ROOT_LAUNCH`) of one fixed helper operation. ``--exec`` runs the helper
    without the login shell, so nothing in the arguments is re-parsed."""
    return ["wsl.exe", "-d", WSL_DISTRO, "-u", "root", "--exec", "/usr/bin/python3", "-I", HELPER_INSTALLED,
            *operation]


def parse_result(stderr: str) -> Mapping[str, Any] | None:
    """The helper's result record: its last stderr line with :data:`RESULT_PREFIX` (None when there is none)."""
    lines = [ln[len(RESULT_PREFIX):] for ln in stderr.splitlines() if ln.startswith(RESULT_PREFIX)]
    try:
        doc = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    return doc if isinstance(doc, Mapping) else None


class WslCardHandle:
    """One card running under the WSL root helper."""

    def __init__(self, proc: subprocess.Popen) -> None:  # noqa: D107
        self._proc = proc
        self.stdin, self.stdout = proc.stdin, proc.stdout

    def wait(self, timeout: float) -> Mapping[str, Any]:
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        stderr = self._proc.stderr.read().decode("utf-8", "replace") if self._proc.stderr else ""
        return parse_result(stderr) or {}


class WslRootHelper:
    """The family-3a root helper reached by the declared root launch. Its identity is MEASURED by the installed
    helper on every call; this class trusts nothing it is told, :func:`identity_problems` compares it to the pins."""

    def identity(self) -> Mapping[str, Any]:
        try:
            done = subprocess.run(wsl_argv("identity"), capture_output=True, timeout=IDENTITY_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RootHelperUnavailable(ROOT_HELPER_FAILED, f"{type(exc).__name__}: {exc}") from exc
        out, err = done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")
        if done.returncode != 0:
            raise RootHelperUnavailable(ROOT_HELPER_FAILED, f"exit {done.returncode}: {err.strip()[-300:]}")
        try:
            doc = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RootHelperUnavailable(ROOT_HELPER_FAILED, f"no identity record: {out[-300:]!r}") from exc
        return doc

    def start(self, request: Mapping[str, Any]) -> CardHandle:
        hexed = json.dumps(request, sort_keys=True, separators=(",", ":")).encode().hex()
        try:
            proc = subprocess.Popen(wsl_argv("run", hexed), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, bufsize=0)
        except OSError as exc:
            raise RootHelperUnavailable(ROOT_HELPER_FAILED, f"{type(exc).__name__}: {exc}") from exc
        return WslCardHandle(proc)


def default_root_helper() -> RootHelper:
    """The WSL root helper where the declared root launch exists (Windows with ``wsl.exe``); otherwise the helper that
    fails closed as :data:`ROOT_HELPER_NOT_IMPLEMENTED`."""
    if sys.platform == "win32" and shutil.which("wsl.exe"):
        return WslRootHelper()
    return UnimplementedRootHelper()


def _helper_identity(helper: Any) -> tuple[Mapping[str, Any] | None, list[Problem]]:
    try:
        return helper.identity(), []
    except RootHelperUnavailable as exc:
        return None, [(exc.reason, str(exc))]
    except Exception as exc:  # noqa: BLE001 - any helper failure refuses
        return None, [(ROOT_HELPER_FAILED, f"{type(exc).__name__}: {str(exc)[:200]}")]


class CardSession:
    """A started card. :meth:`close` returns the helper's record only if it is complete and clean."""

    def __init__(self, request: Mapping[str, Any], handle: CardHandle) -> None:  # noqa: D107
        self.request, self._handle = request, handle
        self.stdin, self.stdout = handle.stdin, handle.stdout

    def close(self, timeout: float) -> dict[str, Any]:
        result = self._handle.wait(timeout)
        problems = helper_result_problems(result, self.request)
        if problems:
            raise Family3aRefused(problems)
        return dict(result)


class Family3aLauncher:
    """Starts ONE card through the root helper, after the config, the spec and the helper's identity are checked."""

    def __init__(self, config: RuntimeConfig, helper: RootHelper) -> None:  # noqa: D107
        self.config, self.helper = config, helper

    def start(self, spec: CardSpec, *, mode: str = CARD) -> CardSession:
        problems = spec_problems(spec) + config_problems(self.config)
        if mode not in MODES:
            problems.append((HELPER_REQUEST_INVALID, f"mode {mode!r}"))
        if problems:
            raise Family3aRefused(problems)
        ident, problems = _helper_identity(self.helper)
        problems = problems or identity_problems(self.config, ident)
        request = helper_request(self.config, spec, mode=mode)
        problems = problems or helper_request_problems(request, self.config)
        if problems:
            raise Family3aRefused(problems)
        try:
            handle = self.helper.start(request)
        except RootHelperUnavailable as exc:
            raise Family3aRefused([(exc.reason, str(exc))]) from exc
        return CardSession(request, handle)


# ---- Device Contract v2 and the evidence validator -------------------------------------------------------------------
class _Found:
    def __init__(self) -> None:
        self.everywhere: set[str] = set()
        self.nodes: dict[str, set[str]] = {p: set() for p in device_contract.DEVICES}
        self.details: list[str] = []

    def all(self, reason: str, detail: str) -> None:
        self.everywhere.add(reason)
        self.details.append(f"{reason}: {detail}")

    def at(self, paths: Iterable[str], reason: str, detail: str) -> None:
        for path in paths:
            self.nodes[path].add(reason)
        self.details.append(f"{reason}: {detail}")


def _guess(node: Any, window: tuple[int, int]) -> int | None:
    """The detector's guess: 1 when the node's latest stamp lies in the encoder's window before its guard band."""
    if not isinstance(node, Mapping) or not _int(node.get("mtime_ns")) or not _int(node.get("ctime_ns")):
        return None
    return int(window[0] <= max(node["mtime_ns"], node["ctime_ns"]) < window[1] - GUARD_NS)


def _touch_problem(card: Mapping[str, Any], bit: int) -> str | None:
    """An encoder must have tried every node on bit 1, and done nothing on bit 0."""
    done = card.get("utimensat")
    if bit == 0:
        return None if done == {} else f"touched nodes on bit 0: {done!r}"
    want = {**{p: ("OK", "EROFS") for p in ADMITTED}, **{p: ("ENOENT",) for p in ABSENT}}
    if not isinstance(done, Mapping) or set(done) != set(want) or any(done[p] not in want[p] for p in want):
        return f"did not try every node on bit 1: {done!r}"
    return None


def _card(label: str, card: Any, found: _Found) -> tuple[int, int] | None:
    """Device Contract v2 on one formal card; returns its window."""
    if not isinstance(card, Mapping):
        found.all(DEVICE_EVIDENCE_INCOMPLETE, f"{label}: not a card record")
        return None
    window = _window(card.get("window"))
    for reason, detail in _cleanup_problems(card.get("cleanup"), label):
        found.all(reason, detail)
    host = card.get("host_devtmpfs")
    mounts = card.get("mounts")
    rows_ok = isinstance(mounts, list) and mounts and all(
        isinstance(r, Mapping) and isinstance(r.get("target"), str) and isinstance(r.get("fstype"), str)
        and isinstance(r.get("device"), str) and DEVICE_ID.fullmatch(r["device"]) and isinstance(r.get("options"), list)
        and isinstance(r.get("optional"), list) for r in mounts)
    if window is None or not isinstance(host, str) or not DEVICE_ID.fullmatch(host) or not rows_ok:
        found.all(DEVICE_EVIDENCE_INCOMPLETE, f"{label}: window, host devtmpfs or mount table malformed")
        return None
    for row in mounts:
        if row["fstype"] == "devtmpfs" or row["device"] == host:
            found.all(HOST_DEVICE_REACHABLE, f"{label}: {row['target']} is on the host devtmpfs")
        if row["optional"]:
            found.all(MOUNT_PROPAGATION_SHARED, f"{label}: {row['target']} propagates {row['optional']}")
    devs = [r for r in mounts if r["target"] == "/dev"]
    dev_device = None
    if len(devs) != 1 or devs[0]["fstype"] != "tmpfs" or not set(DEV_OPTIONS) <= set(devs[0]["options"]):
        found.at(ADMITTED, DEVICE_NOT_CARD_PRIVATE, f"{label}: /dev is not one ro, nosuid, noexec tmpfs")
    else:
        dev_device = devs[0]["device"]
    walk = card.get("walk")
    if not isinstance(walk, Mapping) or not _int(walk.get("entries")) or walk["entries"] < 1 or not isinstance(
            walk.get("devices"), list):
        found.all(DEVICE_EVIDENCE_INCOMPLETE, f"{label}: no reachable-device walk")
    elif walk["devices"]:
        found.all(HOST_DEVICE_REACHABLE, f"{label}: device nodes outside /dev {walk['devices']}")
    listing = card.get("dev")
    if not isinstance(listing, Mapping):
        found.all(DEVICE_EVIDENCE_INCOMPLETE, f"{label}: no /dev listing")
        return window
    absent_names = {name_of(p): p for p in ABSENT}
    for name, entry in listing.items():
        if name in absent_names:
            found.at([absent_names[name]], DEVICE_PRESENT_NOT_ABSENT, f"{label}: /dev/{name} exists")
        elif name == "shm" and isinstance(entry, Mapping) and entry.get("type") == "dir":
            continue
        elif "/dev/" + str(name) not in ADMITTED:
            found.all(UNDECLARED_DEVICE_ENTRY, f"{label}: /dev/{name} is not declared")
    for path in ADMITTED:
        node, rdev = listing.get(name_of(path)), device_contract.DEVICES[path][0]
        ok = (isinstance(node, Mapping) and node.get("type") == "chr" and node.get("rdev") == rdev
              and node.get("perm") == PERM and dev_device is not None and node.get("dev") == dev_device != host
              and _int(node.get("ctime_ns")) and _int(node.get("mtime_ns"))
              and all(window[0] - COARSE_CLOCK_NS < node[k] <= window[1] for k in ("ctime_ns", "mtime_ns")))
        # never by st_dev/st_ino equality with another card. Any metadata change to a node shared with an earlier card
        # moves its ctime to that card's time, before this window, so the window rule also covers explicit-time writes
        if not ok:
            found.at([path], DEVICE_NOT_CARD_PRIVATE, f"{label}: {path} is not a node made for this card")
    absent = card.get("absent")
    for path in ABSENT:
        seen = absent.get(path) if isinstance(absent, Mapping) else None
        if seen != {"open": "ENOENT", "stat": "ENOENT"}:
            found.at([path], DEVICE_PRESENT_NOT_ABSENT, f"{label}: {path} gave {seen!r}, not ENOENT")
    return window


def _trials(doc: Mapping[str, Any], windows: Mapping[str, tuple[int, int] | None], found: _Found) -> None:
    cards, trials = doc["cards"], doc["trials"]
    if not isinstance(trials, list):
        found.all(DEVICE_EVIDENCE_INCOMPLETE, "no trial list")
        return
    used: set[str] = set()
    count = {0: 0, 1: 0}
    for n, trial in enumerate(trials):
        enc = trial.get("encoder") if isinstance(trial, Mapping) else None
        dec = trial.get("decoder") if isinstance(trial, Mapping) else None
        bit = trial.get("bit") if isinstance(trial, Mapping) else None
        if (bit not in (0, 1) or isinstance(bit, bool) or not isinstance(enc, str) or not isinstance(dec, str)
                or enc == dec or {enc, dec} & used or windows.get(enc) is None or windows.get(dec) is None):
            found.all(DEVICE_EVIDENCE_INCOMPLETE, f"trial {n}: malformed, reused or unknown cards")
            continue
        used |= {enc, dec}
        if windows[dec][0] < windows[enc][1]:
            found.all(DEVICE_EVIDENCE_INCOMPLETE, f"trial {n}: the decoder started before the encoder ended")
            continue
        problem = _touch_problem(cards[enc], bit)
        if problem:
            found.all(DEVICE_EVIDENCE_INCOMPLETE, f"trial {n} encoder {enc}: {problem}")
            continue
        count[bit] += 1
        for path in ADMITTED:
            if _guess(cards[dec]["dev"].get(name_of(path)), windows[enc]) != 0:
                found.at([path], CHANNEL_RECOVERED, f"trial {n} (bit {bit}): decoder {dec} saw encoder {enc} on {path}")
    if min(count.values()) < MIN_TRIALS_PER_BIT:
        found.all(DEVICE_EVIDENCE_INCOMPLETE, f"valid trials per bit {count}, fewer than {MIN_TRIALS_PER_BIT}")


def _controls(doc: Mapping[str, Any], found: _Found) -> None:
    section = doc["controls"].get(POWER_CONTROL) if isinstance(doc["controls"], Mapping) else None
    if not isinstance(section, list):
        found.all(POSITIVE_CONTROL_MISSING, "no shared-device-tmpfs power control")
        return
    count = {0: 0, 1: 0}
    for n, c in enumerate(section):
        enc = c.get("encoder") if isinstance(c, Mapping) else None
        dec = c.get("decoder") if isinstance(c, Mapping) else None
        bit = c.get("bit") if isinstance(c, Mapping) else None
        if bit not in (0, 1) or isinstance(bit, bool) or not isinstance(enc, Mapping) or not isinstance(dec, Mapping):
            found.all(POSITIVE_CONTROL_MISSING, f"control {n}: malformed")
            continue
        for role, rec in (("encoder", enc), ("decoder", dec)):
            for reason, detail in _cleanup_problems(rec.get("cleanup"), f"control {n} {role}"):
                found.all(reason, detail)
        we, wd = _window(enc.get("window")), _window(dec.get("window"))
        listing = dec.get("dev")
        if we is None or wd is None or wd[0] < we[1] or not isinstance(listing, Mapping):
            found.all(POSITIVE_CONTROL_MISSING, f"control {n}: windows or decoder listing malformed")
            continue
        count[bit] += 1
        problem = _touch_problem(enc, bit)
        if problem:
            found.all(POSITIVE_CONTROL_NO_POWER, f"control {n} encoder: {problem}")
            continue
        for path in ADMITTED:
            if _guess(listing.get(name_of(path)), we) != bit:
                found.all(POSITIVE_CONTROL_NO_POWER, f"control {n} (bit {bit}): {path} did not carry the bit")
    if min(count.values()) < MIN_CONTROL_TRIALS_PER_BIT:
        found.all(POSITIVE_CONTROL_MISSING, f"control trials per bit {count}, fewer than {MIN_CONTROL_TRIALS_PER_BIT}")


def _derive(doc: Any, config: RuntimeConfig, found: _Found) -> None:
    if not isinstance(doc, Mapping):
        found.all(EVIDENCE_MALFORMED, f"not an evidence document: {type(doc).__name__}")
        return
    stored = sorted(k for k in VERDICT_KEYS if k in doc)
    if stored:
        found.all(STORED_VERDICT_NOT_EVIDENCE, f"stored verdict fields {stored} are never read")
    unknown = sorted(str(k) for k in doc if k not in DOC_KEYS and k not in VERDICT_KEYS)
    if unknown:
        found.all(EVIDENCE_MALFORMED, f"unknown fields {unknown}")
    current = {"schema": EVIDENCE_SCHEMA, "deployment": DEPLOYMENT, "device_contract": DEVICE_CONTRACT,
               "detector": DETECTOR}
    stale = {k: doc.get(k) for k, v in current.items() if doc.get(k) != v}
    if stale:
        found.all(EVIDENCE_SCHEMA_STALE, f"{stale} is not {current}: nothing is derived")
        return
    if "residue" not in doc:
        found.all(CLEANUP_EVIDENCE_MISSING, "no final residue check")
    missing = sorted(k for k in DOC_KEYS if k not in doc and k != "residue")
    if missing:
        found.all(EVIDENCE_MALFORMED, f"missing fields {missing}")
        return
    for reason, detail in config_problems(config):
        found.all(reason, detail)
    ident = doc["identity"]
    if not isinstance(ident, Mapping) or set(ident) != set(IDENTITY_KEYS) or doc["config_sha256"] != config.digest():
        found.all(EVIDENCE_IDENTITY_MISMATCH, "the evidence's identity or config digest is not this config's")
    else:
        for key in IDENTITY_KEYS:
            if getattr(config, key) == UNPINNED or ident[key] != getattr(config, key):
                found.all(EVIDENCE_IDENTITY_MISMATCH,
                          f"{key}: measured {ident[key]!r}, pinned {getattr(config, key)!r}")
    for reason, detail in _cleanup_problems(doc.get("residue"), "final residue"):
        found.all(reason, detail)
    cards = doc["cards"]
    if not isinstance(cards, Mapping) or not cards:
        found.all(EVIDENCE_MALFORMED, "no card records")
        return
    windows = {str(label): _card(str(label), card, found) for label, card in cards.items()}
    ordered = sorted(w for w in windows.values() if w is not None)
    for (_s0, e0), (s1, _e1) in zip(ordered, ordered[1:]):
        if s1 - e0 < COARSE_CLOCK_NS:
            found.all(DEVICE_EVIDENCE_INCOMPLETE, "card windows overlap or are closer than the coarse clock")
            break
    _trials(doc, windows, found)
    _controls(doc, found)


def validate_evidence(doc: Any, config: RuntimeConfig) -> dict[str, Any]:
    """Device Contract v2 on family-3a evidence, re-derived from the raw records; never raises. PASS only when every
    rule holds. ``boundary_findings`` is BLOCKER 1's closure in :mod:`.readiness` terms: MEASURED only when the
    document, identity, cleanup and power control hold; each node closes only on its own clean record."""
    found = _Found()
    try:
        _derive(doc, config, found)
    except (TypeError, KeyError, ValueError, AttributeError, IndexError) as exc:
        found.all(EVIDENCE_MALFORMED, f"{type(exc).__name__}: {str(exc)[:200]}")
    measured = not found.everywhere
    closes = {**{p: PRIVATE_TO_CARD for p in ADMITTED}, **{p: ABSENT_RESULT for p in ABSENT}}
    nodes = {p: closes[p] if measured and not found.nodes[p] else NOT_CLOSED for p in device_contract.DEVICES}
    reasons = sorted(found.everywhere | {r for rs in found.nodes.values() for r in rs})
    return {"contract": DEVICE_CONTRACT, "status": PASS if not reasons else CHECK_BLOCKED, "reasons": reasons,
            "findings": found.details,
            "per_node": {p: sorted(found.nodes[p] | found.everywhere) for p in device_contract.DEVICES},
            "boundary_findings": {"BLOCKER 1": {"evidence": MEASURED if measured else NOT_MEASURED,
                                                "detector": DETECTOR, "nodes": nodes}}}


# ---- pre-admission ordering and fail-closed readiness ----------------------------------------------------------------
def pre_admission(config: RuntimeConfig, helper: RootHelper,
                  collect: Callable[[Family3aLauncher], Mapping[str, Any]]) -> dict[str, Any]:
    """The family-3a deployment check before a formal admission, in the order of :data:`STAGES`: the config's pins and
    policy, the helper's presence, its identity, evidence collection through the launcher (``collect``), and the
    re-derived validation. The first stage that fails stops the rest (NOT_REACHED): no card starts before the config,
    the helper and its identity hold. It takes no root and no registry, so a refusal never consumes an attempt."""
    stages, problems, ident, doc, verdict = [], [], None, None, None
    for stage in STAGES:
        if problems:
            stages.append({"stage": stage, "status": NOT_REACHED, "problems": []})
            continue
        if stage == "config":
            problems = config_problems(config)
        elif stage == "helper":
            ident, problems = _helper_identity(helper)
        elif stage == "identity":
            problems = identity_problems(config, ident)
        elif stage == "evidence":
            try:
                doc = collect(Family3aLauncher(config, helper))
            except Exception as exc:  # noqa: BLE001 - any collection failure refuses
                problems = [(EVIDENCE_COLLECTION_FAILED, f"{type(exc).__name__}: {str(exc)[:200]}")]
        else:
            verdict = validate_evidence(doc, config)
            problems = [(r, "re-derived from the collected records") for r in verdict["reasons"]]
        stages.append({"stage": stage, "status": CHECK_BLOCKED if problems else PASS, "problems": problems})
    return {"status": REFUSED if problems else ADMISSIBLE, "stages": stages,
            "reasons": sorted({r for r, _ in problems}), "problems": problems, "validation": verdict}


def execution_readiness(config: RuntimeConfig | None = None, helper: RootHelper | None = None) -> dict[str, Any]:
    """Whether a family-3a D5 package could be executed now: READY only when the config is fully pinned and on policy,
    a helper answers, and its identity matches every pin. It inspects only; it never starts a card."""
    config = PINNED_CONFIG if config is None else config
    helper = default_root_helper() if helper is None else helper
    stages = []
    problems = config_problems(config)
    stages.append({"stage": "config", "status": CHECK_BLOCKED if problems else PASS, "problems": problems})
    ident, helper_problems = _helper_identity(helper)
    stages.append({"stage": "helper", "status": CHECK_BLOCKED if helper_problems else PASS,
                   "problems": helper_problems})
    problems = problems + helper_problems
    if ident is None:
        stages.append({"stage": "identity", "status": NOT_REACHED, "problems": []})
    else:
        id_problems = identity_problems(config, ident)
        stages.append({"stage": "identity", "status": CHECK_BLOCKED if id_problems else PASS, "problems": id_problems})
        problems += id_problems
    return {"status": BLOCKED if problems else READY, "deployment": DEPLOYMENT, "stages": stages,
            "reasons": sorted({r for r, _ in problems}), "problems": problems, "config_sha256": config.digest(),
            "d5": "NOT_PROVEN",
            "not_claimed": "readiness to execute is not D5 evidence: D5, N-1 and BLOCKER 1 stay open until pinned "
                           "MEASURED family-3a evidence and a declared detector close them in readiness.py"}


def main(argv: list[str] | None = None) -> int:
    del argv
    result = execution_readiness()
    sys.stdout.write(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return 0 if result["status"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
