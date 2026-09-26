"""Generic multiphysics coupling adapters (BIG 9) for the existing runtime.

The coupling ENGINE is the existing ``engcore.execution.multiphysics.MultiphysicsRuntime``
(graph/plan fingerprints, serial/Jacobi iteration, relaxation, residuals,
field mapping, conservation audit, state-transition receipts, BIG 2 events).
This package does not duplicate it.  It adds the bridges that let any provider
become a participant of that engine:

* :func:`provider_participant` -- wraps a provider-neutral ``solve`` (a BIG 8
  PDE provider, a BIG 6 numerical provider, or anything returning an execution
  record) into the runtime's ``CallbackParticipant``.  Every call REBUILDS the
  provider problem from the incoming coupling values, so each iterate has its
  own problem digest and execution identity; a failed execution raises, so
  the runtime refuses the window and no partially coupled field is accepted.
* :func:`field_port`, :func:`spatial_to_record`, :func:`record_to_spatial` --
  typed conversion between BIG 7 ``SpatialField`` and the Core ``FieldRecord``
  carried by runtime ports (mesh, unit, location, components, frame preserved).

Nothing here decides applicability, validity or evidence.  Coupled convergence
is numerical; conservation audits are diagnostics; neither is validation.
"""

from .adapters import (
    CouplingExecutionLog, ParticipantStateContract, StateCompleteness, field_port, mapped_input, provider_participant,
    record_to_spatial, scalar_port, spatial_to_record,
)

__all__ = ["CouplingExecutionLog", "ParticipantStateContract", "StateCompleteness", "field_port", "mapped_input",
           "provider_participant", "record_to_spatial", "scalar_port", "spatial_to_record"]
