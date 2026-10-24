"""Migration adapter for synthetic callback owners in historical authority controls.

The callback prepares a proposed binding; publish commits it before reader handoff.
This helper is NOT a production promise about an arbitrary callback's intermediate
unpublished local states. Source generations are retained across all calls.
"""
from engcore.mind.world.owners import AccountPublication, BudgetReader

def following(accounts, owner_id="budget"):
    source = AccountPublication()
    def published():
        value = accounts()
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            return value  # malformed handing still challenges reader sealing
        return source.publish(*value)
    return BudgetReader.following(published, owner_id)
