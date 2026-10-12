"""tools/test_impact.py -- the developer gate's change-impact selection.

The property that matters: a test a change can reach is selected. Over-selection
costs seconds; a missed test is false confidence. Every rule is checked on a
small synthetic repository, and the real tree is checked for the gap that
motivated the module (a domain model whose own tests the tag rules never ran).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from tools import forge_check, test_impact
from tools.test_impact import ChangeClass, Tiers

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_graph():
    """The repository's own import graph: built once, read-only."""
    return test_impact.build_graph(ROOT)


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    root = tmp_path_factory.mktemp("impact")
    _write(root, "pyproject.toml", '[tool.pytest.ini_options]\npythonpath = ["src", ".", "tests/helpers"]\n')
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/core.py", "VALUE = 1\n")
    _write(root, "src/pkg/sub/__init__.py", "from pkg import core\n")
    _write(root, "src/pkg/sub/leaf.py", "from ..core import VALUE\n")
    _write(root, "src/pkg/lazy.py", "def f():\n    from pkg import late\n    return late\n")
    _write(root, "src/pkg/late.py", "X = 2\n")
    _write(root, "src/pkg/named.py", "Y = 3\n")
    _write(root, "src/pkg/orphan.py", "Z = 4\n")
    _write(root, "tests/helpers/support.py", "import pkg.sub.leaf\n")
    _write(root, "tests/test_chain.py", "from support import *\n")
    _write(root, "tests/test_lazy.py", "import pkg.lazy\n")
    _write(root, "tests/test_string.py", "import importlib\nM = importlib.import_module('pkg.named')\n")
    _write(root, "tests/test_mentions.py", "PATH = 'data/table.json'\nDOC = 'GUIDE_FOR_TESTS.md'\n")
    _write(root, "tests/test_scan.py", "import pathlib\nFILES = list(pathlib.Path('src').rglob('*.py'))\n")
    _write(root, "tests/test_gone.py", "import pkg.removed\n")
    _write(root, "tests/test_unrelated.py", "X = 1\n")
    _write(root, "tests/deep/conftest.py", "")
    _write(root, "tests/deep/test_governed.py", "X = 1\n")
    _write(root, "data/table.json", "{}\n")
    _write(root, "docs/GUIDE_FOR_TESTS.md", "guide\n")
    return root, test_impact.build_graph(root)


def _affected(synthetic, *paths):
    root, graph = synthetic
    return set(test_impact.impact_of(paths, graph).affected)


def test_an_import_chain_through_a_helper_and_a_package_init_is_followed(synthetic) -> None:
    affected = _affected(synthetic, "src/pkg/core.py")
    assert "tests/test_chain.py" in affected  # support -> pkg.sub.leaf -> ..core, and pkg/sub/__init__ -> core
    assert "tests/test_unrelated.py" not in affected


def test_function_level_and_string_imports_count(synthetic) -> None:
    assert "tests/test_lazy.py" in _affected(synthetic, "src/pkg/late.py")
    assert "tests/test_string.py" in _affected(synthetic, "src/pkg/named.py")


def test_a_package_init_reaches_everything_importing_below_it(synthetic) -> None:
    affected = _affected(synthetic, "src/pkg/__init__.py")
    assert {"tests/test_chain.py", "tests/test_lazy.py", "tests/test_string.py"} <= affected


def test_a_data_file_or_document_is_reached_by_tests_that_name_it(synthetic) -> None:
    assert "tests/test_mentions.py" in _affected(synthetic, "data/table.json")
    assert "tests/test_mentions.py" in _affected(synthetic, "docs/GUIDE_FOR_TESTS.md")


def test_every_source_change_reaches_the_tests_that_walk_the_source_tree(synthetic) -> None:
    assert "tests/test_scan.py" in _affected(synthetic, "src/pkg/orphan.py")
    assert "tests/test_scan.py" not in _affected(synthetic, "data/table.json")


