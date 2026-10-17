from enum import Enum, IntEnum
from .route import VerificationRouteKind


class VerificationLevel(IntEnum):
    V0=0
    V1=1
    V2=2
    V3=3
    V4=4
    V5=5
    V6=6
    V7=7


def level_for_route(kind:VerificationRouteKind)->VerificationLevel:
    mapping={
        VerificationRouteKind.SAME_SOLVER_RERUN:VerificationLevel.V0,
        VerificationRouteKind.DIFFERENT_ALGORITHM:VerificationLevel.V1,
        VerificationRouteKind.DIFFERENT_IMPLEMENTATION:VerificationLevel.V2,
        VerificationRouteKind.DIFFERENT_MODEL:VerificationLevel.V3,
        VerificationRouteKind.ANALYTICAL_REFERENCE:VerificationLevel.V4,
        VerificationRouteKind.EXTERNAL_SOLVER:VerificationLevel.V5,
        VerificationRouteKind.EXPERIMENTAL_MEASUREMENT:VerificationLevel.V6,
        VerificationRouteKind.INDEPENDENT_REPRODUCTION:VerificationLevel.V7,
    }
    return mapping[VerificationRouteKind(kind)]


class VerificationEvidenceCategory(str,Enum):
    """The kind of scientific evidence a verification route provides (Phase 1 BR5).

    The V-levels number the route kinds; they are not an ordinal scale of one
    quantity.  An experiment (V6) is validation, not a stronger verification;
    a different model (V3) verifies nothing about this model's code; an
    external solver (V5) is not an analytical reference (V4).  A requirement is
    therefore a category, and a category is satisfied only by the route kinds
    :data:`CATEGORY_PROVIDERS` names for it.
    """
    REPEATABILITY="repeatability"
    SOLUTION_VERIFICATION="solution_verification"
    CODE_VERIFICATION="code_verification"
    MODEL_FORM_COMPARISON="model_form_comparison"
    ANALYTICAL_COMPARISON="analytical_comparison"
    INDEPENDENT_SOLVER_CORROBORATION="independent_solver_corroboration"
    EXPERIMENTAL_VALIDATION="experimental_validation"
    REPRODUCIBILITY="reproducibility"


#: The category each level's own route kind provides.  It is also how a legacy
#: ``minimum_level`` is read: as a requirement for THAT category, never "this
#: number or any larger one".
_LEVEL_CATEGORY={
    VerificationLevel.V0:VerificationEvidenceCategory.REPEATABILITY,
    VerificationLevel.V1:VerificationEvidenceCategory.SOLUTION_VERIFICATION,
    VerificationLevel.V2:VerificationEvidenceCategory.CODE_VERIFICATION,
    VerificationLevel.V3:VerificationEvidenceCategory.MODEL_FORM_COMPARISON,
    VerificationLevel.V4:VerificationEvidenceCategory.ANALYTICAL_COMPARISON,
    VerificationLevel.V5:VerificationEvidenceCategory.INDEPENDENT_SOLVER_CORROBORATION,
    VerificationLevel.V6:VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION,
    VerificationLevel.V7:VerificationEvidenceCategory.REPRODUCIBILITY,
}

#: Which route kinds provide each category.  Closed and explicit: nothing is
#: inferred from the level numbers.  The one many-to-one entry is
#: CODE_VERIFICATION, which code-to-code comparison provides in three forms of
#: increasing independence from this implementation -- another implementation
#: of the same model, an externally developed one, and an exact solution of the
#: same model (the strongest code-verification evidence).  Provider
#: independence is still required separately by the policy.  Everything else
#: maps one to one; in particular a rerun is repeatability, not
#: reproducibility, and an independent reproduction (which may or may not
#: re-implement anything) satisfies only reproducibility.
CATEGORY_PROVIDERS={
    VerificationEvidenceCategory.REPEATABILITY:frozenset({VerificationRouteKind.SAME_SOLVER_RERUN}),
    VerificationEvidenceCategory.SOLUTION_VERIFICATION:frozenset({VerificationRouteKind.DIFFERENT_ALGORITHM}),
    VerificationEvidenceCategory.CODE_VERIFICATION:frozenset({
        VerificationRouteKind.DIFFERENT_IMPLEMENTATION,
        VerificationRouteKind.EXTERNAL_SOLVER,
        VerificationRouteKind.ANALYTICAL_REFERENCE,
    }),
    VerificationEvidenceCategory.MODEL_FORM_COMPARISON:frozenset({VerificationRouteKind.DIFFERENT_MODEL}),
    VerificationEvidenceCategory.ANALYTICAL_COMPARISON:frozenset({VerificationRouteKind.ANALYTICAL_REFERENCE}),
    VerificationEvidenceCategory.INDEPENDENT_SOLVER_CORROBORATION:frozenset({VerificationRouteKind.EXTERNAL_SOLVER}),
    VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION:frozenset({VerificationRouteKind.EXPERIMENTAL_MEASUREMENT}),
    VerificationEvidenceCategory.REPRODUCIBILITY:frozenset({VerificationRouteKind.INDEPENDENT_REPRODUCTION}),
}


def category_for_level(level:VerificationLevel)->VerificationEvidenceCategory:
    """The category a legacy ``minimum_level`` requires."""
    return _LEVEL_CATEGORY[VerificationLevel(level)]


def category_for_route(kind:VerificationRouteKind)->VerificationEvidenceCategory:
    """The category a route kind's own level names."""
    return _LEVEL_CATEGORY[level_for_route(kind)]


def provides(kind:VerificationRouteKind,category:VerificationEvidenceCategory)->bool:
    """Whether a route of ``kind`` is evidence of ``category`` (only by :data:`CATEGORY_PROVIDERS`)."""
    return VerificationRouteKind(kind) in CATEGORY_PROVIDERS[VerificationEvidenceCategory(category)]
