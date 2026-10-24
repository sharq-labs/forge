"""Leakage scanner v1 for BR-BATT-REDISC-02 (evaluator side; the candidate never imports this module).

Two scanners, kept separate:

* NUMERIC (``numeric_findings``): the text is split into COMPLETE numeric tokens, which are then compared by value:
  - a token is an optionally signed decimal with an optional exponent, ``[+-]?(\\d+(\\.\\d*)?|\\.\\d+)([eE][+-]?\\d+)?``;
  - it may not be preceded by a letter, digit, ``_`` or ``.``, and it may not be followed by a letter or ``_`` unless
    that letter run is a declared unit (``UNITS``), so hex digests and identifiers are never read as numbers;
  - "760.006", "1760" and "76001" are each ONE token, so none of them is "760";
  - a token's value is an exact Decimal, with the sign ignored (a sign flip still leaks the magnitude), so "760",
    "760.0", "+760", "-760" and "7.60e2" are the same value;
  - a token with s significant digits (trailing zeros of an integer count) matches a protected value v if it equals
    v rounded to 3 or to 4 significant digits (the reported forms), or if s >= 5 and it equals v rounded to s digits
    (a longer transcription of the estimate);
  - a token followed by a unit with an SI prefix is also compared after scaling to the base unit (so "20.7 mOhm"
    is 0.0207 ohm), but only against protected values of that base unit;
  - every complete token is compared, however few digits it is written with: "8.4" equals the reported form 8.40.
    (Development: an earlier rule skipped tokens with fewer than 3 significant digits; the mutation suite showed it
    missed "8.4 mV" for a protected 8.40 mV, so it was removed before any candidate run.)
* MEASUREMENT ARRAYS of the pack (``MEASUREMENT_KEYS``) are not numerically scanned: a raw time, current, voltage or
  temperature can equal a short historical number by chance (a 12.5 s timestamp equals a 12.5 mV historical RMSE at 3
  digits).  They are protected by PROVENANCE instead (``provenance_findings``): the pack must rebuild byte-identically
  from the pinned split data files, so any planted or altered measurement value is a finding.  Every other pack field
  (strings, declared numbers, keys) is numerically and textually scanned.
* TEXT (``text_findings``): case-sensitive substrings for identity tokens (datasets, cells, files, digests, record and
  directory names) and historical verdict tokens.

Plus the pack-key whitelist and the runtime path/module audit of the sandboxed run.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable, Sequence

SCANNER_ID = "forge.battery_rediscovery.leakage_scanner"
SCANNER_VERSION = "1.0.0"

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = HERE / "candidate"
MIND_SRC = ROOT / "src" / "engcore" / "mind" / "minimal"

LONG_SIG = 5
PREFIX = {"": Decimal(1), "m": Decimal("1e-3"), "k": Decimal("1e3"), "u": Decimal("1e-6"), "µ": Decimal("1e-6"),
          "M": Decimal("1e6")}
BASE_UNITS = {"ohm": "ohm", "Ohm": "ohm", "Ω": "ohm", "F": "F", "s": "s", "V": "V", "A": "A", "Ah": "Ah"}
UNITS = {p + u: (PREFIX[p], b) for p in PREFIX for u, b in BASE_UNITS.items()}
UNITS.update({"degC": (Decimal(1), "degC"), "C": (Decimal(1), "degC")})

_NUM = re.compile(r"(?<![0-9A-Za-z_.])([+-]?)((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_UNIT_AFTER = re.compile(r"\s?([A-Za-zΩµ]+)")


@dataclass(frozen=True)
class Protected:
    """One protected historical value: its name, value (in ``unit``) and the base unit it is a quantity of."""

    name: str
    value: Decimal
    unit: str                  # the unit the value is stated in (e.g. "mV")
    base: str                  # the base unit (e.g. "V")
    scale_to_base: Decimal     # value * scale_to_base is the value in the base unit

    @property
    def base_value(self) -> Decimal:
        return self.value * self.scale_to_base


def protected(name: str, value: float | str, unit: str) -> Protected:
    scale, base = UNITS[unit] if unit in UNITS else (Decimal(1), unit)
    return Protected(name, Decimal(str(value)), unit, base, scale)


def sig_digits(mantissa: str) -> int:
    digits = mantissa.replace(".", "").lstrip("0")
    return len(digits) if digits else 1


def round_sig(v: Decimal, s: int) -> Decimal:
    if v == 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 60
        exp = v.adjusted() - s + 1
        return v.quantize(Decimal(f"1e{exp}"), rounding=ROUND_HALF_EVEN)


def _matches(x: Decimal, s: int, v: Decimal) -> bool:
    v = abs(v)
    if x == round_sig(v, 3) or x == round_sig(v, 4):
        return True
    return s >= LONG_SIG and x == round_sig(v, s)


@dataclass(frozen=True)
class Token:
    text: str
    value: Decimal
    sig: int
    unit: str | None
    start: int


def tokens(text: str) -> list[Token]:
    out = []
    for m in _NUM.finditer(text):
        end = m.end()
        unit = None
        nxt = text[end:end + 1]
        if nxt and (nxt.isalpha() or nxt == "_" or nxt in "Ωµ"):
            run = re.match(r"[A-Za-zΩµ_]+", text[end:]).group(0)
            if run not in UNITS:
                continue                                   # part of an identifier or a hex digest, not a number
            unit = run
        elif nxt == " ":
            u = _UNIT_AFTER.match(text, end)
            if u and u.group(1) in UNITS:
                after = text[u.end():u.end() + 1]
                if not (after.isalnum() or after == "_"):
                    unit = u.group(1)
        mant = m.group(2).split("e")[0].split("E")[0]
        out.append(Token(m.group(0), abs(Decimal(m.group(2))), sig_digits(mant), unit, m.start()))
    return out


def numeric_hits(text: str, values: Sequence[Protected]) -> list[dict[str, Any]]:
    hits = []
    for t in tokens(text):
        for v in values:
            how = None
            if _matches(t.value, t.sig, v.value):
                how = "value"
            elif t.unit is not None:
                scale, base = UNITS[t.unit]
                if base == v.base and _matches(t.value * scale, t.sig, v.base_value):
                    how = f"value_in_{base}"
            if how:
                ctx = text[max(0, t.start - 30):t.start + len(t.text) + 12].replace("\n", " ")
                hits.append({"protected": v.name, "token": t.text, "unit": t.unit, "match": how, "context": ctx})
    return hits


# --------------------------------------------------------------------------------------------------- text scanner
STATIC_IDENTITY = [
    "NASA", "PCoE", "FY08Q4", "BatteryAgingARC", "B0005", "B0006", "B0007", "B0018", "HG2", "McMaster", "Kollmeyer",
    "Mendeley", "cp3473x7xv", "Digatron", "Kirkaldy", "forge-data", "549_", "551_", "battery_1rc_closure",
    "battery_1rc_identifiability", "battery_1rc_crosscell", "thevenin_route", "nasa_battery_aging", "IDENTITY_MAP",
    "PACK_PROVENANCE", "CALIBRATION.json", "VALIDATION.json", "OUTCOME.json", "UNCERTAINTY_REPORT", "SENSITIVITY.json",
    "PREREGISTRATION", "EVALUATION.json", "EVALUATION_AMENDMENT", "AMENDMENT_01", "V0_HISTORY", "0eae4585baf3",
    "fa818ab4db5d", "d022afa086ef", "82302a7db4fc", "70ffb357511d", "d9b9dd9b9b84", "52eff1a8d273", "408f9dc4b174",
    "35bb500c2934", "d8acfb269758",
]
VERDICT = ["NOT_IDENTIFIABLE", "WEAKLY_IDENTIFIABLE", "IDENTIFIABILITY_SUPPORTED", "MODEL_REJECTED",
           "MODEL_VALIDATION_SUPPORTED", "PARTIALLY_CLOSED", "INSUFFICIENT_MEASUREMENT_EVIDENCE", "EVIDENCE_BACKED",
           "LEAKAGE_INVALIDATED", "REPRESENTATION_BOTTLENECK", "NO_MEASURED_ADVANTAGE", "PROMISING_SIGNAL"]
PLATFORM_EXEMPT = {"NASA"}


def identity_tokens() -> list[str]:
    tokens_ = set(STATIC_IDENTITY)
    ev = HERE / "evaluator"
    for entries in json.loads((ev / "IDENTITY_MAP.json").read_bytes()).values():
        for e in entries.values():
            tokens_.add(pathlib.PurePosixPath(e["source_file"]).name)
            for k in ("cell", "test"):
                if k in e:
                    tokens_.add(str(e[k]))
    for entry in json.loads((ev / "PACK_PROVENANCE.json").read_bytes()).values():
        tokens_ |= {d[:12] for d in entry["source_data_sha256"].values()}
    return sorted(tokens_)


def text_hits(text: str, *, platform: bool = False) -> list[str]:
    idt = [t for t in identity_tokens() if not (platform and t in PLATFORM_EXEMPT)]
    return sorted({t for t in idt if t in text} | ({t for t in VERDICT if t in text} if not platform else set()))


# --------------------------------------------------------------------------------------------- file-level audits
def candidate_files() -> list[pathlib.Path]:
    files = [p for p in CANDIDATE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(files + sorted(MIND_SRC.glob("*.py")))


def _name(p: pathlib.Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT)).replace(os.sep, "/")
    except ValueError:
        return str(p)


MEASUREMENT_KEYS = ("t_s", "current_A", "voltage_V", "temperature_C", "knots_z_V")


def scannable_text(p: pathlib.Path) -> str:
    """The text the numeric scanner reads: a JSON file without its measurement arrays (each replaced by a marker),
    any other file as it is."""
    raw = p.read_bytes().decode("utf-8", errors="replace")
    if p.suffix != ".json":
        return raw

    def strip(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: ("<measurement array: provenance-checked>" if k in MEASUREMENT_KEYS and isinstance(v, list)
                        else strip(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    try:
        return json.dumps(strip(json.loads(raw)), sort_keys=True, indent=1, ensure_ascii=False)
    except ValueError:
        return raw


def numeric_findings(files: Iterable[pathlib.Path], values: Sequence[Protected]) -> list[dict[str, Any]]:
    out = []
    for p in files:
        hits = numeric_hits(scannable_text(p), values)
        if hits:
            out.append({"file": _name(p), "hits": hits})
    return out


def provenance_findings(pack_dir: pathlib.Path = CANDIDATE / "pack") -> list[dict[str, Any]]:
    """Every pack file must equal, byte for byte, what the builder makes from the pinned split data files."""
    from . import build_pack  # noqa: PLC0415  (evaluator side; reads only the pinned split DATA files)

    out = []
    for pid, builder in (("P1", build_pack.build_p1), ("P2", build_pack.build_p2)):
        problem, _, _ = builder()
        expected = (json.dumps(problem, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
        path = pack_dir / f"{pid}.json"
        if not path.exists() or path.read_bytes() != expected:
            out.append({"file": path.name, "finding": "differs from the rebuild from the pinned split data"})
    manifest = json.loads((pack_dir / "MANIFEST.json").read_bytes())
    for pid, entry in manifest["problems"].items():
        if hashlib.sha256((pack_dir / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
            out.append({"file": entry["file"], "finding": "differs from MANIFEST.json"})
    return out


def text_findings(files: Iterable[pathlib.Path]) -> list[dict[str, Any]]:
    out = []
    for p in files:
        hits = text_hits(p.read_bytes().decode("utf-8", errors="replace"))
        if hits:
            out.append({"file": _name(p), "tokens": hits})
    return out


PACK_KEYS = {
    "schema", "problem_id", "description", "declared_model", "family", "equations", "requested_parameters", "bounds",
    "R0_ohm", "R1_ohm", "C1_F", "ocv", "status", "knots_soc", "bounds_V", "knots_z_V", "interpolation", "conventions",
    "current_sign", "rest_band_A", "hold", "initial_polarization_V", "initial_soc", "capacity_basis", "scored_samples",
    "measurement_uncertainty", "voltage_V", "current_A", "temperature_C", "time_s", "half_width", "standard_uncertainty",
    "distribution", "basis", "acceptance", "rmse_mV_max", "p95_abs_mV_max", "applicability", "widen_by", "soc", "min",
    "max", "set_rule", "questions", "MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION",
    "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY", "vocabulary", "sets", "calibration", "trajectories", "subsets", "id",
    "cell", "kind", "t_s", "z0", "capacity_Ah", "problems", "file", "sha256", "P1", "P2",
    "within_cell_heldout", "cross_cell_heldout", "later_cycles", "other_cell", "pulses", "cc",
    "within_cell_heldout/later_cycles", "cross_cell_heldout/other_cell", "within_cell_heldout/pulses",
    "within_cell_heldout/cc",
}


def schema_findings(pack_dir: pathlib.Path = CANDIDATE / "pack") -> list[dict[str, Any]]:
    out = []

    def walk(o: Any, path: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k not in PACK_KEYS:
                    out.append({"file": path, "unexpected_key": k})
                walk(v, path)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    walk(v, path)

    for p in sorted(pack_dir.glob("*.json")):
        walk(json.loads(p.read_bytes()), p.name)
    return out


FORBIDDEN_MODULE_PREFIXES = ("benchmarks.battery_rediscovery_v1.evaluator", "benchmarks.battery_rediscovery_v1.leakage",
                             "benchmarks.battery_rediscovery_v1.mutation", "benchmarks.battery_rediscovery_v1.freeze",
                             "benchmarks.battery_rediscovery_v1.seal", "benchmarks.battery_rediscovery_v1.launch",
                             "benchmarks.battery_rediscovery_v1.v0_history", "benchmarks.battery_rediscovery_v1.build_pack",
                             "benchmarks.battery_rediscovery_v0",
                             "benchmarks.battery_1rc", "tools.nasa_battery")
ALLOWED_FILES = ("benchmarks/__init__.py", "benchmarks/battery_rediscovery_v1/__init__.py",
                 "benchmarks/battery_rediscovery_v1/sandbox_run.py")


def _under(path: str, roots: Iterable[pathlib.Path]) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    return any(p == os.path.normcase(str(r)) or p.startswith(os.path.normcase(str(r)) + os.sep) for r in roots)


def runtime_findings(log: dict[str, Any], out_dirs: Sequence[pathlib.Path]) -> dict[str, Any]:
    roots = [CANDIDATE, ROOT / "src" / "engcore", pathlib.Path(sys.prefix).resolve(),
             pathlib.Path(sys.base_prefix).resolve(), *[d.resolve() for d in out_dirs]]
    allowed_files = {os.path.normcase(str(ROOT / f)) for f in ALLOWED_FILES}
    listable = {os.path.normcase(str(p)) for p in (ROOT, ROOT / "src", ROOT / "benchmarks", HERE)}
    bad, engcore = [], []
    for path, mode in log["opened"]:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in allowed_files or (mode == "list" and norm in listable):
            continue
        if not _under(path, roots):
            bad.append([path, mode])
        elif _under(path, [ROOT / "src" / "engcore"]) and path.endswith(".py"):
            engcore.append(path)
    platform_identity = []
    for path in sorted(set(engcore)):
        hits = text_hits(pathlib.Path(path).read_bytes().decode("utf-8", errors="replace"), platform=True)
        if hits:
            platform_identity.append({"file": path, "tokens": hits})
    return {"paths_outside_roots": bad,
            "forbidden_modules": sorted(m for m in log["modules"] if m.startswith(FORBIDDEN_MODULE_PREFIXES)),
            "platform_identity_tokens": platform_identity, "engcore_files_opened": len(set(engcore)),
            "paths_opened": len(log["opened"])}


def audit(values: Sequence[Protected], *, access_logs: Sequence[pathlib.Path] = (),
          out_dirs: Sequence[pathlib.Path] = (), phase: str) -> dict[str, Any]:
    files = candidate_files()
    numeric = numeric_findings(files, values)
    text = text_findings(files)
    schema = schema_findings()
    provenance = provenance_findings()
    runtime = {str(_name(log)): runtime_findings(json.loads(log.read_bytes()), out_dirs) for log in access_logs}
    bad_runtime = any(r["paths_outside_roots"] or r["forbidden_modules"] or r["platform_identity_tokens"]
                      for r in runtime.values())
    failed = bool(numeric or text or schema or provenance or bad_runtime)
    return {"schema": "forge.battery_rediscovery.leakage_audit/2", "scanner": f"{SCANNER_ID}@{SCANNER_VERSION}",
            "phase": phase, "status": "LEAKAGE_INVALIDATED" if failed else "PASS", "numeric": numeric, "text": text,
            "pack_schema": schema, "provenance": provenance, "runtime": runtime, "files_scanned": len(files),
            "protected_values": [{"name": v.name, "value": str(v.value), "unit": v.unit} for v in values]}


__all__ = ["Protected", "SCANNER_VERSION", "audit", "candidate_files", "identity_tokens", "numeric_findings",
           "numeric_hits", "protected", "provenance_findings", "round_sig", "scannable_text", "runtime_findings", "schema_findings", "text_findings", "text_hits",
           "tokens"]