def test_a_deleted_module_is_traced_to_its_importers_by_name(synthetic) -> None:
    assert "tests/test_gone.py" in _affected(synthetic, "src/pkg/removed.py")


def test_a_conftest_governs_every_test_below_it(synthetic) -> None:
    affected = _affected(synthetic, "tests/deep/conftest.py")
    assert "tests/deep/test_governed.py" in affected and "tests/test_unrelated.py" not in affected


def test_a_change_no_rule_reaches_is_unresolved_never_silently_empty(synthetic) -> None:
    root, graph = synthetic
    impact = test_impact.impact_of(["assets/blob.bin"], graph)
    assert impact.unresolved == ("assets/blob.bin",) and not impact.affected
    targets = forge_check.build_targets(["assets/blob.bin"], whole_pack=True)
    pack = {case["nodeid"] for case in forge_check.load_manifest()["cases"]}
    assert pack <= set(targets)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("docs/TESTING.md", ChangeClass.DOC_ONLY),
        ("tools/forge_check.py", ChangeClass.TEST_INFRASTRUCTURE),
        ("tools/test_impact.py", ChangeClass.TEST_INFRASTRUCTURE),
        ("tests/conftest.py", ChangeClass.TEST_INFRASTRUCTURE),
        ("src/engcore/scientific/units/quantity.py", ChangeClass.CERTIFICATION_PINNED),
        ("src/engcore/authority/ledger.py", ChangeClass.TRUST_OR_AUTHORITY),
        ("src/engcore/claims/selection.py", ChangeClass.SCIENTIFIC_SHARED),
        ("src/engcore/domains/battery/thevenin.py", ChangeClass.DOMAIN_LOCAL),
        ("tools/nasa_battery_aging.py", ChangeClass.LOCAL_NONSCIENTIFIC),
        ("benchmarks/battery_flagship_b3/round.json", ChangeClass.UNCLASSIFIED),
    ],
)
def test_change_classes_follow_repository_ownership(path, expected) -> None:
    assert test_impact.classify(path) is expected


def test_a_recertification_trigger_is_reported_by_the_ci_classifier_itself() -> None:
    from tools.certification.recertification_scope import recertification_reasons

    for path in ("tools/forge_check.py", "src/engcore/scientific/units/quantity.py", "docs/TESTING.md"):
        assert test_impact.recertification_reasons(path) == recertification_reasons(path)
    assert test_impact.recertification_reasons("tools/forge_check.py")
    assert not test_impact.recertification_reasons("docs/TESTING.md")


def test_the_tier_tables_are_read_exactly_as_conftest_defines_them() -> None:
    spec = importlib.util.spec_from_file_location("_tier_conftest", ROOT / "tests" / "conftest.py")
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)
    tiers = test_impact.load_tiers(ROOT)
    assert tiers.campaign_tests == frozenset(conftest.CAMPAIGN_TESTS)
    assert tiers.expensive_tests == frozenset(conftest.EXPENSIVE_TESTS)
    assert tiers.expensive_modules == frozenset(conftest.EXPENSIVE_MODULES)
    assert dict(tiers.static_guards) == dict(conftest.STATIC_GUARDS)


def test_expensive_affected_tests_are_listed_never_silently_dropped() -> None:
    tiers = Tiers(
        campaign_tests=frozenset({"tests/test_a.py::test_campaign"}),
        expensive_tests=frozenset({"tests/test_a.py::test_slow", "tests/test_b.py::test_x"}),
        expensive_modules=frozenset({"tests/test_heavy.py"}),
        static_guards={"tests/test_heavy.py": frozenset({"test_guard"})},
    )
    texts = {
        "tests/test_a.py": "def test_campaign(): pass\ndef test_slow(): pass\ndef test_fast(): pass\n",
        "tests/test_b.py": "def test_x(): pass\ndef test_x_fast_sibling(): pass\n",
    }
    targets, deselect, left_out = test_impact.split_by_tier(
        ["tests/test_a.py", "tests/test_b.py", "tests/test_heavy.py"], tiers, texts
    )
    assert targets == ["tests/test_a.py", "tests/test_b.py", "tests/test_heavy.py::test_guard"]
    assert deselect == ["tests/test_a.py::test_campaign", "tests/test_a.py::test_slow"]
    # `--deselect` is a prefix match: test_x would also drop test_x_fast_sibling, so test_x runs instead.
    assert "tests/test_b.py::test_x" not in deselect
    assert set(left_out) == {"tests/test_heavy.py", "tests/test_a.py::test_campaign", "tests/test_a.py::test_slow"}


