import pytest
from engcore.uq.budget import *

def component(name): return UncertaintyComponent(name,UncertaintySource.PARAMETER,1.0)

def test_non_psd_correlation_matrix_is_refused_even_when_each_pair_is_in_range():
    components=(component("a"),component("b"),component("c"))
    correlations=(Correlation("a","b",-0.9),Correlation("a","c",-0.9),Correlation("b","c",-0.9))
    with pytest.raises(ValueError,match="positive-semidefinite"):
        aggregate_uncertainty(components,correlations)
