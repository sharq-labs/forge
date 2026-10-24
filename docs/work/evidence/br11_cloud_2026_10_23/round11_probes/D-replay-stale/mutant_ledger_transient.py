"""R11-D mutant: ledgers whose state their owner cannot write down / read back are refused for that verification only
(the round-9 behaviour) instead of for good; experiments unchanged.  argv[1]: tree."""
import sys
p = sys.argv[1] + "/src/engcore/mind/world/owners.py"
s = open(p).read()
old1 = ('            text_ = _written(lambda: json.dumps(BudgetLedger.from_dict(ledger.to_dict()).to_dict(), sort_keys=True,\n'
        '                                                separators=(",", ":"), default=str), what)\n')
new1 = ('            try:\n'
        '                text_ = _written(lambda: json.dumps(BudgetLedger.from_dict(ledger.to_dict()).to_dict(), '
        'sort_keys=True, separators=(",", ":"), default=str), what)\n'
        '            except _Unreadable as e:\n'
        '                raise OwnerUnavailable(str(e)) from None\n')
old2 = ('            except Exception as exc:  # noqa: BLE001 - a ledger its owner cannot read back from its own text\n'
        '                raise _Unreadable(')
new2 = ('            except Exception as exc:  # noqa: BLE001 - a ledger its owner cannot read back from its own text\n'
        '                raise OwnerUnavailable(')
for o, n in ((old1, new1), (old2, new2)):
    assert s.count(o) == 1, o[:60]
    s = s.replace(o, n)
open(p, "w").write(s)
print("applied ledger_transient")
