"""forge-precice: preCICE as a numerical coupling/data-exchange provider for Forge.

Forge owns the coupling CONTRACT (:class:`ScalarTwoWayContract`): participants,
exchanged quantities and units, scheme, iteration limit, relaxation, explicit
absolute convergence measures, time window.  This module RENDERS a preCICE v3
configuration from it (the XML is provider configuration, never Forge's
ontology), runs each participant as a separate process over preCICE sockets,
and returns a :class:`PreciceExecutionRecord` whose identity includes the
preCICE version and the digest of the exact generated configuration.

preCICE's own convergence is not trusted alone: the record is accepted only
if (a) the iteration log shows the last window converged within the limit AND
(b) Forge's independent fixed-point residual check on the exchanged values
passes.  Otherwise it is FAILED and exposes no values.  Nothing here is
validation or evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Mapping


def precice_available() -> tuple[bool, str]:
    try:
        import precice
        info = precice.get_version_information()
        text = info.decode() if isinstance(info, bytes) else str(info)
        return True, text.split(";")[0]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class ExchangedQuantity:
    data_name: str          # preCICE data name (rendered)
    quantity: str           # Forge quantity id
    unit: str               # Forge unit (values cross preCICE normalized to this unit)
    writer: str             # participant that writes it
    absolute_limit: float   # explicit absolute convergence measure, in `unit`


@dataclass(frozen=True)
class ScalarTwoWayContract:
    """A Forge-owned two-participant scalar coupling contract (serial-implicit)."""

    contract_id: str
    first: str
    second: str
    exchanges: tuple[ExchangedQuantity, ExchangedQuantity]
    max_iterations: int
    relaxation: float
    time_window: float
    max_time: float
    participant_setup: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 < self.relaxation <= 1:
            raise ValueError("relaxation factor must be in (0, 1]")
        if self.max_iterations < 2:
            raise ValueError("implicit coupling needs at least two iterations")
        for x in self.exchanges:
            if not x.absolute_limit > 0:
                raise ValueError(f"{x.data_name}: an explicit positive absolute convergence limit is required; none is defaulted")
        if {x.writer for x in self.exchanges} != {self.first, self.second}:
            raise ValueError("each participant must write exactly one exchanged quantity")

    def to_dict(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id, "first": self.first, "second": self.second,
                "exchanges": [x.__dict__ for x in self.exchanges], "max_iterations": self.max_iterations,
                "relaxation": self.relaxation, "time_window": self.time_window, "max_time": self.max_time,
                "participant_setup": {k: dict(v) for k, v in self.participant_setup.items()}}

    def render(self, exchange_dir: str) -> str:
        """Render the preCICE v3 configuration for this contract."""
        mesh = {p: f"{p}Mesh" for p in (self.first, self.second)}
        data = "".join(f'  <data:scalar name="{x.data_name}"/>\n' for x in self.exchanges)
        meshes = "".join(
            f'  <mesh name="{mesh[p]}" dimensions="2">\n' + "".join(f'    <use-data name="{x.data_name}"/>\n' for x in self.exchanges) + "  </mesh>\n"
            for p in (self.first, self.second))
        parts = ""
        for p, other in ((self.first, self.second), (self.second, self.first)):
            w = next(x for x in self.exchanges if x.writer == p)
            r = next(x for x in self.exchanges if x.writer == other)
            parts += (f'  <participant name="{p}">\n    <provide-mesh name="{mesh[p]}"/>\n    <receive-mesh name="{mesh[other]}" from="{other}"/>\n'
                      f'    <write-data name="{w.data_name}" mesh="{mesh[p]}"/>\n    <read-data name="{r.data_name}" mesh="{mesh[p]}"/>\n'
                      f'    <mapping:nearest-neighbor direction="read" from="{mesh[other]}" to="{mesh[p]}" constraint="consistent"/>\n  </participant>\n')
        ex = "".join(f'    <exchange data="{x.data_name}" mesh="{mesh[x.writer]}" from="{x.writer}" to="{self.second if x.writer == self.first else self.first}" initialize="true"/>\n'
                     for x in self.exchanges)
        conv = "".join(f'    <absolute-convergence-measure limit="{x.absolute_limit!r}" data="{x.data_name}" mesh="{mesh[x.writer]}"/>\n' for x in self.exchanges)
        second_writes = next(x for x in self.exchanges if x.writer == self.second)
        return (
            '<?xml version="1.0" encoding="UTF-8" ?>\n<precice-configuration>\n' + data + meshes + parts
            + f'  <m2n:sockets acceptor="{self.first}" connector="{self.second}" exchange-directory="{exchange_dir}"/>\n'
            + f'  <coupling-scheme:serial-implicit>\n    <participants first="{self.first}" second="{self.second}"/>\n'
            + f'    <max-time value="{self.max_time!r}"/>\n    <time-window-size value="{self.time_window!r}"/>\n'
            + f'    <max-iterations value="{self.max_iterations}"/>\n' + ex + conv
            + f'    <acceleration:constant>\n      <relaxation value="{self.relaxation!r}"/>\n    </acceleration:constant>\n'
            + '  </coupling-scheme:serial-implicit>\n</precice-configuration>\n'
        )
        del second_writes  # noqa -- rendering is fully determined by the contract


@dataclass(frozen=True)
class PreciceExecutionRecord:
    contract: Mapping[str, Any]
    precice_version: str
    config_digest: str
    succeeded: bool
    values: Mapping[str, float]
    iterations: tuple[int, ...]
    reason: str = ""
    participant_logs: Mapping[str, Any] = field(default_factory=dict)

    @property
    def execution_identity(self) -> str:
        payload = json.dumps({"contract": self.contract, "precice": self.precice_version, "config": self.config_digest}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "coupling_execution_not_scientific_evidence", "execution_identity": self.execution_identity,
                "precice_version": self.precice_version, "config_digest": self.config_digest, "succeeded": self.succeeded,
                "values": dict(self.values) if self.succeeded else {}, "iterations": list(self.iterations), "reason": self.reason}


def execute(contract: ScalarTwoWayContract, fixed_point_check, *, timeout: float = 300.0) -> PreciceExecutionRecord:
    """Run both participants of ``contract`` as preCICE processes and check the result.

    ``fixed_point_check(values) -> (ok, detail)`` is Forge's independent
    acceptance test on the exchanged values (e.g. re-evaluating both models
    at the final values); preCICE's own convergence flag is not sufficient.
    """
    ok, version = precice_available()
    if not ok:
        from engcore.numerical.core import ProviderUnavailable
        raise ProviderUnavailable(f"preCICE is not available here: {version}")
    work = tempfile.mkdtemp(prefix="forge-precice-")
    xml = contract.render(work)
    digest = hashlib.sha256(xml.encode()).hexdigest()
    cfg = os.path.join(work, "precice-config.xml")
    with open(cfg, "w") as fh:
        fh.write(xml)
    import engcore
    env = dict(os.environ)
    # children run in the temp work dir: give them absolute import roots
    roots = [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
             os.path.dirname(os.path.dirname(os.path.abspath(engcore.__file__)))]
    env["PYTHONPATH"] = os.pathsep.join(roots + [os.path.abspath(p) for p in env.get("PYTHONPATH", "").split(os.pathsep) if p])
    procs = {}
    for name in (contract.first, contract.second):
        spec = json.dumps({"config": cfg, "participant": name, "contract": contract.to_dict()})
        procs[name] = subprocess.Popen([sys.executable, "-m", "forge_precice.driver", spec], cwd=work, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    outputs, logs = {}, {}
    for name, proc in procs.items():
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            for p in procs.values():
                p.kill()
            return PreciceExecutionRecord(contract.to_dict(), version, digest, False, {}, (), "timeout")
        logs[name] = {"returncode": proc.returncode, "stderr_tail": err[-400:]}
        if proc.returncode != 0:
            return PreciceExecutionRecord(contract.to_dict(), version, digest, False, {}, (), f"{name} exited {proc.returncode}", logs)
        outputs[name] = json.loads(out.strip().splitlines()[-1])
    iterations = tuple(outputs[contract.second]["iterations_per_window"])
    values = {k: v for o in outputs.values() for k, v in o["final_written"].items()}
    if any(i >= contract.max_iterations for i in iterations):
        return PreciceExecutionRecord(contract.to_dict(), version, digest, False, {}, iterations,
                                      "a time window reached max-iterations; preCICE continues, Forge refuses", logs)
    ok, detail = fixed_point_check(values)
    if not ok:
        return PreciceExecutionRecord(contract.to_dict(), version, digest, False, {}, iterations, f"Forge fixed-point check failed: {detail}", logs)
    return PreciceExecutionRecord(contract.to_dict(), version, digest, True, values, iterations, detail, logs)
