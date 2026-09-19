from engcore.scientific.replay_core.migration import MigrationDecision, assess_migration

def test_schema_change_without_migration_is_refused():
    assert assess_migration("x/1","x/2").decision is MigrationDecision.REFUSED
