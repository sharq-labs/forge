from __future__ import annotations

import numpy as np

from .component import UncertaintyComponent
from .correlation import Correlation


def correlation_matrix(
    components:tuple[UncertaintyComponent,...],
    correlations:tuple[Correlation,...]=(),
)->np.ndarray:
    ids=[c.component_id for c in components]
    if len(ids)!=len(set(ids)):
        raise ValueError("duplicate uncertainty component id")
    index={name:i for i,name in enumerate(ids)}
    matrix=np.eye(len(ids),dtype=float)
    seen=set()
    for item in correlations:
        if item.left_id not in index or item.right_id not in index:
            raise ValueError("correlation references unknown uncertainty component")
        if item.key in seen:
            raise ValueError("duplicate correlation pair")
        seen.add(item.key)
        i,j=index[item.left_id],index[item.right_id]
        matrix[i,j]=matrix[j,i]=item.coefficient
    return matrix


def require_positive_semidefinite_correlation(
    components:tuple[UncertaintyComponent,...],
    correlations:tuple[Correlation,...]=(),
    *,
    tolerance:float=1e-12,
)->np.ndarray:
    matrix=correlation_matrix(components,correlations)
    if matrix.size==0:
        return matrix
    eigenvalues=np.linalg.eigvalsh(matrix)
    if float(eigenvalues.min()) < -abs(float(tolerance)):
        raise ValueError(
            "declared uncertainty correlations do not form a positive-semidefinite correlation matrix"
        )
    return matrix
