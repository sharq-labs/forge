from __future__ import annotations

from itertools import combinations

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity,require_spread_unit
from engcore.uq.budget import Correlation,UncertaintyComponent,UncertaintySource as BudgetSource,aggregate_uncertainty
from .contribution import UncertaintyContribution
from .policy import CombinationMode,CombinationPolicy,MissingCorrelationPolicy
from .report import CombinationReport


def _validate_common(nominal:Quantity,contributions:tuple[UncertaintyContribution,...],policy:CombinationPolicy)->None:
    if not isinstance(nominal,Quantity): raise InvalidScientificProblem("combined UQ nominal must be Quantity")
    if not contributions: raise InvalidScientificProblem("combined UQ requires at least one contribution")
    ids=[c.contribution_id for c in contributions]
    if len(ids)!=len(set(ids)): raise InvalidScientificProblem("combined UQ contribution ids must be unique")
    seen={}
    for contribution in contributions:
        for lineage in contribution.lineage_digests:
            prior=seen.get(lineage)
            if prior is not None:
                raise InvalidScientificProblem(
                    f"double-counted uncertainty lineage {lineage}: {prior!r} and {contribution.contribution_id!r}"
                )
            seen[lineage]=contribution.contribution_id
    present={c.source_kind for c in contributions}
    missing=set(policy.required_sources)-present
    if missing: raise InvalidScientificProblem(f"combined UQ is missing required sources {sorted(x.value for x in missing)}")


def _standard_magnitude(contribution:UncertaintyContribution,spread_unit:str)->float:
    uncertainty=contribution.uncertainty
    if uncertainty.kind is not UncertaintyKind.STANDARD or uncertainty.standard_uncertainty is None:
        raise InvalidScientificProblem(f"{contribution.contribution_id!r} is not STANDARD uncertainty")
    try: return uncertainty.standard_uncertainty.magnitude_as_spread_in(spread_unit)
    except Exception as exc: raise InvalidScientificProblem(f"contribution {contribution.contribution_id!r} has incompatible dimension: {exc}") from exc


def _interval_widths(contribution:UncertaintyContribution,nominal:Quantity)->tuple[float,float]:
    u=contribution.uncertainty
    if u.kind is not UncertaintyKind.INTERVAL or u.lower is None or u.upper is None:
        raise InvalidScientificProblem(f"{contribution.contribution_id!r} is not INTERVAL uncertainty")
    try:
        lower=u.lower.to(nominal.units).magnitude;upper=u.upper.to(nominal.units).magnitude
    except Exception as exc: raise InvalidScientificProblem(f"contribution {contribution.contribution_id!r} has incompatible interval dimension: {exc}") from exc
    center=nominal.magnitude
    if lower>center or upper<center:
        raise InvalidScientificProblem(f"contribution {contribution.contribution_id!r} interval does not contain nominal value")
    return center-lower,upper-center


def _explicit_correlations(contributions,correlations,policy):
    ids={c.contribution_id for c in contributions}
    pairs={corr.key:corr for corr in correlations}
    if any(c.left_id not in ids or c.right_id not in ids for c in correlations):
        raise InvalidScientificProblem("combined UQ correlation references unknown contribution")
    expected={tuple(sorted((a.contribution_id,b.contribution_id))) for a,b in combinations(contributions,2)}
    missing=sorted(expected-set(pairs))
    assumptions=[]
    if missing and policy.missing_correlation is MissingCorrelationPolicy.REFUSE:
        raise InvalidScientificProblem(f"correlations are unspecified for contribution pairs {missing}")
    if missing:
        assumptions.extend(f"assumed_zero_correlation:{a}:{b}" for a,b in missing)
    return tuple(assumptions)


def combine_uncertainties(nominal:Quantity,contributions:tuple[UncertaintyContribution,...],
                          policy:CombinationPolicy,correlations:tuple[Correlation,...]=())->CombinationReport:
    contributions=tuple(contributions);correlations=tuple(correlations)
    _validate_common(nominal,contributions,policy)
    spread_unit=require_spread_unit(nominal.units,context="combined UQ nominal")
    assumptions=[]
    if policy.mode is CombinationMode.STANDARD_RSS:
        if any(c.uncertainty.kind is not UncertaintyKind.STANDARD for c in contributions):
            raise InvalidScientificProblem("STANDARD_RSS accepts only STANDARD uncertainty records")
        assumptions.extend(_explicit_correlations(contributions,correlations,policy))
        components=tuple(UncertaintyComponent(
            c.contribution_id,BudgetSource(c.source_kind.value),_standard_magnitude(c,spread_unit)
        ) for c in contributions)
        aggregate=aggregate_uncertainty(components,correlations)
        output=Uncertainty(kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(aggregate.standard_uncertainty,spread_unit),
            method="correlation-aware RSS over explicitly attributed uncertainty contributions",
            notes="; ".join(assumptions),source_kind=UncertaintySource.COMBINED)
    elif policy.mode is CombinationMode.CONSERVATIVE_INTERVAL:
        if correlations:
            raise InvalidScientificProblem("CONSERVATIVE_INTERVAL does not consume correlation coefficients")
        widths=[_interval_widths(c,nominal) for c in contributions]
        lower=sum(x[0] for x in widths);upper=sum(x[1] for x in widths)
        output=Uncertainty(kind=UncertaintyKind.INTERVAL,
            lower=Quantity(nominal.magnitude-lower,nominal.units),
            upper=Quantity(nominal.magnitude+upper,nominal.units),
            method="worst-case additive interval envelope; no independence assumption",
            source_kind=UncertaintySource.COMBINED)
    else:
        if correlations:
            raise InvalidScientificProblem("HYBRID_INTERVAL is a conservative envelope and does not consume correlations")
        lower=upper=0.0
        for contribution in contributions:
            if contribution.uncertainty.kind is UncertaintyKind.INTERVAL:
                lo,hi=_interval_widths(contribution,nominal);lower+=lo;upper+=hi
            elif contribution.uncertainty.kind is UncertaintyKind.STANDARD:
                width=policy.standard_coverage_factor*_standard_magnitude(contribution,spread_unit)
                # Convert spread width into nominal units for asymmetric absolute endpoints.
                width=Quantity(width,spread_unit).magnitude_as_spread_in(nominal.units)
                lower+=width;upper+=width
            else:
                raise InvalidScientificProblem("HYBRID_INTERVAL accepts only STANDARD or INTERVAL records")
        assumptions.append(f"standard_components_expanded_by_declared_k={policy.standard_coverage_factor}")
        output=Uncertainty(kind=UncertaintyKind.INTERVAL,
            lower=Quantity(nominal.magnitude-lower,nominal.units),
            upper=Quantity(nominal.magnitude+upper,nominal.units),
            method="conservative hybrid interval envelope with explicit standard coverage factor",
            notes="; ".join(assumptions),source_kind=UncertaintySource.COMBINED)
    return CombinationReport(nominal,contributions,policy,correlations,output,tuple(assumptions))
