"""Round-13 local mutation challenge: apply one mutant to src/engcore/mind/world/owners.py in a tree copy.

Usage: python mutate_r13_local.py <tree> <mutant>.  Each mutant restores one defect the round-13 fixes removed, or one
the round-12 fixes removed (re-checked on the rewritten code); each replacement must match exactly once."""
import sys

root, name = sys.argv[1], sys.argv[2]
O = "src/engcore/mind/world/owners.py"
M = {
    # F13-02 / R13-C-F1: a state not read back observed as entry objects
    "unread_length_only": [("    return len(entries) >= len(prefix) and all(a is b for a, b in zip(entries, prefix))",
                            "    return len(entries) >= len(prefix)")],
    "no_note_unread": [("                        observed[key] = self._note_unread(key, got.entries) or got.why",
                        "                        observed[key] = got.why")],
    "no_unread_check_on_read": [("                unread = self._unread_entries.get(key)\n"
                                 "                if unread is not None and (before is None or not _extends(before, unread)):",
                                 "                unread = self._unread_entries.get(key)\n"
                                 "                if False:")],
    "no_unread_post_wait": [("                    elif unread is not None and (before is None or not _extends(before, unread)):",
                             "                    elif False:")],
    "unread_not_cleared": [("                self._unread_entries.pop(key, None)  # it moved on",
                            "                pass  # it moved on")],
    "unreadable_entries_tolerated": [("        if entries is None:\n            return _NotRead(f\"{why}; which entries",
                                      "        if False:\n            return _NotRead(f\"{why}; which entries"),
                                     ("        return _NotRead(why, False, entries)\n",
                                      "        return _NotRead(why, False, entries or ())\n")],
    # R13-C-F2 / R13-A-F1 / F13-03: BaseException content and interrupts
    "base_exception_not_classified": [("        except BaseException as exc:  # noqa: BLE001 - classified by the caller over several attempts\n"
                                       "            if _interrupt(exc):\n                raise\n",
                                       "        except Exception as exc:  # noqa: BLE001 - classified by the caller over several attempts\n")],
    "described_exception_only": [("    except BaseException as failed:  # noqa: BLE001 - a message that cannot be rendered is no message, never an escape\n"
                                  "        if _interrupt(failed):\n            raise\n",
                                  "    except Exception:  # noqa: BLE001 - a message that cannot be rendered is no message, never an escape\n")],
    "interrupt_not_caught": [("            except BaseException as exc:  # noqa: BLE001 - an interrupt (or the caller's stack): re-raised after comparing",
                              "            except _Failed as exc:  # never raised here")],
    "interrupt_swallowed": [("        if interrupted is not None:\n            raise interrupted\n",
                             "        if False:\n            raise interrupted\n")],
    # R13-B-F1: the mapping's entries listed without hashing its keys
    "items_trust_mapping": [("    if not issubclass(type(mapping), dict):\n"
                             "        raise TypeError(f\"an account mapping is a dict, not a {_type_name(mapping)}\")\n"
                             "    return list(dict.items(mapping))\n",
                             "    return list(dict(mapping or {}).items())\n")],
    "ctor_dict": [("            try:\n                listed = _items(mapping)\n",
                   "            try:\n                listed = list(dict(mapping or {}).items())\n")],
    "unread_keeps_shorter": [("        elif not _extends(earlier, entries):\n            self._diverged[key] = self._rewrote_unread(key)\n",
                              "        elif _extends(earlier, entries):\n            self._unread_entries[key] = entries\n"
                              "        else:\n            self._diverged[key] = self._rewrote_unread(key)\n")],
    # fresh-thread MINORs
    "box_before_alive": [("        thread.join(max(0.0, self._deadline - time.monotonic()))\n",
                          "        thread.join(max(0.0, self._deadline - time.monotonic()))\n        early = box.get(\"result\")\n"),
                         ("        result = box.get(\"result\")\n        if result is None:\n            raise OwnerUnavailable(f\"{what} was not read back: its read-back on a fresh thread ended",
                          "        result = early\n        if result is None:\n            raise OwnerUnavailable(f\"{what} was not read back: its read-back on a fresh thread ended")],
    "no_one_thread_per_account": [("        if earlier is not None and earlier.is_alive():", "        if False:")],
    "no_shared_deadline": [("        thread.join(max(0.0, self._deadline - time.monotonic()))\n", "        thread.join(self.WAIT_S)\n")],
    "shared_cache": [("        cache = dict(self._readback)\n", "        cache = self._readback\n")],
    "discard_at_compare_start": [("            pending = self._in_flight - {ticket}\n",
                                  "            self._in_flight.discard(ticket)\n            pending = set(self._in_flight)\n")],
    # round-11 abandonment guards (the restated r11 control)
    "no_abandon": [("                        waiter[1] = True", "                        pass")],
    "handed_never_set": [("            handed = True\n", "            handed = False\n")],
    # round-12 guards, re-checked on the rewritten code
    "render_raw": [("            why = _described(exc)\n", "            why = f\"{type(exc).__name__}: {exc}\"\n")],
    "no_spelled_check": [("                if key in spelled:", "                if False:")],
    "ctor_no_spelling_check": [("                if str.__str__(raw_id) in entries:", "                if False:")],
    "recursion_direct_only": [("    pending, seen = [exc], set()\n",
                               "    return issubclass(type(exc), RecursionError)\n    pending, seen = [exc], set()\n")],
    "fresh_single_attempt": [("                box[\"result\"] = self._attempts(key, cache)\n",
                              "                try:\n"
                              "                    box[\"result\"] = (self._read_once(key, cache), [])\n"
                              "                except _Failed as failed:\n"
                              "                    box[\"result\"] = (None, [failed])\n")],
    "join_unbounded": [("        thread.join(max(0.0, self._deadline - time.monotonic()))\n", "        thread.join()\n")],
    "timeout_for_good": [("            raise OwnerUnavailable(f\"{what} was not read back: its read-back on a fresh thread had not completed",
                          "            raise _Unreadable(f\"{what} was not read back: its read-back on a fresh thread had not completed")],
    "id_str_call": [("                key = (kind, str.__str__(raw_id))    # the plain str it spells (no code of the id runs)",
                     "                key = (kind, str(raw_id))")],
    "differ_not_moving": [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                           "        if any(f.moving for f in failures):")],
    "why_only": [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                  "        if any(f.moving for f in failures) or len({f.why for f in failures}) > 1:")],
    "alias_not_recorded2": [("                self._seen[key] = history\n                unread = self._unread_entries.get(key)\n",
                             "                if key not in snapshot._aliased:\n                    self._seen[key] = history\n"
                             "                unread = self._unread_entries.get(key)\n")],
    "fresh_thread_no_flag": [("        def run() -> None:\n            self._in_follow.active = True\n",
                              "        def run() -> None:\n            self._in_follow.active = False\n")],
}
path = f"{root}/{O}"
with open(path, "rb") as f:
    s = f.read().decode("utf-8")
for old, new in M[name]:
    assert s.count(old) == 1, (name, old[:70], s.count(old))
    s = s.replace(old, new)
with open(path, "wb") as f:
    f.write(s.encode("utf-8"))
print("applied", name)
