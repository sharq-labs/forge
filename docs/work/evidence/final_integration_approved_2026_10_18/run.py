import datetime,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
root=Path('D:/forge-main-337519d1');task=root/'.pytest-review-temp/final-integration-approved-2026-10-18'
job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));name=job['id']
if (task/(name+'.json')).exists():raise RuntimeError('Refuse overwriting completed job '+name)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(label):
    paths=[p for area in ('src','tests','tools') for p in (root/area).rglob('*.py') if '__pycache__' not in p.parts]
    paths += list((root/'certification').rglob('*.json'))
    paths += [root/'docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md',root/'docs/project/scientific_capability_completion.json',root/'docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md',root/'docs/CORE_FREEZE_POLICY.md']
    files={p.relative_to(root).as_posix():digest(p) for p in sorted(set(paths))}
    encoded=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    index=task/(name+'-source-'+label+'.json');index.write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
    return {'index':str(index),'sha256':hashlib.sha256(encoded).hexdigest(),'files':len(files)},files
before,files_before=snapshot('before')
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(root/'src')+os.pathsep+str(root)+os.pathsep+str(root/'tests/claims'),PYTEST_ADDOPTS='--basetemp='+(task/(name+'-temp')).as_posix())
if job.get('bootstrap',True):env['PYTHONPATH']=str(task/'bootstrap')+os.pathsep+env['PYTHONPATH']
python=job.get('python','C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe')
args=[python]+job['args'];log=task/(name+'.log')
start=time.monotonic();start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
with log.open('w',encoding='utf-8') as f:
    try:
        p=subprocess.run(args,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=job.get('timeout',300));code=p.returncode;status='EXECUTED'
    except subprocess.TimeoutExpired:code=None;status='BLOCKED_TIMEOUT'
seconds=time.monotonic()-start
after,files_after=snapshot('after')
output=log.read_text(encoding='utf-8',errors='replace')
summary=[line for line in output.splitlines() if re.search(r'\d+ (passed|failed|errors?|skipped)',line) and not line.startswith('E ')][-1:]
record=dict(id=name,argv=args,command=subprocess.list2cmdline(args),cwd=str(root),started_utc=start_utc,seconds=seconds,timeout=job.get('timeout',300),exit_code=code,status=status,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),working_state=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=root,text=True),environment={k:env[k] for k in ('PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','PYTHONPATH','PYTEST_ADDOPTS')},source_before=before,source_after=after,source_unchanged=files_before==files_after,source_changes=[p for p in set(files_before)|set(files_after) if files_before.get(p)!=files_after.get(p)],log=str(log),log_sha256=digest(log),summary=summary,failure_names=[line for line in output.splitlines() if line.startswith(('FAILED ','ERROR '))],resource_usage='Wall time measured. Child CPU/RSS not measured; no attribution to Fraction or setup is inferred.')
record['counts']={k:sum(int(v) for v in re.findall(r'(\d+) '+k+r'\b','; '.join(summary))) for k in ('passed','failed','skipped','errors')}
(task/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
with (root/'docs/work/PROGRESS.md').open('a',encoding='utf-8') as f:
    f.write('\n\n### Approved final integration / '+name+' / 2026-10-18\n- Exact command: `'+record['command']+'`\n- Result: '+status+', exit'+str(code)+', '+str(round(seconds,3))+'s wall; '+'; '.join(summary)+'; source unchanged='+str(record['source_unchanged'])+'. Source HEAD '+record['head']+' plus working patch; before/after source indexes, environment, counts, state, log SHA256: '+str(task/(name+'.json'))+'.\n- Failures/errors: '+(' | '.join(record['failure_names']) or 'none reported; non-pytest diagnostics require log interpretation')+'.\n')
print(json.dumps({k:record[k] for k in ('id','status','exit_code','seconds','summary','failure_names','source_unchanged')},indent=2),flush=True)
if not summary:print(output[-5000:],flush=True)
