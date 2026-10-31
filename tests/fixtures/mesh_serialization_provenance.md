# Synthetic mesh and vertex serialization fixtures

These two golden files are **SYNTHETIC test fixtures**, generated from constructed
mesh/state inputs by the unmodified baseline implementation at
`d05b25eec565b48b4a024799cbda4f046e872d6c`. They contain no physical measurements,
validation, calibration, certification or new scientific authority. Their use is
exact serialization/hash regression verification only.

| File | SHA-256 |
|---|---|
| mesh_serialization_baseline.json | d4d44833791020e0a9ba1541af15bd8bd18d5d2b6302bce9ffe5b8fd503fac8e |
| vertex_serialization_baseline.json | 22cb385a2bb96d51ec842cd55535e02010d0a8066e05b344daca7c574e3de664 |

The generation ran on 2026-10-31 in the clean baseline checkout
`/home/dev_kaeem/forge-mesh-record-base-20261031`, using Python 3.12.3 from the
existing FORGE environment. Task-local scripts `mesh_golden.py` and
`mesh_state_golden.py` wrote the files once before candidate changes were tested.
Their generation bodies are reproduced below. Serialize each `wire` as
`(json.dumps(wire, indent=2, sort_keys=True) + "\n").encode()`; no timestamps or
machine-dependent fields are added. The immutable baseline source files and this
description are independently SHA-bound in `CURRENT_PROVENANCE.json`.

Mesh fixture (baseline imports only):

```python
from engcore.numerical.mesh_adaptation import Grid1D, MeshLineage1D
from engcore.scientific.units.quantity import Quantity

lineage = MeshLineage1D(Grid1D((0., 1., 4.), 'm'),
                      root_context='serialization-fixture',
                      coordinate_frame='fixture:axis')
root = lineage.current
change = lineage.refine(tuple(c.cell_id for c in root.cells),
                        minimum_cell=Quantity(.01, 'm'), max_ratio=10)
fine = lineage.current
lineage.coarsen(change.bisections, max_ratio=10)
wire = {'baseline_sha': 'd05b25eec565b48b4a024799cbda4f046e872d6c',
        'records': [m.to_dict() for m in (root, fine, lineage.current)]}
```

Vertex fixture (baseline implementation and its existing test helpers only):

```python
from tests.test_m1b_vertex_dual_state import manager, register, refine

m = manager()
root = register(m, (1, 4, 3))
change = refine(m)
fine, _ = m.transfer_state(root, change)
back, _ = m.transfer_state(
    fine, m.coarsen(change.primal.change.bisections, max_ratio=10))
wire = {'baseline_sha': 'd05b25eec565b48b4a024799cbda4f046e872d6c',
        'records': [s.to_dict() for s in (root, fine, back)]}
```

The baseline source imports must be selected explicitly when reproducing these
bytes. Regenerating with the candidate would remove the independent regression
reference. Editing a fixture or its declared source invalidates the existing
provenance binding and requires a new review.
