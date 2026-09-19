from __future__ import annotations

import hashlib

from ..serialization import to_json
from .report import ValidationReport


def validation_report_fingerprint(report: ValidationReport) -> str:
    if not isinstance(report, ValidationReport):
        raise TypeError("validation_report_fingerprint requires ValidationReport")
    return hashlib.sha256(to_json(report).encode("utf-8")).hexdigest()
