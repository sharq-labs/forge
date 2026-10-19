"""Read-only discovery/registry inventory, not pytest or scientific validation."""
import platform
platform._wmi = None  # process-local fallback independently established in P0 evidence
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

root=Path('D:/forge-main-337519d1')
spec=importlib.util.spec_from_file_location('owner_census_guard_probe',root/'tests/test_core_guards.py')
guard=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=guard
spec.loader.exec_module(guard)
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.models.registry import ModelRegistry
from engcore.scientific.realizations.definition import ModelRealizationDefinition
from engcore.scientific.realizations.registry import RealizationRegistry

def serial_hash(record):
    return hashlib.sha256(json.dumps(record.to_dict(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

models={}
realizations={}
for name,module in tuple(sys.modules.items()):
    if not name.startswith('engcore.') or module is None:
        continue
    for attribute,value in vars(module).items():
        group=models if isinstance(value,ScientificModelDefinition) else realizations if isinstance(value,ModelRealizationDefinition) else None
        if group is not None:
            identity=value.key
            entry=group.setdefault(identity,{})
            obj=entry.setdefault(id(value),{'record':value,'aliases':[]})
            obj['aliases'].append(name+':'+attribute)

rows=[]
for key,objects in sorted(models.items()):
    first=next(iter(objects.values()))['record']
    rows.append({'key':list(key),'record':first.to_dict(),'object_count':len(objects),
        'distinct_serialized_hashes':sorted({serial_hash(v['record']) for v in objects.values()}),
        'aliases':sorted(a for v in objects.values() for a in v['aliases'])})
registry=ModelRegistry(guard.MODELS)
serialized=registry.to_dict()
try:
    roundtrip_equal=ModelRegistry.from_dict(serialized).to_dict()==serialized
    roundtrip_error=None
except Exception as exc:
    roundtrip_equal=False
    roundtrip_error=type(exc).__name__+': '+str(exc)
model_reader_errors=[]
for m in guard.MODELS:
    try:
        ScientificModelDefinition.from_dict(m.to_dict())
    except Exception as exc:
        model_reader_errors.append({'key':list(m.key),'error':type(exc).__name__+': '+str(exc)})
rr=RealizationRegistry(tuple(next(iter(v.values()))['record'] for _,v in sorted(realizations.items())))
realization_rows=[{'key':list(k),'record':next(iter(v.values()))['record'].to_dict(),
    'distinct_serialized_hashes':sorted({serial_hash(o['record']) for o in v.values()}),
    'aliases':sorted(a for o in v.values() for a in o['aliases'])} for k,v in sorted(realizations.items())]

historical_revision=subprocess.check_output(['git','rev-parse','89b9e7c3'],cwd=root,text=True).strip()
historical_paths=subprocess.check_output(['git','grep','-l','ScientificModelDefinition(',historical_revision,'--','src/engcore'],cwd=root,text=True).splitlines()
historical=[]
for qualified in historical_paths:
    path=qualified.split(':',1)[1]
    source=subprocess.check_output(['git','show',historical_revision+':'+path],cwd=root,text=True)
    tree=ast.parse(source)
    bindings={}
    def literal(node):
        if isinstance(node,ast.Constant):return node.value
        if isinstance(node,ast.Name):return bindings.get(node.id)
        return None
    for assignment in tree.body:
        value=assignment.value if isinstance(assignment,(ast.Assign,ast.AnnAssign)) else None
        if isinstance(assignment,ast.Assign):
            for target in assignment.targets:
                if isinstance(target,ast.Name) and literal(value) is not None:bindings[target.id]=literal(value)
        if not isinstance(value,ast.Call):
            continue
        func=value.func
        if not isinstance(func,ast.Name) or func.id!='ScientificModelDefinition':
            continue
        fields={k.arg:k.value for k in value.keywords}
        if all(literal(fields.get(k)) is not None for k in ('model_id','version')):
            historical.append({'key':[literal(fields['model_id']),literal(fields['version'])],'path':path,'line':assignment.lineno})
current_keys={tuple(r['key']) for r in rows}
old_keys={tuple(r['key']) for r in historical}
output={'purpose':'Read-only owner-decision inventory; no test functions invoked','head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    'python':sys.version,'executable':sys.executable,'engcore_path':sys.modules['engcore'].__file__,
    'versions':{n:importlib.metadata.version(n) for n in ('numpy','scipy','pint','pytest','mcp')},
    'model_discovery_failures':guard.MODEL_DISCOVERY_FAILURES,'optional_absences':guard.OPTIONAL_DEPENDENCY_ABSENCES,
    'observed_models':len(guard.MODELS),'unique_current_model_keys':len(models),'models':rows,
    'reserving_count':len(guard.RESERVING),'condition_names':sum(len(m.validity.context_keys) for m in guard.MODELS),
    'reserved_names':sum(len(m.derived_quantities) for m in guard.MODELS),
    'model_registry_roundtrip_equal':roundtrip_equal,'model_registry_roundtrip_error':roundtrip_error,
    'individual_model_reader_errors':model_reader_errors,
    'model_registry_identity_lookup_equal':all(registry.get(*m.key) is m for m in guard.MODELS),
    'realizations':realization_rows,'realization_registry_constructed':True,
    'historical_revision':historical_revision,'historical_literal_module_models':sorted(historical,key=lambda x:x['key']),
    'historical_count':len(old_keys),'added_keys':sorted([list(k) for k in current_keys-old_keys]),
    'removed_keys':sorted([list(k) for k in old_keys-current_keys])}
print(json.dumps(output,indent=2))
