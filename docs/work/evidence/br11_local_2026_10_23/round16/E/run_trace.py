import pathlib, subprocess,sys,json,os
out=pathlib.Path('/home/dev_kaeem/br11-review/r16/E')
root=pathlib.Path('/home/dev_kaeem/forge-r16-review')
cmd=[sys.executable,str(out/'trace_repro.py')]
r=subprocess.run(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(out/'trace_repro.log').write_text(r.stdout)
(out/'trace_execution.json').write_text(json.dumps({'command':' '.join(cmd),'cwd':str(root),'exit':r.returncode,'env':{'PYTHONPATH':os.environ['PYTHONPATH'],'PYTHONDONTWRITEBYTECODE':os.environ['PYTHONDONTWRITEBYTECODE']},'log':str(out/'trace_repro.log')},indent=2))
print(r.stdout);sys.exit(r.returncode)
