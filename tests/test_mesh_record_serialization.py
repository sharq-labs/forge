"""Baseline wire compatibility and fresh mutation checks for mesh serialization."""
from dataclasses import fields, replace
import json
from pathlib import Path

import pytest

from engcore.numerical.core import NumericalRefusal
from engcore.numerical.mesh_adaptation import Grid1D, MeshLineage1D, MeshVersion1D
from engcore.scientific.units.quantity import Quantity


def lineage():
    return MeshLineage1D(Grid1D((0., 1., 4.), "m"), root_context="serialization-fixture",
                         coordinate_frame="fixture:axis")


def test_root_refine_coarsen_wires_match_the_preoptimization_baseline():
    expected = json.loads((Path(__file__).parent / "fixtures/mesh_serialization_baseline.json").read_text())
    assert expected["baseline_sha"] == "d05b25eec565b48b4a024799cbda4f046e872d6c"
    owner = lineage()
    root = owner.current
    change = owner.refine(tuple(c.cell_id for c in root.cells), minimum_cell=Quantity(.01, "m"), max_ratio=10)
    fine = owner.current
    owner.coarsen(change.bisections, max_ratio=10)
    actual = [m.to_dict() for m in (root, fine, owner.current)]
    assert actual == expected["records"]
    assert json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(expected["records"], sort_keys=True, separators=(",", ":"))
    owner.verify()


@pytest.mark.parametrize("target,attribute,value", [
    ("mesh", "root_context", "changed"),
    ("mesh", "coordinate_frame", "changed"),
    ("mesh", "policy", (("injected", "changed"),)),
    ("grid", "nodes", (0., 1., 5.)),
    ("grid", "unit", "mm"),
    ("cell", "parent_id", "changed"),
    ("cell", "right", 1.5),
])
def test_serializing_does_not_cache_nested_mutations(target, attribute, value):
    owner = lineage()
    mesh = owner.current
    before = mesh.to_dict()
    selected = {"mesh": mesh, "grid": mesh.grid, "cell": mesh.cells[0]}[target]
    object.__setattr__(selected, attribute, value)
    after = mesh.to_dict()
    assert after != before
    assert after["version_id"] != before["version_id"]
    with pytest.raises(NumericalRefusal, match="unissued, substituted or tampered mesh record"):
        owner._issued.require(mesh)


def test_serialized_payload_edits_do_not_persist_and_equal_substitution_is_rejected():
    owner = lineage()
    mesh = owner.current
    before = mesh.to_dict()
    wire = mesh.to_dict()
    wire["grid"]["nodes"][1] = 99
    wire["cells"][0]["parent_id"] = "forged"
    wire["policy"]["forged"] = "value"
    assert mesh.to_dict() == before
    owner._issued.require(mesh)
    foreign = replace(mesh)
    assert foreign.to_dict() == before
    with pytest.raises(NumericalRefusal, match="unissued, substituted or tampered mesh record"):
        owner._issued.require(foreign)


@pytest.mark.parametrize("raises", [False, True])
def test_mesh_subclass_version_override_and_exception_are_preserved(raises):
    events = []

    class CustomVersion(MeshVersion1D):
        def _material(self):
            events.append("material")
            return super()._material()

        @property
        def version_id(self):
            events.append("version")
            if raises:
                raise RuntimeError("custom version failure")
            return "custom-version"

    original = lineage().current
    custom = CustomVersion(**{f.name: getattr(original, f.name) for f in fields(original)})
    if raises:
        with pytest.raises(RuntimeError, match="^custom version failure$"):
            custom.to_dict()
    else:
        assert custom.to_dict()["version_id"] == "custom-version"
    assert events == ["material", "version"]


def test_nested_grid_subclass_retains_each_serialization_call_and_failure():
    calls = []

    class CustomGrid(Grid1D):
        def to_dict(self):
            calls.append(None)
            if len(calls) == 2:
                raise RuntimeError("second grid serialization")
            return super().to_dict()

    mesh = replace(lineage().current, grid=CustomGrid((0., 1., 4.), "m"))
    with pytest.raises(RuntimeError, match="^second grid serialization$"):
        mesh.to_dict()
    assert len(calls) == 2


def test_vertex_root_refine_coarsen_wires_match_baseline():
    from tests.test_m1b_vertex_dual_state import manager, register, refine

    expected = json.loads((Path(__file__).parent / "fixtures/vertex_serialization_baseline.json").read_text())
    assert expected["baseline_sha"] == "d05b25eec565b48b4a024799cbda4f046e872d6c"
    owner = manager()
    root = register(owner, (1, 4, 3))
    change = refine(owner)
    fine, _ = owner.transfer_state(root, change)
    back, _ = owner.transfer_state(fine, owner.coarsen(change.primal.change.bisections, max_ratio=10))
    assert [s.to_dict() for s in (root, fine, back)] == expected["records"]
    assert owner.read_state(back) == pytest.approx((1, 4, 3))
    with pytest.raises(NumericalRefusal, match="stale"):
        owner.read_state(root)


