from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidScientificProblem
from .manifest import ScientificRunManifest


@dataclass(frozen=True)
class LineageVerification:
    verified:bool
    problems:tuple[str,...]


def verify_manifest_lineage(manifests:tuple[ScientificRunManifest,...])->LineageVerification:
    manifests=tuple(manifests);problems=[]
    by_run={}
    by_digest={}
    for manifest in manifests:
        if manifest.run_id in by_run:
            problems.append(f"duplicate run id {manifest.run_id!r}")
        if manifest.digest in by_digest:
            problems.append(f"duplicate manifest digest {manifest.digest!r}")
        by_run[manifest.run_id]=manifest;by_digest[manifest.digest]=manifest
    for manifest in manifests:
        if manifest.parent_run_id is None: continue
        parent=by_run.get(manifest.parent_run_id)
        if parent is None:
            problems.append(f"run {manifest.run_id!r} names missing parent run {manifest.parent_run_id!r}")
            continue
        if parent.digest!=manifest.parent_manifest_digest:
            problems.append(f"run {manifest.run_id!r} parent digest does not match named parent")
    for manifest in manifests:
        seen=set();current=manifest
        while current.parent_run_id is not None:
            if current.run_id in seen:
                problems.append(f"lineage cycle reaches run {current.run_id!r}");break
            seen.add(current.run_id)
            parent=by_run.get(current.parent_run_id)
            if parent is None: break
            current=parent
    return LineageVerification(not problems,tuple(dict.fromkeys(problems)))
