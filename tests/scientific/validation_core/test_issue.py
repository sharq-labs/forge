import pytest
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.validation_core import ValidationIssue, ValidationSeverity

def test_issue_requires_meaningful_identity():
    with pytest.raises(InvalidScientificProblem):
        ValidationIssue("", "x", ValidationSeverity.ERROR)
