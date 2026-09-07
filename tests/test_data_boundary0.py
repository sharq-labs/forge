"""DATA-BOUNDARY0 — scientific data identity vs. storage location.

The single question under test:

    Can Crafty move a real scientific bulk field without placing O(mesh-size)
    data inside the scientific control plane, and without making scientific
    identity depend on storage location?

These tests assert *behaviour*, not dataclass syntax. The field they move is
the real solved field of the frozen ``Conduction1DSolver``, at four spatial
resolutions, and the record they inspect is a real ``ScientificResult``.

Naming, deliberately: ``u`` is a normalized **dimensionless** field, not a
temperature. The thermal domain says so in three places and enforces it.

See ``docs/milestones/data-boundary0-prereg.md`` for the preregistered hypothesis, proofs
and fail conditions, and ``docs/milestones/data-boundary0-evidence.md`` for what execution
actually showed. The section headers below name the preregistered test.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib

import pytest

from src.engcore.data import (
    BulkDataIntegrityError,
    BulkDataResolver,
    BulkDataUnavailable,
    FilesystemBulkStore,
    InMemoryBulkStore,
    relocate,
    store_values,
)
from src.engcore.domains.thermal.conduction1d import (
    ConductionSlab,
    SlabDiscretization,
    solve_slab,
)
from src.engcore.domains.thermal_models.conduction1d_bulk import (
    FIELD_DATA_NAME,
    FIELD_DIAGNOSTIC_KEY,
    solve_slab_with_bulk_field,
)
from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.serialization import require_schema
from src.engcore.scientific.results.data_reference import (
    ScientificDataReference,
    decode_float64,
    encode_float64,
)
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.result import (
    RESULT_SCHEMA,
    RESULT_SCHEMA_V1,
    RESULT_SCHEMA_V2,
    RESULT_SCHEMA_V3,
    SUPPORTED_RESULT_SCHEMAS,
    ScientificResult,
)
from src.engcore.scientific.results.uncertainty import Uncertainty
from src.engcore.scientific.solvers.protocol import (
    RAW_OUTPUT_SCHEMA,
    RAW_OUTPUT_SCHEMA_V1,
    SUPPORTED_RAW_OUTPUT_SCHEMAS,
    ConvergenceState,
    RawSolverOutput,
    SolverIdentity,
)
from src.engcore.scientific.units.quantity import Quantity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LENGTH = Quantity(0.1, "meter")
ALPHA = Quantity(1.2e-5, "m**2/s")
END_TIME = Quantity(60.0, "second")

#: Four resolutions spanning 64x in field size. Enough to separate "the record
#: is independent of resolution" from "the record grows slowly".
RESOLUTIONS = (32, 128, 512, 2048)


def make_slab(n_cells: int = 64, n_steps: int = 80, slab_id: str = "db0") -> ConductionSlab:
    return ConductionSlab(
        slab_id=slab_id,
        length=LENGTH,
        diffusivity=ALPHA,
        end_time=END_TIME,
        discretization=SlabDiscretization(n_cells, n_steps),
    )


def scalar_result(**overrides) -> ScientificResult:
    """A pre-DATA-BOUNDARY0 result: scalars only, no bulk anything."""
    payload = dict(
        result_id="legacy-1",
        problem_id="p1",
        values={"v:out": Quantity(1.6612, "volt")},
        solver=SolverIdentity("legacy.solver", "0.1.0", backend="none"),
        convergence=ConvergenceState.CONVERGED,
        uncertainty={"v:out": Uncertainty.unknown("none performed")},
        assumptions=("steady state",),
        provenance=ProvenanceRecord(
            run_id="legacy-1",
            software_version="legacy/0.1.0",
            inputs={"r": Quantity(2.0, "ohm")},
        ),
    )
    payload.update(overrides)
    return ScientificResult(**payload)


def canonical(result: ScientificResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True)


def imported_modules(root: pathlib.Path) -> list[str]:
    """Every module imported under ``root``, as absolute dotted names.

    Relative imports are resolved against the importing file's own package.
    A substring check would miss ``from ...data.store import X`` written from a
    deeper module, and the dependency direction this milestone rests on cannot
    be enforced by a guard with a hole in it.
    """
    src = root.parents[len(root.relative_to(REPO_ROOT / "src").parts) - 1]
    modules: list[str] = []
    for path in root.rglob("*.py"):
        package = path.relative_to(src).with_suffix("").parts
        if package and package[-1] == "__init__":
            package = package[:-1]
        else:
            package = package[:-1]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if not node.level:
                    modules.append(module)
                    continue
                base = package[: len(package) - node.level + 1]
                modules.append(
                    ".".join(list(base) + ([module] if module else []))
                )
    return modules


# =====================================================================
# TEST A — existing scalar compatibility
#
# Fail condition F3: existing scalar consumers must not need rewriting.
# =====================================================================

def test_a1_scalar_only_result_serializes_and_behaves_unchanged():
    result = scalar_result()
    assert result.data_references == ()
    assert result.value("v:out").magnitude_in("volt") == pytest.approx(1.6612)
    assert result.is_usable is True

    restored = ScientificResult.from_dict(json.loads(canonical(result)))
    assert canonical(restored) == canonical(result)
    assert restored.value("v:out").magnitude_in("volt") == pytest.approx(1.6612)
    assert restored.data_references == ()


def test_a2_the_writer_emits_the_bumped_schema_and_the_reader_accepts_both():
    """``data_references`` is scientific content, so the version moves.

    A reader that accepted a payload carrying references and then ignored them
    would return a result understating what was computed. That is worse than
    refusing to read it, so the writer emits ``/2`` and an older reader — whose
    ``require_schema`` is an exact match against ``/1`` — fails loudly.

    The cost is paid on the reader side, once: this reader accepts both.
    """
    # ``/3`` since the recommendations round, which added
    # ``ScientificResult.validity`` on this milestone's own argument: whether
    # the model applied is scientific content, so a reader that dropped it
    # would understate the result. The accept-set grew rather than moved, which
    # is the property this milestone established and this test still measures:
    # every payload that loaded before still loads.
    # ``/4`` since the core round, which added
    # ``ScientificResult.validity_not_assessed`` on this same argument: why a
    # model went unassessed is scientific content too, and a reader that
    # dropped it would be back to reading an empty mapping as either "nobody
    # asked" or "nobody said". The accept-set grew again rather than moving.
    assert RESULT_SCHEMA == "scientific_result/4"
    assert RESULT_SCHEMA_V3 == "scientific_result/3"
    assert RESULT_SCHEMA_V2 == "scientific_result/2"
    assert RESULT_SCHEMA_V1 == "scientific_result/1"
    assert SUPPORTED_RESULT_SCHEMAS == (
        "scientific_result/1",
        "scientific_result/2",
        "scientific_result/3",
        "scientific_result/4",
    )
    assert scalar_result().to_dict()["schema"] == "scientific_result/4"

    assert RAW_OUTPUT_SCHEMA == "raw_solver_output/2"
    assert RAW_OUTPUT_SCHEMA_V1 == "raw_solver_output/1"
    assert SUPPORTED_RAW_OUTPUT_SCHEMAS == (
        "raw_solver_output/1",
        "raw_solver_output/2",
    )
    raw = RawSolverOutput(convergence=ConvergenceState.CONVERGED)
    assert raw.to_dict()["schema"] == "raw_solver_output/2"


def test_a2b_an_old_reader_refuses_a_new_payload_rather_than_losing_data():
    """NEW payload → OLD reader must fail loudly, not succeed and drop data.

    The old reader is `require_schema`, still exactly as it was: one exact
    string comparison. Simulated here against the string it pinned, because
    the pre-milestone reader is not importable from this tree.
    """
    result, _ = solve_slab_with_bulk_field(make_slab(64, 80), run_id="v2-only")
    payload = result.to_dict()
    assert payload["schema"] == "scientific_result/4"
    assert payload["data_references"], "the payload must actually carry one"

    with pytest.raises(ScientificCoreError) as excinfo:
        require_schema(payload, RESULT_SCHEMA_V1)
    assert "scientific_result/4" in str(excinfo.value)
    # The /2 reader refuses it too, and for this milestone's own reason: a /3
    # payload can carry a validity assessment, and a reader that accepted it
    # and dropped that would report a result while losing the answer to
    # whether the model applied.
    with pytest.raises(ScientificCoreError):
        require_schema(payload, RESULT_SCHEMA_V2)
    # And the /3 reader refuses it, for the reason this round added: a /4
    # payload can state why a model was not assessed, and a reader that
    # accepted it and dropped that would be unable to tell a stated
    # non-assessment from a silent one -- the exact confusion the field ended.
    with pytest.raises(ScientificCoreError):
        require_schema(payload, RESULT_SCHEMA_V3)

    raw_payload = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED,
        data_references=result.data_references,
    ).to_dict()
    with pytest.raises(ScientificCoreError):
        require_schema(raw_payload, RAW_OUTPUT_SCHEMA_V1)

    # And an unknown future version is refused by the new reader too: the
    # accept-set is exact strings, not a range.
    with pytest.raises(ScientificCoreError):
        ScientificResult.from_dict({**payload, "schema": "scientific_result/5"})


def test_a2c_a_v2_payload_round_trips_its_references():
    result, store = solve_slab_with_bulk_field(make_slab(64, 80), run_id="v2-rt")
    restored = ScientificResult.from_dict(json.loads(canonical(result)))

    assert restored.data_references == result.data_references
    assert canonical(restored) == canonical(result)
    assert BulkDataResolver(store).resolve(restored.data_references[0])


def test_a3_a_payload_written_before_this_milestone_still_loads():
    """OLD payload → NEW reader must succeed. The exact bytes an older Crafty
    would have produced: ``scientific_result/1``, and no such key."""
    payload = json.loads(canonical(scalar_result()))
    payload["schema"] = "scientific_result/1"
    del payload["data_references"]
    assert "data_references" not in payload

    restored = ScientificResult.from_dict(payload)
    assert restored.data_references == ()
    assert restored.value("v:out").magnitude_in("volt") == pytest.approx(1.6612)
    # Re-serializing upgrades it: the writer emits one version only.
    assert restored.to_dict()["schema"] == "scientific_result/4"


def test_a3b_a_v1_payload_carries_no_references_even_if_a_key_appears():
    """``/1`` predates bulk data, so it loads with none — by version, not by
    key presence. A key in a ``/1`` payload was not written by this contract
    and is not read as if it were."""
    reference = ScientificDataReference.for_values(
        "u:field", [1.0, 2.0], unit="dimensionless"
    )[0]
    payload = json.loads(canonical(scalar_result()))
    payload["schema"] = "scientific_result/1"
    payload["data_references"] = [reference.to_dict()]

    assert ScientificResult.from_dict(payload).data_references == ()


def test_a4_raw_solver_output_is_versioned_the_same_way():
    raw = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED,
        values={"x": 1.0},
        diagnostics={"n": 3},
    )
    assert raw.data_references == ()

    payload = raw.to_dict()
    assert payload["schema"] == "raw_solver_output/2"

    # An old record: version /1, no key.
    payload["schema"] = "raw_solver_output/1"
    del payload["data_references"]
    restored = RawSolverOutput.from_dict(payload)
    assert restored.data_references == ()
    assert restored.values == {"x": 1.0}
    assert restored.to_dict()["schema"] == "raw_solver_output/2"

    # A /2 record round-trips its references.
    reference = ScientificDataReference.for_values(
        "u:field", [1.0, 2.0], unit="dimensionless"
    )[0]
    carried = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED, data_references=(reference,)
    )
    assert RawSolverOutput.from_dict(carried.to_dict()).data_references == (
        reference,
    )


def test_a5_the_frozen_conduction_wrapper_is_untouched():
    """``solve_slab`` still behaves exactly as before, field-free."""
    result = solve_slab(make_slab(128, 160), run_id="legacy-path")
    assert result.data_references == ()
    assert FIELD_DIAGNOSTIC_KEY not in result.metadata["numerics"]
    assert result.convergence is ConvergenceState.CONVERGED


def test_a6_the_frozen_thermal_tree_was_not_edited():
    """DATA-BOUNDARY0 spent none of T1/T2/T3's evidence.

    The bulk path was introduced around a solver pinned byte-for-byte by three
    frozen experiments. This restates their pin here so that a future edit to
    the thermal tree fails in *this* milestone's suite too, where the reason it
    must not happen is written down.
    """
    from experiments.thermal_t1 import t1_config

    for relative, expected in t1_config.THERMAL_FROZEN_FILE_DIGESTS.items():
        path = REPO_ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"DATA-BOUNDARY0 must not edit {relative}"

    on_disk = {
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "src/engcore/domains/thermal").rglob("*.py")
    }
    assert on_disk == set(t1_config.THERMAL_FROZEN_FILE_DIGESTS), (
        "the DATA-BOUNDARY0 path must live outside the frozen thermal tree"
    )


# =====================================================================
# TEST B — real field separation
#
# Fail conditions F1 (no inline field) and F5 (no untyped escape hatch).
# =====================================================================

@pytest.mark.parametrize("n_cells", RESOLUTIONS)
def test_b1_the_real_field_leaves_the_solver_as_referenced_bulk_data(n_cells):
    result, store = solve_slab_with_bulk_field(
        make_slab(n_cells, 80), run_id=f"bulk-{n_cells}"
    )

    assert len(result.data_references) == 1
    reference = result.data_references[0]
    assert reference.name == FIELD_DATA_NAME
    assert reference.unit == "dimensionless"
    # Node count, not cell count: both Dirichlet ends are nodes of the field.
    assert reference.count == n_cells + 1
    assert reference.byte_length == (n_cells + 1) * 8

    values = BulkDataResolver(store).resolve(reference)
    assert len(values) == n_cells + 1
    # It is the real solved field: ends held at zero, interior positive.
    assert values[0] == 0.0 and values[-1] == 0.0
    assert max(values) > 0.4
    # And it agrees with the scalar metrics the same solve produced.
    assert max(abs(v) for v in values) == pytest.approx(
        result.value("u:max_abs").magnitude_in("dimensionless")
    )


@pytest.mark.parametrize("n_cells", RESOLUTIONS)
def test_b2_the_field_is_nowhere_inside_the_scientific_record(n_cells):
    result, _ = solve_slab_with_bulk_field(
        make_slab(n_cells, 80), run_id=f"absent-{n_cells}"
    )

    assert FIELD_DATA_NAME not in result.values
    assert FIELD_DIAGNOSTIC_KEY not in result.metadata["numerics"]
    assert FIELD_DIAGNOSTIC_KEY not in result.metadata
    assert result.artifacts == ()

    # Nothing anywhere in the serialized record is an array of mesh length.
    payload = result.to_dict()

    def longest_sequence(node) -> int:
        if isinstance(node, (list, tuple)):
            return max([len(node)] + [longest_sequence(v) for v in node])
        if isinstance(node, dict):
            return max([0] + [longest_sequence(v) for v in node.values()])
        return 0

    assert longest_sequence(payload) < 32, (
        "a mesh-length sequence reached the scientific record"
    )


def test_b3_serialized_size_is_independent_of_field_resolution():
    """The record must not grow with the mesh. The data must."""
    sizes: dict[int, int] = {}
    field_bytes: dict[int, int] = {}
    for n_cells in RESOLUTIONS:
        result, _ = solve_slab_with_bulk_field(
            make_slab(n_cells, 80), run_id="size"
        )
        sizes[n_cells] = len(canonical(result))
        field_bytes[n_cells] = result.data_references[0].byte_length

    smallest, largest = min(RESOLUTIONS), max(RESOLUTIONS)
    data_growth = field_bytes[largest] / field_bytes[smallest]
    record_growth = sizes[largest] / sizes[smallest]

    assert data_growth > 50, f"the field did not actually grow: {field_bytes}"
    # The only variation permitted is decimal digits of n_cells/n_steps inside
    # the numeric diagnostics, which is a handful of bytes.
    assert record_growth < 1.02, (
        f"serialized result grew with resolution: {sizes}"
    )
    assert sizes[largest] - sizes[smallest] < 64, sizes


def test_b4_the_field_is_removed_from_the_diagnostics_escape_hatch():
    """Not merely absent from the result — gone from the raw output too."""
    from src.engcore.data.capture import BulkCaptureSpec, capture_bulk
    from src.engcore.domains.thermal.conduction1d.solver import Conduction1DSolver
    from src.engcore.domains.thermal.conduction1d.problem import (
        build_conduction_problem,
    )

    slab = make_slab(256, 80)
    solver = Conduction1DSolver()
    problem = build_conduction_problem(slab)
    solver.bind_slab(slab, problem.problem_id)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)

    # Before the boundary the frozen solver's untyped escape hatch holds it.
    assert len(raw.diagnostics[FIELD_DIAGNOSTIC_KEY]) == 257

    store = InMemoryBulkStore()
    captured, references = capture_bulk(
        raw,
        store,
        (BulkCaptureSpec(FIELD_DIAGNOSTIC_KEY, FIELD_DATA_NAME, "dimensionless"),),
    )

    # After it, the key does not exist and the raw record is small.
    assert FIELD_DIAGNOSTIC_KEY not in captured.diagnostics
    assert captured.data_references == references
    assert len(json.dumps(captured.to_dict(), sort_keys=True)) < 1200
    # The input was frozen and is unchanged; capture returned a new record.
    assert FIELD_DIAGNOSTIC_KEY in raw.diagnostics


def test_b5_scalar_metrics_are_identical_to_the_frozen_path():
    """Referencing the field changed no science."""
    slab = make_slab(128, 160, slab_id="parity")
    frozen = solve_slab(slab, run_id="parity")
    bulk, _ = solve_slab_with_bulk_field(slab, run_id="parity")

    assert set(frozen.values) == set(bulk.values)
    for name, quantity in frozen.values.items():
        assert quantity.magnitude_in("dimensionless") == pytest.approx(
            bulk.value(name).magnitude_in("dimensionless"), rel=0.0, abs=0.0
        )
    assert frozen.validation.to_dict() == bulk.validation.to_dict()
    assert frozen.convergence is bulk.convergence


# =====================================================================
# TEST C — relocation
#
# Fail condition F6: relocation must not change the scientific record.
# =====================================================================

def test_c1_relocating_the_artifact_leaves_the_record_byte_identical(tmp_path):
    memory = InMemoryBulkStore("A-memory")
    result, _ = solve_slab_with_bulk_field(
        make_slab(512, 80), run_id="relocate", store=memory
    )
    reference = result.data_references[0]
    before = canonical(result)
    expected = BulkDataResolver(memory).resolve(reference)

    disk = FilesystemBulkStore(tmp_path / "home_b", name="B-filesystem")
    returned = relocate(reference, memory, disk, remove_source=True)

    # The record was not rewritten, re-registered or migrated. It was not
    # touched at all — there is nothing in it that a move could invalidate.
    assert canonical(result) == before
    assert returned == reference
    assert returned is reference
    assert result.data_references[0] == reference

    assert not memory.has(reference)
    assert disk.has(reference)
    assert BulkDataResolver(disk).resolve(reference) == expected


def test_c2_a_second_relocation_to_another_root_also_changes_nothing(tmp_path):
    first = FilesystemBulkStore(tmp_path / "one", name="B1")
    result, _ = solve_slab_with_bulk_field(
        make_slab(256, 80), run_id="rehome", store=first
    )
    reference = result.data_references[0]
    before = canonical(result)

    second = FilesystemBulkStore(tmp_path / "two", name="B2")
    relocate(reference, first, second, remove_source=True)

    assert canonical(result) == before
    assert BulkDataResolver(second).resolve(reference)[0] == 0.0
    assert first.root != second.root


def test_c3_a_resolver_finds_the_artifact_wherever_it_now_lives(tmp_path):
    memory = InMemoryBulkStore("A")
    disk = FilesystemBulkStore(tmp_path / "shared", name="B")
    result, _ = solve_slab_with_bulk_field(
        make_slab(128, 80), run_id="chain", store=memory
    )
    reference = result.data_references[0]

    # One resolver, both stores, no idea which holds it. Same answer either way.
    resolver = BulkDataResolver(memory, disk)
    from_memory = resolver.resolve(reference)
    assert resolver.locate(reference) is memory

    relocate(reference, memory, disk, remove_source=True)
    assert resolver.locate(reference) is disk
    assert resolver.resolve(reference) == from_memory


def test_c4_one_artifact_can_be_referenced_by_several_results(tmp_path):
    """Two results of the same slab name the same bytes and share one blob."""
    store = FilesystemBulkStore(tmp_path / "shared", name="B")
    slab = make_slab(128, 80, slab_id="shared")
    first, _ = solve_slab_with_bulk_field(slab, run_id="run-1", store=store)
    second, _ = solve_slab_with_bulk_field(slab, run_id="run-2", store=store)

    assert first.result_id != second.result_id
    assert first.data_references == second.data_references
    stored = list((tmp_path / "shared").glob("*.bulk"))
    assert len(stored) == 1, "identical content should not be stored twice"


# =====================================================================
# TEST D — integrity
# =====================================================================

def test_d1_corrupting_one_value_is_detected(tmp_path):
    store = FilesystemBulkStore(tmp_path / "corrupt", name="B")
    result, _ = solve_slab_with_bulk_field(
        make_slab(128, 80), run_id="corrupt", store=store
    )
    reference = result.data_references[0]
    resolver = BulkDataResolver(store)
    assert len(resolver.resolve(reference)) == 129

    values = list(resolver.resolve(reference))
    values[64] += 1e-12  # a perturbation far below any physical tolerance
    path = next((tmp_path / "corrupt").glob("*.bulk"))
    path.write_bytes(encode_float64(values))

    with pytest.raises(BulkDataIntegrityError) as excinfo:
        resolver.resolve(reference)
    assert "modified or substituted" in str(excinfo.value)


def test_d2_truncation_is_detected_and_named_as_such(tmp_path):
    store = FilesystemBulkStore(tmp_path / "trunc", name="B")
    result, _ = solve_slab_with_bulk_field(
        make_slab(128, 80), run_id="trunc", store=store
    )
    reference = result.data_references[0]
    path = next((tmp_path / "trunc").glob("*.bulk"))
    path.write_bytes(path.read_bytes()[:-8])

    with pytest.raises(BulkDataIntegrityError) as excinfo:
        BulkDataResolver(store).resolve(reference)
    message = str(excinfo.value)
    assert "truncated" in message
    assert str(reference.byte_length) in message


def test_d3_substituting_another_result_s_field_is_detected():
    """A different, entirely valid field is still not the one asked for."""
    memory = InMemoryBulkStore("A")
    coarse, _ = solve_slab_with_bulk_field(
        make_slab(128, 80, "coarse"), run_id="a", store=memory
    )
    other = InMemoryBulkStore("A2")
    fine, _ = solve_slab_with_bulk_field(
        make_slab(128, 160, "fine"), run_id="b", store=other
    )
    assert coarse.data_references[0] != fine.data_references[0]

    memory.corrupt(
        coarse.data_references[0],
        other.read(fine.data_references[0]),
    )
    with pytest.raises(BulkDataIntegrityError):
        BulkDataResolver(memory).resolve(coarse.data_references[0])


def test_d4_relocation_cannot_launder_corrupt_bytes(tmp_path):
    memory = InMemoryBulkStore("A")
    result, _ = solve_slab_with_bulk_field(
        make_slab(64, 80), run_id="launder", store=memory
    )
    reference = result.data_references[0]
    memory.corrupt(reference, b"\x00" * reference.byte_length)

    disk = FilesystemBulkStore(tmp_path / "dest", name="B")
    with pytest.raises(BulkDataIntegrityError):
        relocate(reference, memory, disk)
    assert not disk.has(reference)


# =====================================================================
# TEST E — missing data
# =====================================================================

def test_e1_a_deleted_artifact_raises_a_typed_failure(tmp_path):
    store = FilesystemBulkStore(tmp_path / "gone", name="B-filesystem")
    result, _ = solve_slab_with_bulk_field(
        make_slab(128, 80), run_id="gone", store=store
    )
    reference = result.data_references[0]
    store.delete(reference)

    with pytest.raises(BulkDataUnavailable) as excinfo:
        BulkDataResolver(store).resolve(reference)
    message = str(excinfo.value)
    assert FIELD_DATA_NAME in message
    assert "B-filesystem" in message
    # Unavailable is not integrity: a caller must be able to tell them apart.
    assert not isinstance(excinfo.value, BulkDataIntegrityError)


def test_e2_missing_bulk_data_does_not_invalidate_the_scalar_science(tmp_path):
    store = FilesystemBulkStore(tmp_path / "gone2", name="B")
    result, _ = solve_slab_with_bulk_field(
        make_slab(128, 80), run_id="scalars-survive", store=store
    )
    before = canonical(result)
    store.delete(result.data_references[0])

    with pytest.raises(BulkDataUnavailable):
        BulkDataResolver(store).resolve(result.data_references[0])

    # Nothing about the result changed, and its scalar claims stand.
    assert canonical(result) == before
    assert result.is_usable is True
    assert result.value("u:midpoint").magnitude_in("dimensionless") > 0.4
    assert result.validation.status.value == "pass"
    assert result.data_references[0].count == 129


def test_e3_nothing_fabricates_empty_or_zero_data(tmp_path):
    """The refusal is total: no empty tuple, no zero fill, no nearest match."""
    empty = FilesystemBulkStore(tmp_path / "empty", name="B")
    reference = ScientificDataReference.for_values(
        "u:field", [1.0, 2.0, 3.0], unit="dimensionless"
    )[0]
    resolver = BulkDataResolver(empty)

    assert resolver.locate(reference) is None
    with pytest.raises(BulkDataUnavailable):
        resolver.resolve(reference)
    with pytest.raises(BulkDataUnavailable):
        resolver.read_bytes(reference)


# =====================================================================
# TEST F — no storage identity leakage
#
# Fail conditions F2 and F4.
# =====================================================================

def test_f1_the_same_data_yields_the_same_reference_from_any_store(tmp_path):
    values = [0.0, 0.25, 0.5, 0.25, 0.0]

    memory = store_values(InMemoryBulkStore("A"), "u:field", values, unit="dimensionless")
    disk_one = store_values(
        FilesystemBulkStore(tmp_path / "r1", name="B1"),
        "u:field", values, unit="dimensionless",
    )
    disk_two = store_values(
        FilesystemBulkStore(tmp_path / "r2", name="B2"),
        "u:field", values, unit="dimensionless",
    )

    assert memory == disk_one == disk_two
    assert hash(memory) == hash(disk_one) == hash(disk_two)
    assert len({memory, disk_one, disk_two}) == 1


def test_f2_no_field_or_serialized_key_can_hold_a_location(tmp_path):
    store = FilesystemBulkStore(
        tmp_path / "vaultdir" / "deepdir" / "rootdir", name="backend-bravo"
    )
    result, _ = solve_slab_with_bulk_field(
        make_slab(64, 80), run_id="leak", store=store
    )
    reference = result.data_references[0]

    payload = reference.to_dict()
    assert set(payload) == {
        "schema", "name", "unit", "count", "dtype", "digest", "digest_algorithm",
    }

    # Nothing in the reference, and nothing anywhere in the serialized result,
    # names the place the bytes are sitting.
    reference_blob = json.dumps(payload).lower()
    record = canonical(result).lower()
    for fragment in (
        "vaultdir", "deepdir", "rootdir", "backend-bravo", "filesystem",
        ".bulk", str(tmp_path),
    ):
        assert fragment.lower() not in reference_blob, fragment
        assert fragment.lower() not in record, fragment


def test_f3_reference_identity_survives_relocation_unchanged(tmp_path):
    memory = InMemoryBulkStore("A")
    result, _ = solve_slab_with_bulk_field(
        make_slab(64, 80), run_id="identity", store=memory
    )
    reference = result.data_references[0]
    snapshot = (reference.to_dict(), hash(reference))

    disk = FilesystemBulkStore(tmp_path / "moved", name="B")
    relocate(reference, memory, disk, remove_source=True)

    assert (reference.to_dict(), hash(reference)) == snapshot


def test_f4_the_legacy_artifacts_field_is_not_narrowed_by_this_milestone():
    """``artifacts`` keeps exactly the values it accepted before.

    It is legacy, generic and untyped, and DATA-BOUNDARY0 does not get to
    narrow it. No in-repo producer is not evidence that no external caller
    exists, and rejecting a value that used to load — including on the
    deserialization path — would break a caller this milestone cannot see.
    """
    for label in (
        "convergence_plot",
        "/var/runs/u_field.npy",
        r"C:\runs\u_field.npy",
        "s3://crafty/runs/u_field",
        "~/runs/u_field",
        "runs/u_field",
    ):
        assert scalar_result(artifacts=(label,)).artifacts == (label,)
        # And it still survives the deserialization path unchanged.
        restored = ScientificResult.from_dict(
            json.loads(canonical(scalar_result(artifacts=(label,))))
        )
        assert restored.artifacts == (label,)

    # `RawSolverOutput.artifacts` is likewise untouched.
    raw = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED, artifacts=("runs/case.foam",)
    )
    assert raw.artifacts == ("runs/case.foam",)


def test_f4b_new_scientific_data_code_does_not_use_the_artifacts_channel():
    """The fitness rule that replaces the narrowing.

    Old serialized values keep working; what is constrained is *new* code. No
    module introduced by DATA-BOUNDARY0 may write ``artifacts``, because it is
    untyped, unitless, countless and unverifiable — which is how a storage
    location reaches a scientific record by habit. Bulk data goes through
    ``data_references``, which is checkable.
    """
    new_modules = [
        REPO_ROOT / "src/engcore/scientific/results/data_reference.py",
        REPO_ROOT / "src/engcore/domains/thermal_models/conduction1d_bulk.py",
        *(REPO_ROOT / "src/engcore/data").rglob("*.py"),
    ]
    for path in new_modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            written = None
            if isinstance(node, ast.keyword) and node.arg == "artifacts":
                written = "keyword argument"
            elif isinstance(node, ast.Attribute) and node.attr == "artifacts":
                if isinstance(node.ctx, ast.Store):
                    written = "attribute assignment"
            assert written is None, (
                f"{path.relative_to(REPO_ROOT)} writes `artifacts` as a "
                f"{written}; new scientific-data code uses data_references"
            )


def test_f4c_a_scientific_name_is_not_judged_by_its_punctuation():
    """Scientific identity is storage-independent, so name *shape* is not policed.

    ``phase/alpha``, ``velocity/x`` and ``species:H2O`` are scientific names
    that happen to contain punctuation. Rejecting them because they resemble a
    path would let a storage concern dictate scientific vocabulary — and there
    is no storage field on the reference for such a name to be confused with.
    """
    for name in ("phase/alpha", "velocity/x", "species:H2O", "u:field"):
        reference, _ = ScientificDataReference.for_values(
            name, [1.0, 2.0], unit="dimensionless"
        )
        assert reference.name == name
        assert ScientificDataReference.from_dict(reference.to_dict()) == reference


def test_f5_the_scientific_core_never_imports_the_data_plane():
    """The direction of this dependency is the whole architecture.

    If the control plane could name a store, a store could end up named in a
    record, and a scientific record would mean different things in different
    deployments.
    """
    offenders = imported_modules(REPO_ROOT / "src" / "engcore" / "scientific")
    offenders = [m for m in offenders if m.startswith("engcore.data")]
    assert not offenders, (
        f"the Scientific Core must not import the runtime data plane: "
        f"{sorted(set(offenders))}"
    )


def test_f6_the_data_plane_never_imports_a_named_domain():
    """Storage moves labelled bytes. It knows no physics and no domain."""
    banned = ("domains", "thermal", "electrical", "kinetics", "fluids", "sria")
    offenders = [
        module
        for module in imported_modules(REPO_ROOT / "src" / "engcore" / "data")
        for name in banned
        if name in module
    ]
    assert not offenders, f"the data plane bound itself to a domain: {offenders}"


def test_f7_no_premature_field_mesh_or_coupling_vocabulary_was_introduced():
    """Fail condition F7. The reference names data; it does not model a field.

    Docstrings in these modules say at length what was deliberately *not*
    built, so a plain text search would flag its own disclaimers. This walks
    the parsed source instead and checks the identifiers the code actually
    defines and uses.
    """
    banned = (
        "mesh", "topolog", "coupling", "transfer", "interpolat",
        "fielddefinition", "probe", "tensor_rank", "coordinate_frame",
    )
    for relative in (
        "src/engcore/scientific/results/data_reference.py",
        "src/engcore/data/store.py",
        "src/engcore/data/resolver.py",
        "src/engcore/data/capture.py",
    ):
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                identifiers.add(node.name)
            elif isinstance(node, ast.arg):
                identifiers.add(node.arg)
        for identifier in identifiers:
            lowered = identifier.lower()
            for term in banned:
                assert term not in lowered, (
                    f"{relative} introduced {identifier!r}: DATA-BOUNDARY0 "
                    f"builds no field, mesh, transfer or coupling vocabulary"
                )


# =====================================================================
# TEST G — serialization roundtrip
# =====================================================================

def test_g1_a_reference_survives_to_dict_json_from_dict():
    reference, payload = ScientificDataReference.for_values(
        "u:field", [0.0, 0.5, 1.0, 0.5, 0.0], unit="dimensionless"
    )
    text = json.dumps(reference.to_dict(), sort_keys=True)
    restored = ScientificDataReference.from_dict(json.loads(text))

    assert restored == reference
    assert hash(restored) == hash(reference)
    store = InMemoryBulkStore()
    store.put(restored, payload)
    assert BulkDataResolver(store).resolve(restored) == (0.0, 0.5, 1.0, 0.5, 0.0)
    # Small, and no values in it.
    assert len(text) < 256
    assert "0.5" not in text


def test_g2_a_result_carrying_a_reference_round_trips_without_bulk_data():
    result, store = solve_slab_with_bulk_field(
        make_slab(1024, 80), run_id="roundtrip"
    )
    text = canonical(result)
    restored = ScientificResult.from_dict(json.loads(text))

    assert canonical(restored) == text
    assert restored.data_references == result.data_references
    # The rehydrated record can still find its data — identity is enough.
    assert BulkDataResolver(store).resolve(
        restored.data_references[0]
    ) == BulkDataResolver(store).resolve(result.data_references[0])
    # 1025 float64 values would be ~20 kB of JSON. The record is far smaller.
    assert len(text) < 9000


def test_g3_encoding_is_canonical_and_round_trips_exactly():
    values = (0.0, -1.5, 1e-300, 1e300, 0.1, 1.0 / 3.0)
    payload = encode_float64(values)
    assert len(payload) == len(values) * 8
    assert decode_float64(payload) == values
    # Byte-identical for an equal sequence built a different way.
    assert encode_float64(list(values)) == payload
    assert encode_float64(iter(values)) == payload


def test_g4_a_malformed_reference_is_refused_rather_than_repaired():
    good = dict(name="u:field", unit="dimensionless", count=3, digest="a" * 64)
    ScientificDataReference(**good)

    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "digest": "short"})
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "count": -1})
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "dtype": "float32"})
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "digest_algorithm": "md5"})
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "unit": "not_a_unit_at_all"})
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(**{**good, "name": ""})


def test_g5_a_name_cannot_mean_a_scalar_and_a_bulk_array_at_once():
    reference = ScientificDataReference.for_values(
        "v:out", [1.0], unit="volt"
    )[0]
    with pytest.raises(ScientificCoreError) as excinfo:
        scalar_result(data_references=(reference,))
    assert "one name must mean one thing" in str(excinfo.value)


def test_g6_duplicate_reference_names_are_refused():
    first = ScientificDataReference.for_values("u:field", [1.0], unit="dimensionless")[0]
    second = ScientificDataReference.for_values("u:field", [2.0], unit="dimensionless")[0]
    assert first != second
    with pytest.raises(ScientificCoreError):
        scalar_result(data_references=(first, second))


# =====================================================================
# FALSIFIER CORRECTIONS
#
# Each test below pins one required change from the architecture-falsifier
# pass. They sit apart from the A-G blocks because they answer attacks on the
# boundary rather than the preregistered proofs.
# =====================================================================

def test_x1_a_wrong_shaped_buffer_is_refused_not_silently_upcast():
    """D-2. A float32 producer must not get a digest for data it never made.

    Falling back to a per-element ``float()`` loop would upcast the array, and
    the digest would then attest to a float64 image the solver never computed.
    """
    import numpy as np

    single = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    with pytest.raises(ScientificCoreError) as excinfo:
        encode_float64(single)
    assert "did not compute" in str(excinfo.value)

    # 2-D and non-contiguous are refused for the same reason.
    with pytest.raises(ScientificCoreError):
        encode_float64(np.zeros((2, 2), dtype=np.float64))
    with pytest.raises(ScientificCoreError):
        encode_float64(np.arange(10, dtype=np.float64)[::2])

    # A conforming buffer takes the fast path and agrees with the slow one.
    double = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    assert encode_float64(double) == encode_float64([1.0, 2.0, 3.0])
    # A plain Python sequence exposes no buffer at all and is converted.
    assert len(encode_float64([1, 2, 3])) == 24


def test_x2_an_empty_bulk_claim_is_allowed_and_resolves(tmp_path):
    """Zero-length data is not forbidden universally.

    DATA-BOUNDARY0 has no evidence that an empty scientific dataset is invalid,
    and no storage invariant here requires a non-empty payload: an empty blob
    round-trips through both backends and verifies. The known consequence —
    every empty payload of a dtype shares one digest, so one empty blob
    satisfies every empty reference — is a documented property, not grounds for
    a universal ban. A consumer for which emptiness is a domain error says so
    itself; the frozen Conduction1D path never produces one.
    """
    reference, payload = ScientificDataReference.for_values(
        "u:field", [], unit="dimensionless"
    )
    assert reference.count == 0
    assert reference.byte_length == 0
    assert payload == b""

    for store in (InMemoryBulkStore("mem"), FilesystemBulkStore(tmp_path, "disk")):
        store.put(reference, payload)
        assert BulkDataResolver(store).resolve(reference) == ()

    # Absence is still absence: an unstored empty reference is unavailable, not
    # silently satisfied.
    with pytest.raises(BulkDataUnavailable):
        BulkDataResolver(InMemoryBulkStore("empty")).resolve(reference)

    # The shared-digest consequence, stated as an executed fact.
    other, _ = ScientificDataReference.for_values(
        "p:field", [], unit="dimensionless"
    )
    assert other.digest == reference.digest


def test_x3_relocation_verifies_the_destination_before_dropping_the_source():
    """C-10. The one operation that can leave zero copies must not trust a write."""

    class SilentlyFailingStore:
        """A destination whose writes vanish. A full disk, in miniature."""

        name = "broken-destination"

        def put(self, reference, payload):
            return None

        def has(self, reference):
            return False

        def read(self, reference):
            raise BulkDataUnavailable("nothing was written")

        def delete(self, reference):
            return None

    memory = InMemoryBulkStore("A")
    result, _ = solve_slab_with_bulk_field(
        make_slab(64, 80), run_id="halfmove", store=memory
    )
    reference = result.data_references[0]

    with pytest.raises(BulkDataUnavailable):
        relocate(reference, memory, SilentlyFailingStore(), remove_source=True)

    # The source copy survives: the move failed rather than half-succeeding.
    assert memory.has(reference)
    assert len(BulkDataResolver(memory).resolve(reference)) == 65


def test_x4_capture_failures_are_typed():
    """C-16. A milestone about typed failure does not raise a bare KeyError."""
    from src.engcore.data.capture import BulkCaptureSpec, capture_bulk
    from src.engcore.data.errors import BulkDataError

    raw = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED, diagnostics={"other": 1}
    )
    spec = BulkCaptureSpec("field", "u:field", "dimensionless")

    with pytest.raises(BulkDataError) as excinfo:
        capture_bulk(raw, InMemoryBulkStore(), (spec,))
    assert "no diagnostic 'field'" in str(excinfo.value)

    # A present-but-unencodable diagnostic is also typed, not a stray TypeError.
    bad = RawSolverOutput(
        convergence=ConvergenceState.CONVERGED,
        diagnostics={"field": "not an array"},
    )
    with pytest.raises(BulkDataError):
        capture_bulk(bad, InMemoryBulkStore(), (spec,))

    # A missing key on a failed solve is tolerated, because a solve that never
    # reached a solution genuinely has no field.
    tolerated, references = capture_bulk(
        raw, InMemoryBulkStore(), (spec,), required=False
    )
    assert references == ()
    assert tolerated.diagnostics == {"other": 1}


def test_x5_content_sharing_means_a_move_affects_every_reference(tmp_path):
    """C-2. The dedup benefit and the ownership hazard are one mechanism.

    Not a defect to repair here — retention and ownership are preregistered
    non-goals — but a behaviour that must not be discovered by surprise.
    """
    store = InMemoryBulkStore("A")
    slab = make_slab(64, 80, slab_id="shared-move")
    first, _ = solve_slab_with_bulk_field(slab, run_id="one", store=store)
    second, _ = solve_slab_with_bulk_field(slab, run_id="two", store=store)
    assert first.data_references == second.data_references
    assert len(store) == 1

    elsewhere = FilesystemBulkStore(tmp_path / "elsewhere", name="B")
    relocate(first.data_references[0], store, elsewhere, remove_source=True)

    # run-2 never asked for anything to move, and its data moved.
    with pytest.raises(BulkDataUnavailable):
        BulkDataResolver(store).resolve(second.data_references[0])
    # Its scalar science is untouched, and the data is still findable.
    assert second.is_usable is True
    assert BulkDataResolver(elsewhere).resolve(second.data_references[0])[0] == 0.0


def test_x6_capture_runs_after_every_in_process_consumer():
    """D-3. Both ``validate`` and ``extract_metrics`` still see the array.

    The frozen conduction solver's ``extract_metrics`` reads only
    ``raw.values``, so a capture placed too early would have worked here and
    failed in the next domain that derives a scalar from the field.
    """
    import inspect

    from src.engcore.domains.thermal_models import conduction1d_bulk as bridge

    source = inspect.getsource(bridge.solve_slab_with_bulk_field)
    validate_at = source.index("solver.validate(")
    metrics_at = source.index("solver.extract_metrics(")
    capture_at = source.index("capture_bulk(")
    assert validate_at < capture_at, "validate must see the field"
    assert metrics_at < capture_at, "extract_metrics must see the field too"
