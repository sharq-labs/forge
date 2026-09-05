"""Runtime data plane — where bulk scientific data actually lives.

This package is the **only** place in Crafty that knows about storage
locations. The Scientific Core knows what data a result *means*
(:class:`~engcore.scientific.results.data_reference.ScientificDataReference`);
this package knows where the bytes are and how to get them back.

Dependency direction, and why it is one-way
-------------------------------------------

```
engcore.scientific        scientific meaning        imports nothing from here
        ^
engcore.data              storage / resolution      imports the reference type
        ^
engcore.domains.*         may depend on both
```

``engcore.scientific`` must never import ``engcore.data``. That is not a
stylistic preference: it is the mechanism by which scientific identity is kept
independent of storage. If the control plane could name a store, a store could
end up named in a record, and a scientific record would start meaning
different things in different deployments.

Symmetrically, ``engcore.data`` must never import a named domain pack. It has
no idea what a temperature, a slab or a mesh is; it moves labelled bytes.

Both directions are enforced by tests, not by convention.

Scope
-----
Two backends exist here — in-memory and filesystem — and their purpose is
**not** to be good storage. They exist so that the same scientific data can be
put in two structurally different places and the scientific record can be shown
not to change. Object storage, retention, distribution, device memory and
external providers are out of scope and unimplemented.
"""

from .capture import BulkCaptureSpec, capture_bulk
from .errors import (
    BulkDataError,
    BulkDataIntegrityError,
    BulkDataUnavailable,
)
from .resolver import BulkDataResolver, relocate
from .store import (
    BulkDataStore,
    FilesystemBulkStore,
    InMemoryBulkStore,
    store_values,
)

__all__ = [
    "BulkCaptureSpec",
    "BulkDataError",
    "BulkDataIntegrityError",
    "BulkDataResolver",
    "BulkDataStore",
    "BulkDataUnavailable",
    "FilesystemBulkStore",
    "InMemoryBulkStore",
    "capture_bulk",
    "relocate",
    "store_values",
]
