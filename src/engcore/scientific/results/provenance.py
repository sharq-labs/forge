"""Provenance record.

Mandatory for every scientific result: a number whose origin cannot be
reconstructed is not a scientific result.

Privacy position: this module **collects nothing on its own**. Software
version, git commit, environment facts and timestamps are all supplied by the
caller. Auto-harvesting machine identity would be both a privacy problem and
a determinism problem (records would differ between runs that are otherwise
identical).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..ir.problem import ModelReference
from ..ir.values import (
    ScientificValue,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..realizations.definition import RealizationReference
from ..serialization import (
    require_schema,
    require_schema_any,
    schema_string,
    unwritable,
)
from ..solvers.protocol import SolverIdentity
from .immutable import detach, freeze
from ..composition.transfer import QuantityTransfer, require_agreeing_transfers
from ..units.quantity import Quantity

#: Bumped for typed ``inputs``. A record may now carry any
#: :data:`~engcore.scientific.ir.values.ScientificValue` -- an integer count, a
#: declared flag, a category -- where /1../3 could carry only a ``Quantity``.
#: The bump is about the READER, not the writer: an older reader calls
#: ``Quantity.from_dict`` on every input and would fail on a categorical one, so
#: a /4 record is not readable by code that predates it. Reading older records
#: needs no migration at all -- ``decode_value`` dispatches on each value's own
#: schema, and a /1 input is a ``quantity/1`` payload, which decodes to the same
#: ``Quantity`` it always did.
PROVENANCE_SCHEMA = schema_string("provenance_record", 4)

#: The version before ``inputs`` could hold anything but a ``Quantity``. Bumped
#: for ``bindings``: a record carrying only participant *sets* cannot state
#: which realization computed which model on which solver once any of them has
#: more than one member, and a producer writing four models and one realization
#: would leave the association unrecoverable. That association is scientific
#: content, so an old reader dropping it would attribute a result to a
#: computation it did not perform. Same rule, and same mechanism, as
#: ``scientific_result/2`` (DATA-BOUNDARY0 §4).
PROVENANCE_SCHEMA_V3 = schema_string("provenance_record", 3)

#: The version before ``transfers`` existed. Still read, never written. Bumped
#: on the argument every other bump here has used: a quantity that crossed into
#: this run from another domain is scientific content, not decoration. A reader
#: that dropped it would report a result while losing the fact that one of the
#: numbers behind it came from somewhere else -- which is exactly the state
#: this field was added to end.
PROVENANCE_SCHEMA_V2 = schema_string("provenance_record", 2)

#: The version before ``bindings`` existed. Still read, never written.
PROVENANCE_SCHEMA_V1 = schema_string("provenance_record", 1)

#: Exactly the versions this reader interprets. A tuple of exact strings, not
#: a range: a range would admit versions that do not exist yet.
SUPPORTED_PROVENANCE_SCHEMAS = (
    PROVENANCE_SCHEMA_V1,
    PROVENANCE_SCHEMA_V2,
    PROVENANCE_SCHEMA_V3,
    PROVENANCE_SCHEMA,
)

EXECUTION_BINDING_SCHEMA = schema_string("execution_binding")


@dataclass(frozen=True)
class ExecutionBinding:
    """One executed computation: which model, realized how, run by what.

    This is the record that preserves the ternary relation

    ``model -> realization -> concrete solver``

    which three independent participant tuples lose the moment any of them
    holds more than one member. Association is **structural** here: it comes
    from the three fields of one record, never from the position of an entry
    in a list. Two bindings in any order say exactly the same thing.

    ``realization`` is optional, and ``None`` is a real answer rather than a
    gap to be filled: every solver predating MODEL0-R computed a model without
    declaring a realization, and such a binding still carries a true and
    useful model-to-solver association. It is never inferred.

    The three members are the identities that already exist —
    :class:`~engcore.scientific.ir.problem.ModelReference`,
    :class:`~engcore.scientific.realizations.definition.RealizationReference`
    and :class:`~engcore.scientific.solvers.protocol.SolverIdentity`. No new
    identity scheme is introduced, and nothing here embeds a definition.

    Note what does **not** happen: the concrete solver lives on *this* record,
    not on ``ModelRealizationDefinition``. A realization is a way of computing
    a claim, not one execution of it, and the same realization run on a
    second backend must remain the same realization.
    """

    model: ModelReference
    solver: SolverIdentity
    realization: RealizationReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelReference):
            raise ScientificCoreError(
                f"execution binding requires a ModelReference, got "
                f"{type(self.model).__name__}"
            )
        if not isinstance(self.solver, SolverIdentity):
            raise ScientificCoreError(
                f"execution binding requires a SolverIdentity, got "
                f"{type(self.solver).__name__}"
            )
        if self.realization is not None and not isinstance(
            self.realization, RealizationReference
        ):
            raise ScientificCoreError(
                f"execution binding realization must be a "
                f"RealizationReference or None, got "
                f"{type(self.realization).__name__}"
            )

    @classmethod
    def from_execution(
        cls,
        prepared,
        raw,
        *,
        model,
        realization=None,
    ) -> "ExecutionBinding":
        """A binding stated by an execution rather than typed by hand.

        The defect this exists for: three names in a constructor are three
        names. Nothing about ``ExecutionBinding(model=..., solver=...,
        realization=...)`` requires that the solver ever ran, and a record
        assembled after the fact -- which is how a transport boundary assembles
        one -- can name a solver that did nothing while looking exactly like a
        record of work.

        This constructor takes the two objects that exist **because** the work
        happened: a :class:`PreparedSolve`, which only ``prepare()`` returns,
        and a :class:`RawSolverOutput`, which only ``solve()`` returns. The
        solver identity is read off ``prepared.solver`` rather than accepted as
        an argument, so the binding cannot name a solver other than the one
        that prepared this solve. The model must be one the prepared problem
        actually names, so it cannot name a model the run was not about.

        It is not a proof of execution and this docstring will not pretend
        otherwise: a caller determined to lie can construct a ``RawSolverOutput``
        by hand. What it removes is the accident -- the record assembled from
        what a boundary *believes* ran, which is the live case this guard was
        written for. ``NEEDS.md`` G5.1 records what a real proof would cost.
        """
        solver = getattr(prepared, "solver", None)
        if not isinstance(solver, SolverIdentity):
            raise ScientificCoreError(
                "a binding from an execution needs a PreparedSolve carrying a "
                f"SolverIdentity; got {type(prepared).__name__}"
            )
        if not hasattr(raw, "convergence"):
            raise ScientificCoreError(
                "a binding from an execution needs the RawSolverOutput that "
                f"solve() returned; got {type(raw).__name__}"
            )
        problem = getattr(prepared, "problem", None)
        named = {reference.key for reference in getattr(problem, "models", ())}
        if named and model.key not in named:
            raise ScientificCoreError(
                f"the prepared problem does not name model "
                f"{model.model_id}@{model.version}; it names "
                f"{sorted(f'{a}@{b}' for a, b in named)}. A binding cannot "
                f"attribute this execution to a model the problem was not about"
            )
        return cls(model=model, solver=solver, realization=realization)

    @property
    def key(self) -> tuple[tuple[str, str], tuple[str, str] | None, tuple[str, str]]:
        """Order-independent identity of the association this binding states."""
        return (
            self.model.key,
            self.realization.key if self.realization else None,
            self.solver.key,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXECUTION_BINDING_SCHEMA,
            "model": self.model.to_dict(),
            "realization": (
                self.realization.to_dict() if self.realization else None
            ),
            "solver": self.solver.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionBinding":
        require_schema(payload, EXECUTION_BINDING_SCHEMA)
        realization = payload.get("realization")
        return cls(
            model=ModelReference.from_dict(payload["model"]),
            solver=SolverIdentity.from_dict(payload["solver"]),
            realization=(
                RealizationReference.from_dict(realization)
                if realization
                else None
            ),
        )


@dataclass(frozen=True)
class StoredParentClaim:
    """A lineage claim a stored record already carries, reproduced not re-made.

    :class:`ProvenanceRecord` refuses a bare ``parent_run_id``: naming a source
    means holding it. Reading a record back is the one situation where that is
    both impossible and not being asked for -- the claim was made by whoever
    wrote the payload, and ``from_dict`` is reproducing it, not asserting it
    afresh. So the reader passes this instead of the record it does not have,
    and the difference between "I hold the parent" and "this payload says there
    was one" is a type rather than a flag nobody can see.
    """

    run_id: str

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise ScientificCoreError(
                "a stored parent claim must name a run; a payload whose "
                "parent_run_id is blank carries no claim to reproduce"
            )
        object.__setattr__(self, "run_id", run_id)


@dataclass(frozen=True)
class ProvenanceRecord:
    """Everything needed to attribute and re-derive a result.

    Two representations, and exactly one of them is canonical.

    ``bindings``
        The **canonical** statement of what was computed: a set of
        :class:`ExecutionBinding` records, each naming one model, optionally
        the realization that computed it, and the concrete solver that ran it.
        The association is structural, so it survives any number of
        participants and any ordering.

    ``models`` / ``solvers``
        Participant **sets**, kept because most of the repository writes them
        and reads them. They say who took part and nothing about who worked
        with whom. When ``bindings`` are present these are a *derived view* —
        computed from the bindings, never a second place to edit — and a
        caller passing values that contradict the bindings is refused rather
        than silently reconciled.

    A record may legitimately carry participants with no bindings: that is
    every producer written before this contract existed, and it is honest.
    What it may not do is imply an association it does not state.
    """

    run_id: str
    software_version: str = ""
    git_commit: str | None = None
    models: tuple[tuple[str, str], ...] = ()      # (model_id, version)
    solvers: tuple[tuple[str, str], ...] = ()     # (solver_id, version)
    #: The canonical model -> realization -> solver relation. Empty means no
    #: association was recorded — never that none existed, and never a licence
    #: to infer one by pairing ``models`` with ``solvers`` positionally.
    bindings: tuple[ExecutionBinding, ...] = ()
    #: Quantities that crossed into this run from another problem, each with
    #: the declaration it realizes, the record it was read from and the instant
    #: it was read at. Empty means nothing crossed *that anybody declared* —
    #: which, until this field existed, was indistinguishable from nothing
    #: crossing at all. Two transfers of one declaration at one instant must
    #: agree; a contradiction is refused rather than resolved by order.
    transfers: tuple[QuantityTransfer, ...] = ()
    #: Every execution-relevant scientific input, as the typed union
    #: `ScientificProblem` already speaks. See `__post_init__`.
    inputs: Mapping[str, ScientificValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    tolerances: Mapping[str, float] = field(default_factory=dict)
    environment: Mapping[str, str] = field(default_factory=dict)
    timestamp: str | None = None
    #: The run this one derives from. **Never set directly.** It is filled from
    #: ``parent``, which is the record itself -- see the refusal in
    #: ``__post_init__``.
    parent_run_id: str | None = None
    #: The parent, presented rather than named. Consumed by ``__post_init__``
    #: and never stored: what survives is ``parent_run_id``, which is what a
    #: payload can carry. Compared and repr'd out, because it is an argument
    #: rather than a field -- two records that agree on their lineage are equal
    #: whether one was built from a record and the other read back from a
    #: payload.
    parent: "ProvenanceRecord | StoredParentClaim | None" = field(
        default=None, repr=False, compare=False
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise ScientificCoreError("provenance requires a non-empty run_id")
        object.__setattr__(self, "run_id", run_id)

        self._resolve_lineage(run_id)
        object.__setattr__(
            self, "transfers", require_agreeing_transfers(tuple(self.transfers))
        )

        models = tuple((str(a), str(b)) for a, b in self.models)
        solvers = tuple((str(a), str(b)) for a, b in self.solvers)

        bindings = tuple(self.bindings)
        for binding in bindings:
            if not isinstance(binding, ExecutionBinding):
                raise ScientificCoreError(
                    f"provenance bindings must be ExecutionBinding records, "
                    f"got {type(binding).__name__}"
                )
        # Deterministic and duplicate-free: two identical bindings state one
        # fact, and the order they were appended in must not be readable as
        # information.
        bindings = tuple(
            sorted(
                {b.key: b for b in bindings}.values(),
                key=lambda b: (
                    b.model.key,
                    b.realization.key if b.realization else ("", ""),
                    b.solver.key,
                ),
            )
        )
        object.__setattr__(self, "bindings", bindings)

        if bindings:
            # The participant sets become a derived view. A caller may still
            # declare extra participants that no binding covers — partial
            # knowledge is honest — but may not contradict a binding.
            bound_models = {b.model.key for b in bindings}
            bound_solvers = {b.solver.key for b in bindings}
            for label, declared, bound in (
                ("models", set(models), bound_models),
                ("solvers", set(solvers), bound_solvers),
            ):
                if declared and not bound <= declared:
                    raise ScientificCoreError(
                        f"provenance {run_id!r}: {label} {sorted(declared)} "
                        f"contradicts the bindings, which name "
                        f"{sorted(bound - declared)}; bindings are canonical, "
                        f"so pass {label} consistent with them or omit it"
                    )
                # And, for solvers only, the other direction -- which is
                # where a participant that did nothing hides.
                #
                # A model may legitimately appear with no binding: its
                # assumptions travel with the result, its validity was
                # assessed, and no solver executed it. That is partial
                # knowledge and it is honest.
                #
                # A solver may not. Executing is the only thing a solver does,
                # so naming one in a record that *states what ran* is a claim
                # that it ran, and the binding is where a record says what it
                # ran. Before this check the battery transport named a solver
                # whose `validate` never executed, in a record that otherwise
                # looked exactly like a record of work.
                if label == "solvers":
                    unbound = sorted(declared - bound)
                    if unbound:
                        raise ScientificCoreError(
                            f"provenance {run_id!r} names solver(s) {unbound} "
                            f"that no binding covers. This record states what "
                            f"ran; a solver beside the bindings is a name with "
                            f"no execution behind it. Bind it with "
                            f"ExecutionBinding.from_execution(), or leave it out"
                        )
            if not models:
                models = tuple(sorted(bound_models))
            if not solvers:
                solvers = tuple(sorted(bound_solvers))

        object.__setattr__(self, "models", models)
        object.__setattr__(self, "solvers", solvers)
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

        inputs = dict(self.inputs)
        for name, value in inputs.items():
            # THE UNION, not the Quantity alone. `ScientificProblem` has always
            # carried its parameters as a `ScientificValue` -- a dimensional
            # Quantity, an exact integer count, a declared flag, or a category
            # -- and provenance accepted only the first of the four. A study
            # legitimately turns on `steady_state = True` or
            # `material = "aluminum"`, and those change which model applies and
            # what the result means.
            #
            # This was not a silent drop, which is the one thing that would
            # have been worse: the record REFUSED them, so a producer either
            # left an execution-relevant input out of provenance entirely or
            # smuggled it into untyped `metadata`, where nothing checks it and
            # nothing can read its type back.
            #
            # `require_scientific_value` refuses everything outside the union,
            # so a bare int or a naked string is still refused -- and a bare
            # float still is, which is what "provenance never records
            # unit-stripped values" was protecting.
            require_scientific_value(
                value, context=f"provenance input {name!r}"
            )
        # Frozen rather than merely copied. ``frozen=True`` protects the
        # attribute and not the object behind it, so `provenance.inputs[...] = 5`
        # was accepted on every record this platform has ever produced —
        # including one whose whole purpose is to say what a result was
        # computed from. See ``results.immutable``.
        object.__setattr__(self, "inputs", freeze(inputs))
        object.__setattr__(
            self,
            "tolerances",
            freeze({str(k): float(v) for k, v in self.tolerances.items()}),
        )
        object.__setattr__(
            self,
            "environment",
            freeze({str(k): str(v) for k, v in self.environment.items()}),
        )
        # The same refusal the result makes, for the same reason and in the
        # same words: provenance that cannot be written down is the sharpest
        # form of provenance that does not exist.
        unrecordable = unwritable(self.metadata, path="metadata")
        if unrecordable is not None:
            where, kind = unrecordable
            raise ScientificCoreError(
                f"provenance for run {str(self.run_id).strip()!r} cannot be "
                f"recorded: {where} is a {kind}, which no scientific record "
                f"can carry"
            )
        object.__setattr__(self, "metadata", freeze(self.metadata))

    # ---- derived views over the canonical bindings ----------------------
    @property
    def realizations(self) -> tuple[tuple[str, str], ...]:
        """``(realization_id, version)`` for every realization that ran.

        A **derived view**, not a stored field: it is computed from
        ``bindings`` and there is nowhere else to write it, so it cannot
        drift from the association it summarises. Deduplicated and sorted.

        Being a set, it carries no association — which is exactly why it is
        derived rather than canonical. Use :meth:`bindings_for_model` or
        :attr:`bindings` when the pairing matters.
        """
        return tuple(
            sorted(
                {
                    b.realization.key
                    for b in self.bindings
                    if b.realization is not None
                }
            )
        )

    @property
    def executed_solvers(self) -> tuple[tuple[str, str], ...]:
        """The solvers a binding actually names, which is not ``solvers``.

        ``solvers`` is the participant set: every producer written before
        bindings existed fills it, and it says who was present, not who worked.
        This says who a recorded execution is attributed to. When bindings are
        present the two agree by construction -- ``__post_init__`` refuses a
        participant no binding covers -- and when they are absent this is
        empty, which is the honest answer to "which solver executed this" for a
        record that never said.
        """
        return tuple(sorted({b.solver.key for b in self.bindings}))

    @property
    def executed_models(self) -> tuple[tuple[str, str], ...]:
        """The models a binding attributes an execution to. See above."""
        return tuple(sorted({b.model.key for b in self.bindings}))

    def bindings_for_model(
        self, model_id: str, version: str | None = None
    ) -> tuple[ExecutionBinding, ...]:
        """Every binding naming this model. Exact match; nothing is inferred.

        Returns empty when the record states no association for the model —
        including when the model appears in ``models``. Absence of a recorded
        association is not an invitation to construct one.
        """
        return tuple(
            b
            for b in self.bindings
            if b.model.model_id == str(model_id)
            and (version is None or b.model.version == str(version))
        )

    def solvers_for_realization(
        self, realization_id: str, version: str | None = None
    ) -> tuple[SolverIdentity, ...]:
        """Which concrete solvers executed this realization.

        The question a set of participant tuples cannot answer, and the
        reason this contract exists: one realization run on two backends is
        one realization, and the record has to be able to say so.
        """
        return tuple(
            b.solver
            for b in self.bindings
            if b.realization is not None
            and b.realization.realization_id == str(realization_id)
            and (version is None or b.realization.version == str(version))
        )

    def _resolve_lineage(self, run_id: str) -> None:
        """Fill ``parent_run_id`` from a parent that was actually presented.

        THE DEFECT. ``parent_run_id`` was a string a caller typed. Nothing
        about ``ProvenanceRecord(parent_run_id="run-0001")`` required that
        ``run-0001`` ever existed, ever ran, or was ever anything at all -- so
        a provenance record could make a claim about a source that was never
        there, which is the one claim this project exists to make impossible,
        violated in its own record type.

        THE RULE. Naming a source means holding it. ``parent`` takes the parent
        record; ``parent_run_id`` is read off it and is not accepted on its own.
        This is the shape ``ExecutionBinding.from_execution`` already uses one
        field over: take the object that exists *because* the thing happened,
        rather than the name someone believes it had.

        It is not a proof that the parent run occurred, and this will not
        pretend otherwise -- a caller determined to lie can build a
        ``ProvenanceRecord`` to be the parent. What it removes is the accident:
        the lineage assembled from what a boundary *believes* ran, the typo
        that points a chain at nothing, and the copied-and-edited record whose
        parent id still names the run it was copied from.

        The one exception is a type rather than a flag.
        :class:`StoredParentClaim` says "this payload carries a claim someone
        else made", which is exactly what ``from_dict`` is doing and is not the
        same act as making one.
        """
        parent = self.parent
        claimed = self.parent_run_id
        claimed = None if claimed is None else str(claimed).strip()

        if parent is None:
            if claimed:
                raise ScientificCoreError(
                    f"provenance {run_id!r} names {claimed!r} as its parent "
                    f"run but was not given it. A provenance record making a "
                    f"claim about a source it cannot show is the claim this "
                    f"platform exists to refuse. Pass parent=<the parent "
                    f"ProvenanceRecord>, or call parent.derived({run_id!r})"
                )
            object.__setattr__(self, "parent_run_id", None)
            return

        if isinstance(parent, StoredParentClaim):
            named = parent.run_id
        elif isinstance(parent, ProvenanceRecord):
            named = parent.run_id
        else:
            raise ScientificCoreError(
                f"provenance {run_id!r} was given a "
                f"{type(parent).__name__} as its parent. A lineage claim is "
                f"about a ProvenanceRecord; anything else is a name wearing an "
                f"object's clothes"
            )

        if claimed and claimed != named:
            raise ScientificCoreError(
                f"provenance {run_id!r} names {claimed!r} as its parent run "
                f"while holding a parent whose run is {named!r}. Two different "
                f"answers to one question, and picking either would let the "
                f"typed one silently outrank the one that exists"
            )
        if named == run_id:
            raise ScientificCoreError(
                f"provenance {run_id!r} names itself as its own parent run. A "
                f"lineage that closes on itself has no source and no root, and "
                f"a reader walking it does not terminate"
            )
        object.__setattr__(self, "parent_run_id", named)
        # What is KEPT is the marker, never the parent record itself. Two
        # reasons, and the second is the one that was measured rather than
        # reasoned:
        #
        # A record must not hold a handle on its whole ancestry -- a chain
        # forty runs deep would be forty records alive because the last one is.
        #
        # And `dataclasses.replace` re-runs this constructor with the fields it
        # finds. Setting `parent` to None here made every `replace` on a record
        # that HAS a parent illegal, because the rebuilt record would be naming
        # a source with nothing behind it -- a rule that refused the honest
        # reconstruction of a record it had already accepted. Five MVR1 tests
        # said so. The marker is what makes the reconstruction legal and says
        # what it is: a claim being reproduced, not made afresh.
        object.__setattr__(self, "parent", StoredParentClaim(named))

    def derived(self, run_id: str, **overrides: Any) -> "ProvenanceRecord":
        """A child record that keeps the lineage link explicit.

        Rebinding ``models`` while inheriting bindings is refused. A binding
        names the model it is about, so an inherited binding would contradict
        the new participant set rather than silently mis-attribute — but
        refusing early says what the caller has to decide instead of letting
        the consistency check phrase it as a contradiction.
        """
        if "models" in overrides and "bindings" not in overrides and self.bindings:
            raise ScientificCoreError(
                f"provenance {self.run_id!r}: rebinding 'models' while "
                f"inheriting {len(self.bindings)} execution binding(s) would "
                f"carry associations about a model the child does not claim; "
                f"pass 'bindings' explicitly (use () to drop them)"
            )
        base = {
            "run_id": run_id,
            "software_version": self.software_version,
            "git_commit": self.git_commit,
            "models": self.models,
            "solvers": self.solvers,
            "bindings": self.bindings,
            "transfers": self.transfers,
            "inputs": self.inputs,
            "assumptions": self.assumptions,
            "tolerances": self.tolerances,
            "environment": self.environment,
            "timestamp": self.timestamp,
            # The parent, held rather than named. `derived` is the constructor
            # that has always had it; now it is the one that says so.
            "parent": self,
            "metadata": self.metadata,
        }
        base.update(overrides)
        return ProvenanceRecord(**base)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROVENANCE_SCHEMA,
            "run_id": self.run_id,
            "software_version": self.software_version,
            "git_commit": self.git_commit,
            # Participant sets. When ``bindings`` is non-empty these are a
            # derived view of it, written so that a reader interested only in
            # "who took part" needs no knowledge of the relation.
            "models": [list(m) for m in self.models],
            "solvers": [list(s) for s in self.solvers],
            # Canonical. ``realizations`` is deliberately NOT serialized: it
            # is derived, and writing it would create the second source of
            # truth this contract exists to remove.
            "bindings": [b.to_dict() for b in self.bindings],
            "inputs": {
                k: encode_value(v) for k, v in sorted(self.inputs.items())
            },
            "transfers": [t.to_dict() for t in self.transfers],
            "assumptions": list(self.assumptions),
            # Not detached, and provably not needing to be: __post_init__
            # coerces every value here through ``float`` and ``str``, so these
            # two mappings hold only scalars and a fresh outer dict shares
            # nothing. ``metadata`` below is the free-form one and is the only
            # place a nested alias could have been.
            "tolerances": dict(sorted(self.tolerances.items())),
            "environment": dict(sorted(self.environment.items())),
            "timestamp": self.timestamp,
            "parent_run_id": self.parent_run_id,
            # Detached at every depth, in one pass. ``to_dict`` used to build
            # a fresh outer dict and hand out the record's own nested objects,
            # so editing a payload edited the record it came from.
            "metadata": {
                key: detach(value)
                for key, value in sorted(self.metadata.items(), key=lambda kv: kv[0])
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProvenanceRecord":
        version = require_schema_any(payload, SUPPORTED_PROVENANCE_SCHEMAS)
        # The one compatibility branch, decided by version and not by key
        # presence. ``provenance_record/1`` predates execution bindings and
        # cannot have written one, so it loads with none.
        #
        # It is NOT upgraded by inference. A ``/1`` record with exactly one
        # model and one solver looks like it determines a binding, and does
        # not: it never stated that the solver computed that model, and
        # manufacturing the association here would put a claim into the
        # record that its author never made. Unrecorded stays unrecorded.
        bindings = (
            ()
            if version == PROVENANCE_SCHEMA_V1
            else tuple(
                ExecutionBinding.from_dict(b) for b in payload.get("bindings", ())
            )
        )
        return cls(
            run_id=payload["run_id"],
            software_version=payload.get("software_version", ""),
            git_commit=payload.get("git_commit"),
            models=tuple(tuple(m) for m in payload.get("models", ())),
            solvers=tuple(tuple(s) for s in payload.get("solvers", ())),
            bindings=bindings,
            # By version, not by key presence — the rule ``/1`` established.
            # A ``/1`` or ``/2`` writer could not carry a transfer, and a key
            # appearing in one of their payloads was not written by this
            # contract and is not read as if it were.
            transfers=(
                ()
                if version in (PROVENANCE_SCHEMA_V1, PROVENANCE_SCHEMA_V2)
                else tuple(
                    QuantityTransfer.from_dict(x)
                    for x in payload.get("transfers", ())
                )
            ),
            # `decode_value` dispatches on each value's OWN schema, so a
            # /1../3 record -- whose inputs are all `quantity/1` payloads --
            # decodes to exactly the Quantities it always did. No migration,
            # no version branch, and nothing older is reinterpreted.
            inputs={
                k: decode_value(v)
                for k, v in (payload.get("inputs") or {}).items()
            },
            assumptions=tuple(payload.get("assumptions", ())),
            tolerances=dict(payload.get("tolerances", {})),
            environment=dict(payload.get("environment", {})),
            timestamp=payload.get("timestamp"),
            # Reproducing a claim, not making one -- see StoredParentClaim.
            parent=(
                StoredParentClaim(payload["parent_run_id"])
                if str(payload.get("parent_run_id") or "").strip()
                else None
            ),
            metadata=dict(payload.get("metadata", {})),
        )
