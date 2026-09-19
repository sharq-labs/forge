import hashlib,json
from .report import CombinationReport
from .serialization import report_to_dict

def combined_uq_fingerprint(report:CombinationReport)->str:
    return hashlib.sha256(json.dumps(report_to_dict(report),sort_keys=True,separators=(",",":")).encode()).hexdigest()