def test_markers_a_module_applies_itself_are_honoured_too() -> None:
    empty = Tiers(frozenset(), frozenset(), frozenset(), {})
    texts = {
        "tests/test_deco.py": (
            "import pytest\n"
            "@pytest.mark.expensive\ndef test_rebuild(): pass\n"
            "@pytest.mark.campaign(reason='big')\nclass TestStudy:\n    def test_it(self): pass\n"
            "def test_cheap(): pass\n"
        ),
        "tests/test_module_marked.py": "import pytest\npytestmark = [pytest.mark.expensive]\ndef test_a(): pass\n",
    }
    targets, deselect, left_out = test_impact.split_by_tier(list(texts), empty, texts)
    assert targets == ["tests/test_deco.py"]
    assert deselect == ["tests/test_deco.py::TestStudy", "tests/test_deco.py::test_rebuild"]
    assert "tests/test_module_marked.py" in left_out


def test_no_tier_deselection_can_drop_a_regression_sentinel(real_graph) -> None:
    """``--deselect`` applies to the whole command: no key may prefix a sentinel node id."""
    graph = real_graph
    sentinels = [case["nodeid"] for case in forge_check.load_manifest()["cases"]]
    modules = sorted({node.split("::", 1)[0] for node in sentinels})
    _, deselect, _ = test_impact.split_by_tier(modules, test_impact.load_tiers(ROOT), graph.texts)
    assert not [(key, node) for key in deselect for node in sentinels if node.startswith(key)]


def test_the_rebuild_tests_that_rewrite_committed_json_are_never_run_by_the_gate(real_graph) -> None:
    """They carry `@pytest.mark.expensive` in the module, not a conftest entry, and rewrite 17 committed files."""
    graph = real_graph
    modules = [
        "benchmarks/empirical_validation/tests/test_empirical_validation.py",
        "benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py",
    ]
    _, deselect, _ = test_impact.split_by_tier(modules, test_impact.load_tiers(ROOT), graph.texts)
    for module in modules:
        assert f"{module}::test_rebuilding_everything_reproduces_the_published_gates" in deselect


def test_a_module_selected_whole_is_not_also_named_node_by_node() -> None:
    sentinel = next(case["nodeid"] for case in forge_check.load_manifest()["cases"])
    module = sentinel.split("::", 1)[0]
    targets = forge_check.build_targets(["src/engcore/claims/selection.py"], affected=[module])
    assert module in targets and not any(t.startswith(module + "::") for t in targets)


def test_the_certified_regression_path_never_loads_the_impact_module(monkeypatch, capsys) -> None:
    monkeypatch.delitem(sys.modules, "tools.test_impact", raising=False)
    import tools as tools_package

    monkeypatch.delattr(tools_package, "test_impact", raising=False)
    assert forge_check.main(["--regression", "--dry-run"]) == 0
    assert "tools.test_impact" not in sys.modules
    assert "--deselect" not in capsys.readouterr().out


def test_the_old_gap_a_domain_models_own_tests_are_now_selected(real_graph) -> None:
    """A thevenin edit used to run only tag sentinels; its own test module was never selected."""
    graph = real_graph
    impact = test_impact.impact_of(["src/engcore/domains/battery/thevenin.py"], graph)
    assert "tests/domains/test_battery_thevenin.py" in impact.affected
    assert "tests/domains/test_battery_thevenin.py" not in forge_check.build_targets(
        ["src/engcore/domains/battery/thevenin.py"]
    )
    assert not graph.unparseable
