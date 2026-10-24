"""F10 f05: mutants of the round-9 changes, applied one at a time to a FULL tree copy of c69e579 (tree-mut), each run
against the authority test files from that tree's own root; reports which tests (if any) fail per mutant."""
import pathlib
import subprocess
import sys

D = pathlib.Path(__file__).parent
T = D / "tree-mut"
PY = "/home/user/.forge-venv/bin/python"
W = T / "src/engcore/mind/world"
MUTANTS = {
    "M1_alias_readback (from_dict(payload), back=rebuilt.to_dict())": [
        (W / "owners.py", "rebuilt = ScientificExperiment.from_dict(json.loads(text))", "rebuilt = ScientificExperiment.from_dict(payload)"),
        (W / "owners.py", "back = json.loads(to_json(rebuilt))", "back = rebuilt.to_dict()")],
    "M2_no_ticket_rule (earlier = False)": [
        (W / "owners.py", "earlier = any(t < ticket for t in self._in_flight)", "earlier = False")],
    "M3_any_other_in_flight (stricter rule)": [
        (W / "owners.py", "earlier = any(t < ticket for t in self._in_flight)", "earlier = bool(self._in_flight)")],
    "M4_no_cache_prune": [
        (W / "owners.py", "self._readback = {k: v for k, v in self._readback.items() if k in read}", "pass")],
    "M5_bind_raw_conversion": [
        (W / "actions.py", "executed = _fixed_as_executed(var.domain, f.value, var.unit)", "executed = as_unit(f.value, var.unit)")],
    "M6_level_problem_any_level": [
        (W / "feasibility.py", "if not isinstance(executed, Quantity) or canonical_bytes(value_payload(executed)) != canonical_bytes(\n            value_payload(as_unit(level, unit))):", "if not is_declared_level(world, spec, name, executed):")],
    "M7_stale_for_any_other": [
        (W / "projection.py", "        if older:                                     # an older revision: STALE speaks", "        if True:                                      # an older revision: STALE speaks")],
    "M8_memo_clears_pin_error": [
        (W / "authority.py", "            raise self._pin_error\n", "            error, self._pin_error = self._pin_error, None\n            raise error\n")],
    "M9_ledger_not_plain_checked": [
        (W / "owners.py", "                if not _plain(raw):\n                    raise ValueError(\"its serialization is not plain JSON data\")", "                pass")],
    "M10_experiment_not_plain_checked": [
        (W / "owners.py", "            if not _plain(payload):                  # exact JSON types only", "            if False:                  # exact JSON types only")],
    "M11_read_back_under_lock": [
        (W / "owners.py", "        read = snapshot._read_back()\n        observed: dict[tuple[str, str], OwnerRecord | str | None] = {}\n        with self._lock:\n",
         "        observed: dict[tuple[str, str], OwnerRecord | str | None] = {}\n        with self._lock:\n            read = snapshot._read_back()\n")],
    "M12_waiting_not_applied (records but decides)": [
        (W / "owners.py", "            if earlier:\n                waiting", "            if False:\n                waiting")],
}
TESTS = sys.argv[1:] or ["tests/mind/"]
which = [k for k in MUTANTS]
for name in which:
    edits = MUTANTS[name]
    originals = {}
    ok = True
    for path, old, new in edits:
        text = originals.get(path) or path.read_text()
        originals.setdefault(path, text)
        cur = path.read_text()
        if cur.count(old) != 1:
            print(f"{name}: pattern not found once in {path.name}: {old[:60]!r}")
            ok = False
            break
        path.write_text(cur.replace(old, new))
    if ok:
        r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-x" if False else "-q",
                            f"--basetemp={D}/pt-mut"], cwd=T, capture_output=True, text=True,
                           env={"PYTHONPATH": f"{T}/src:{T}", "PATH": "/usr/bin:/bin"}, timeout=1800)
        fails = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or l.startswith("ERROR")]
        tail = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l]
        print(f"{name}: {tail[-1] if tail else r.stdout[-300:]}")
        for l in fails[:8]:
            print("    ", l[:170])
    for path, text in originals.items():
        path.write_text(text)