@pytest.mark.parametrize("target,attribute,value", [
    ("state", "parents", ("forged",)),
    ("support", "intervals", Grid1D((0., .5, 2.5, 4.1), "m")),
    ("mesh", "root_context", "changed"),
    ("cell", "parent_id", "changed"),
])
def test_vertex_serialization_keeps_fresh_mutation_and_issuance_checks(target, attribute, value):
    from tests.test_m1b_vertex_dual_state import manager, register

    owner = manager()
    state = register(owner, (1, 4, 3))
    before = state.to_dict()
    selected = {"state": state, "support": state.support, "mesh": state.support.mesh,
                "cell": state.support.mesh.cells[0]}[target]
    object.__setattr__(selected, attribute, value)
    assert state.to_dict() != before
    with pytest.raises(NumericalRefusal):
        owner.read_state(state)


def test_vertex_equal_unissued_replacement_is_still_rejected_after_serialization():
    from tests.test_m1b_vertex_dual_state import manager, register

    owner = manager()
    state = register(owner, (1, 4, 3))
    other = replace(state)
    assert state.to_dict() == other.to_dict()
    with pytest.raises(NumericalRefusal, match="unissued, substituted or tampered mesh record"):
        owner.read_state(other)


@pytest.mark.parametrize("raises", [False, True])
def test_support_subclass_identity_and_exception_are_preserved(raises):
    from engcore.numerical.vertex_state import DualSupport1D
    from tests.test_m1b_vertex_dual_state import manager, register

    class CustomSupport(DualSupport1D):
        @property
        def record_id(self):
            if raises:
                raise RuntimeError("custom support failure")
            return "custom-support"

    state = register(manager(), (1, 4, 3))
    custom = replace(state, support=CustomSupport(state.support.mesh, state.support.intervals))
    if raises:
        with pytest.raises(RuntimeError, match="^custom support failure$"):
            custom.to_dict()
    else:
        assert custom.to_dict()["support"] == "custom-support"


def test_custom_interval_serialization_keeps_the_following_mesh_identity_read():
    from engcore.numerical.vertex_state import DualSupport1D
    from tests.test_m1b_vertex_dual_state import manager, register

    owner = manager()
    state = register(owner, (1, 4, 3))
    mesh = state.support.mesh

    class CustomIntervals(Grid1D):
        def to_dict(self):
            object.__setattr__(mesh, "root_context", "changed during custom serialization")
            object.__setattr__(custom, "name", "changed name")
            return super().to_dict()

    custom = replace(state, support=DualSupport1D(mesh, CustomIntervals(state.support.intervals.nodes, "m")))
    wire = custom.to_dict()
    assert wire["name"] == "q"  # name was read before custom support serialization
    assert wire["mesh_version"] == mesh.version_id
    with pytest.raises(NumericalRefusal):
        owner.read_state(state)


def test_one_shot_cells_are_not_consumed_by_optimization_eligibility():
    owner = lineage()
    mesh = owner.current
    object.__setattr__(mesh, "cells", iter(mesh.cells))
    wire = mesh.to_dict()
    assert len(wire["cells"]) == 2  # the first legacy material read consumes them
    assert wire["version_id"] == mesh.version_id  # the second sees the exhausted iterator
    with pytest.raises(NumericalRefusal):
        owner._issued.require(mesh)


def test_nodes_becoming_plain_during_serialization_keep_the_legacy_second_read():
    mesh = lineage().current

    class InstallingNodes:
        def __iter__(self):
            object.__setattr__(mesh.grid, "nodes", (0., 2., 4.))
            return iter((0., 1., 4.))

    object.__setattr__(mesh.grid, "nodes", InstallingNodes())
    wire = mesh.to_dict()
    assert wire["grid"]["nodes"] == [0., 1., 4.]
    assert wire["version_id"] == mesh.version_id


def test_stateful_cell_float_keeps_later_conversion_exception():
    mesh = lineage().current
    calls = []

    class ThirdConversionFails:
        def __float__(self):
            calls.append(None)
            if len(calls) == 3:
                raise RuntimeError("third endpoint conversion")
            return 0.

    object.__setattr__(mesh.cells[0], "left", ThirdConversionFails())
    with pytest.raises(RuntimeError, match="^third endpoint conversion$"):
        mesh.to_dict()
    assert len(calls) == 3


def test_cell_becoming_plain_during_serialization_keeps_legacy_identity_read():
    mesh = lineage().current
    cell = mesh.cells[0]

    class InstallingEndpoint:
        def __float__(self):
            object.__setattr__(cell, "left", .25)
            return .5

    object.__setattr__(cell, "left", InstallingEndpoint())
    wire = mesh.to_dict()
    assert wire["cells"][0]["cell_id"] != cell.cell_id
    assert wire["version_id"] == mesh.version_id


def test_malformed_records_keep_the_original_first_exception():
    mesh = lineage().current
    object.__delattr__(mesh, "cells")
    object.__setattr__(mesh.grid, "nodes", None)
    with pytest.raises(TypeError, match="'NoneType' object is not iterable"):
        mesh.to_dict()


def test_vertex_subclass_retains_name_support_mesh_access_order():
    from engcore.numerical.vertex_state import VertexState1D
    from tests.test_m1b_vertex_dual_state import manager, register

    events = []

    class CustomState(VertexState1D):
        def __getattribute__(self, key):
            if key in ("name", "support"):
                events.append(key)
            return super().__getattribute__(key)

    original = register(manager(), (1, 4, 3))
    custom = CustomState(**{f.name: getattr(original, f.name) for f in fields(original)})
    custom.to_dict()
    assert events == ["name", "support", "support"]
