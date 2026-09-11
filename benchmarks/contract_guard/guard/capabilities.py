"""Dimension G: a model may not require a capability nothing can serve.

Every shipped record names the solver capability its results depend on. That
name is a promise to a caller choosing a model: *something in this repository
can execute this*. If a solver is renamed, retired or has its
``serves_capabilities`` edited, the record keeps making the promise and the
model becomes unrunnable with no test failing.

The check walks the shipped domains, collects every capability any solver
declares it serves, and requires each model's declared requirement to appear
there.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import pkgutil


@functools.lru_cache(maxsize=1)
def served_capabilities() -> dict[str, tuple[str, ...]]:
    """Capability name -> the solver classes that declare they serve it."""
    import engcore.domains as domains

    served: dict[str, set[str]] = {}
    for module in pkgutil.walk_packages(domains.__path__, domains.__name__ + "."):
        try:
            loaded = importlib.import_module(module.name)
        except Exception:
            # A domain module that will not import cannot serve anything; the
            # model-side check below is what reports the consequence.
            continue
        for obj in vars(loaded).values():
            if not inspect.isclass(obj):
                continue
            declared = getattr(obj, "serves_capabilities", None)
            if not declared:
                continue
            for capability in declared:
                served.setdefault(str(capability), set()).add(
                    f"{obj.__module__}.{obj.__name__}"
                )
    return {name: tuple(sorted(owners)) for name, owners in sorted(served.items())}


@functools.lru_cache(maxsize=1)
def survey() -> dict:
    from . import records

    served = served_capabilities()
    rows = []
    for model in records.shipped_models():
        required = tuple(str(name) for name in model.required_capabilities)
        missing = [name for name in required if name not in served]
        rows.append(
            {
                "model_id": model.model_id,
                "requires": list(required),
                "served_by": {name: list(served.get(name, ())) for name in required},
                "result": "MATCH" if not missing else "CAPABILITY_NOT_SERVED",
            }
        )
    return {
        "models": len(rows),
        "declared_capabilities": sorted(served),
        "unserved": [row for row in rows if row["result"] != "MATCH"],
        "rows": rows,
    }
