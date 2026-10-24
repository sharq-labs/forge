"""Apply one mutant of owners.py in the aad2f69 tree copy, run the BR1.1 suite there (not expensive), restore."""
import pathlib
import subprocess
import sys

TREE = pathlib.Path(__file__).parent / "tree-aad2f69"
OWNERS = TREE / "src/engcore/mind/world/owners.py"
BASE = pathlib.Path(__file__).parent

MUTANTS = {
    # no diverged re-check after the wait (the 'behind' re-check kept)
    "M2_no_diverged_recheck": (
        "                    if key in self._diverged:\n                        observed[key] = self._diverged[key]\n"
        "                    elif len(self._seen.get(key, ())) > len(history):",
        "                    if len(self._seen.get(key, ())) > len(history):"),
    # the wait's timeout ignored: decide on what is observed even if one is still in flight
    "M8_timeout_ignored": (
        "if not self._changed.wait_for(lambda: not pending & self._in_flight, timeout=self.WAIT_S):",
        "if not (self._changed.wait_for(lambda: not pending & self._in_flight, timeout=self.WAIT_S) or True):"),
    # an experiment its owner's from_dict cannot read back from its own text: for this verification only
    "M12_exp_fromdict_transient": (
        "            except Exception as exc:  # noqa: BLE001 - an experiment its owner cannot read back from its own text\n"
        "                raise _Unreadable(",
        "            except Exception as exc:  # noqa: BLE001 - an experiment its owner cannot read back from its own text\n"
        "                raise OwnerUnavailable("),
    # a ledger its owner's from_dict cannot read back from its JSON text: for this verification only
    "M11_ledger_fromdict_transient": (
        "            except Exception as exc:  # noqa: BLE001 - a ledger its owner cannot read back from its own text\n"
        "                raise _Unreadable(",
        "            except Exception as exc:  # noqa: BLE001 - a ledger its owner cannot read back from its own text\n"
        "                raise OwnerUnavailable("),
    # every non-recursion failure of the owner's serialization: for this verification only (no refusal for good)
    "M10_written_all_transient": (
        "    except Exception as exc:  # noqa: BLE001 - a state its owner cannot write down is unreadable\n"
        "        raise _Unreadable(",
        "    except Exception as exc:  # noqa: BLE001 - a state its owner cannot write down is unreadable\n"
        "        raise OwnerUnavailable("),
    # the torn-accounting check removed
    "M13_no_torn_check": (
        "            if back[\"accounting\"] != written[\"accounting\"] or back[\"budget\"] != written[\"budget\"]:",
        "            if False:"),
    # RecursionError treated as a move (for this verification only)
    "M14_recursion_transient": (
        "    except RecursionError as exc:\n        raise _Unreadable(",
        "    except RecursionError as exc:\n        raise OwnerUnavailable("),
}


def run(name):
    old, new = MUTANTS[name]
    src = OWNERS.read_text()
    assert src.count(old) == 1, (name, src.count(old))
    OWNERS.write_text(src.replace(old, new))
    try:
        cmd = [str(pathlib.Path("/home/user/.forge-venv/bin/python")), "-m", "pytest", "tests/mind",
               "benchmarks/mind_gen2_authority_v1/tests", "benchmarks/mind_gen2_world_v1/tests",
               "tests/test_sria_budget_ledger_identity.py", "-q", "-p", "no:cacheprovider", "-m", "not expensive",
               "-n", "4", f"--basetemp={BASE}/pt-{name}"]
        env = {"PYTHONPATH": f"{TREE}/src:{TREE}", "PATH": "/usr/bin:/bin", "HOME": "/root"}
        p = subprocess.run(cmd, cwd=TREE, env=env, capture_output=True, text=True, timeout=1500)
        tail = [l for l in p.stdout.splitlines() if l.startswith("FAILED") or " passed" in l or " failed" in l]
        print(f"== {name}: rc={p.returncode}")
        print("\n".join(tail[-12:]))
    finally:
        OWNERS.write_text(src)
        subprocess.run(["rm", "-rf", f"{BASE}/pt-{name}"])


for n in (sys.argv[1:] or MUTANTS):
    run(n)
