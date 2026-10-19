"""Read-only current-record reproduction; no archive behavior is changed."""
import hashlib,json
from engcore.domains.thermal.conduction1d.problem import DIFFUSION_MODEL
from engcore.domains.thermal_models.conduction1d_transient_fv import MODEL as M1C_MODEL
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.models.registry import ModelRegistry
records=[]
for model in (DIFFUSION_MODEL,M1C_MODEL):
    payload=model.to_dict()
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    row={'model_key':list(model.key),'schema':payload['schema'],'exclusions':payload['exclusions'],'payload_sha256':hashlib.sha256(canonical).hexdigest(),'payload':payload}
    for label,read in (('model_read',lambda:ScientificModelDefinition.from_dict(payload)),('registry_read',lambda:ModelRegistry.from_dict(ModelRegistry((model,)).to_dict()))):
        try:
            value=read()
            row[label]={'outcome':'READ_SUCCEEDED','type':type(value).__name__}
        except Exception as exc:
            row[label]={'outcome':'REFUSED','error_type':type(exc).__name__,'error':str(exc)}
    records.append(row)
print(json.dumps({'status':'DIAGNOSTIC_COMPLETED_NOT_A_COMPATIBILITY_PASS','records':records,'classification':'UNCLASSIFIED scientific impact; dependent archive/registry readback claims blocked. No behavior repaired.'},indent=2))
