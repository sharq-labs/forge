"""Deterministic semantic mutants; isolated export, never mutate a checkout."""
from pathlib import Path
import hashlib, io, json, os, shutil, subprocess, tarfile, tempfile
ROOT = Path("/home/dev_kaeem/forge-gen2-authority-v1")
EV = ROOT / "docs/work/evidence/br11_local_2026_10_23/round15"
TREE = Path(tempfile.mkdtemp(prefix="r15-mutants-", dir="/home/dev_kaeem/br11-review"))
archive = subprocess.check_output(["git", "archive", "95f3869e"], cwd=ROOT)
with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
    tf.extractall(TREE, filter="data")
paths = ["src/engcore/mind/world/owners.py", "tests/mind/test_authority_review_r14.py",
         "tests/mind/test_authority_review_r15.py", "tests/mind/test_authority_state_machine_r15.py"]
for name in paths:
    shutil.copy2(ROOT/name, TREE/name)
source = (ROOT/paths[0]).read_text()
owner = TREE/paths[0]
python = str(ROOT/".venv/bin/python")
args = [python, "-m", "pytest", "tests/mind/test_authority_review_r15.py",
        "tests/mind/test_authority_state_machine_r15.py", "tests/mind/test_authority_review_r13.py::test_a_dict_subclass_never_hides_a_handed_account", "-q", "-p", "no:cacheprovider"]
env = dict(os.environ, PYTHONPATH=f"{TREE}/src:{TREE}", PYTHONDONTWRITEBYTECODE="1")
results = []
def run(name, code):
    owner.write_text(code)
    result = subprocess.run(args,cwd=TREE,env=env,capture_output=True,text=True,timeout=90)
    log = result.stdout + result.stderr
    (EV/f"mutant_{name}.log").write_text(log)
    row = dict(name=name,exit_code=result.returncode,
               source_sha256=hashlib.sha256(code.encode()).hexdigest(),
               command=args,cwd=str(TREE),failures=[x for x in log.splitlines() if x.startswith("FAILED ")],
               summary=log.splitlines()[-1] if log.splitlines() else "")
    results.append(row)
    print(name, result.returncode, row["summary"],flush=True)
    return row
baseline = subprocess.check_output(["git","show","95f3869e:"+paths[0]],cwd=ROOT,text=True)
run("reviewed_prefix",baseline)
run("control",source)
def changed(old,new):
    assert old in source,old
    return source.replace(old,new,1)
first = """            if self._sealed is not None:
                if interrupted is not None:
                    raise interrupted
                raise OwnerUnavailable(self._sealed)
"""
after = """                if self._sealed is not None:
                    raise OwnerUnavailable(self._sealed)
"""
mutants = {
 "discard_interrupted_handing": changed("    def _recover_handing(self, ticket: int) -> None:\n", "    def _recover_handing(self, ticket: int) -> None:\n        self._uncompared.pop(ticket, None)\n        return\n"),
 "retain_live_mapping": changed("self._uncompared[ticket] = BudgetReader._retain_handing(mapping)", "self._uncompared[ticket] = mapping"),
 "handing_dictionary_copy": changed("return _RetainedHanding(tuple(_items(m) for m in maps))", "return _RetainedHanding(tuple(_items(None if m is None else dict.copy(m)) for m in maps))"),

 "exact_pair_type": changed("pair = tuple if issubclass(type(handed), tuple) else list if issubclass(type(handed), list) else None", "pair = type(handed) if type(handed) in (tuple, list) else None"),
 "reread_retired_content": changed("            if key in snapshot._skip:\n                continue                            # retired accounts never run their content again\n", ""),
 "seal_entry_only": source.replace(first,"").replace(after,""),
 "no_comparison_seal": changed(first,""),
 "no_post_wait_seal": changed(after,""),
 "interrupt_poison": changed("except _InvalidHanding as exc:  # structural evidence, never an asynchronous interruption",
                            "except BaseException as exc:  # mutant: any interruption poisons the reader"),
 "no_reconciliation": changed("""                if (before is None or after is None or len(before) != len(after)
                        or not _extends(before, after) or len(history) != len(after)):""",
                             "                if False:"),
 "no_history_count": changed("or not _extends(before, after) or len(history) != len(after)", "or not _extends(before, after)"),
 "drop_before_observation": changed("        if before is not None and entries is not None:", "        if False:"),
 "comparison_outside_lock": changed("            for key, got in read.items():", "            self._changed.release()\n            for key, got in read.items():").replace(
     "            self._in_flight.discard(ticket)          # compared:", "            self._changed.acquire()\n            self._in_flight.discard(ticket)          # compared:"),
 "no_retained_history_reconciliation": changed("for key, entries in snapshot._unread_entries.items():", "for key, entries in {}.items():"),
 "listing_outside_interrupt_guard": changed("""            before = None
            try:
                before = self._entries(key)""", """            before = self._entries(key)
            try:"""),
 "interrupt_implicit_success": changed("        if interrupted is not None:\n            raise interrupted\n        return observed", "        return observed"),
}
mutants["listing_outside_without_handing_recovery"] = mutants["listing_outside_interrupt_guard"].replace(
    "    def _recover_handing(self, ticket: int) -> None:\n",
    "    def _recover_handing(self, ticket: int) -> None:\n        self._uncompared.pop(ticket, None)\n        return\n", 1)
for name, code in mutants.items():
    run(name,code)
owner.write_text(source)
(EV/"mutations.json").write_text(json.dumps(results,indent=2)+"\n")
assert results[1]["exit_code"] == 0, "unmutated control failed"
for r in results[2:]:
    if r["name"] == "listing_outside_interrupt_guard":
        assert r["exit_code"] == 0
        r["justification"] = "Existing interrupted-handing recovery preserves the same entries even when listing leaves the inner guard. Redundant guard removal, not a correctness mutation after R15-REPAIR-3. Compound removal of listing guard and recovery is independently killed."
    else:
        assert r["exit_code"] == 1 and r["failures"], "a correctness mutant survived or failed for a harness reason"
(EV/"mutations.json").write_text(json.dumps(results,indent=2)+"\n")
print(f"{len(mutants)-1} correctness mutants deterministically killed; one redundant guard removal justified by retained recovery")
