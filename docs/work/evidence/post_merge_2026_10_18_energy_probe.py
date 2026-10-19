"""Source-extracted admission diagnostic, NOT an end-to-end M1C execution.
The M1C realization cannot currently be constructed. Do not bypass its guard.
Compile only the unchanged balance arithmetic/decision to assess its mathematics.
"""
import ast, math, json, hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
path=Path("src/engcore/domains/thermal_models/conduction1d_transient_fv.py")
source=path.read_bytes(); tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="TransientConduction1D")
step=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="_step")
start=next(i for i,n in enumerate(step.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="delta" for t in n.targets))
end=next(i for i in range(start,len(step.body)) if isinstance(step.body[i],ast.If))
block=ast.Module(body=step.body[start:end+1],type_ignores=[])
class Refusal(Exception):pass
compiled=compile(block,str(path),"exec")
results=[]
for cells in (4,32,128,256,512):
 n=cells+1;h=1/cells;capacity=np.full(n,h);capacity[[0,-1]]*=.5;g=np.full(cells,1/h);seconds=.1
 diag=capacity/seconds+np.r_[g,0]+np.r_[0,g]
 matrix=sp.diags((-g,diag,-g),(-1,0,1),format="csr")
 old=np.full(n,300.);new=old+1e-7;rhs=capacity/seconds*old
 local=capacity*(new-old)/seconds-(np.r_[0,g*(new[:-1]-new[1:])]-np.r_[g*(new[:-1]-new[1:]),0])
 env=dict(math=math,np=np,_BALANCE_ROUNDOFF_FACTOR=64,self=SimpleNamespace(_capacity=capacity,atol=1e-9,rtol=1e-6),old=old,new=new,seconds=seconds,boundary=[0.,0.],powers=np.zeros(n),matrix=matrix,rhs=rhs,local=local,NumericalRefusal=Refusal)
 try:exec(compiled,env);admitted=True
 except Refusal:admitted=False
 row_allowance=1e-8+1e-8*(abs(matrix)@abs(new)+abs(rhs))
 results.append(dict(cells=cells,delta_J=env['delta'],exchange_J=env['exchange'],floor_J=env['arithmetic'],allowance_J=env['allowance'],energy_admitted=admitted,row_admitted=bool(np.all(abs(matrix@new-rhs)<=row_allowance)),relative_residual=float(np.linalg.norm(matrix@new-rhs)/np.linalg.norm(rhs)),independent_equilibrium_floor_J=64*np.finfo(float).eps*(600+120*cells*cells)))
assert not results[0]['energy_admitted'] and results[-1]['energy_admitted']
print(json.dumps(dict(classification="SCIENTIFIC_CORRECTNESS_COUNTEREXAMPLE_TO_MESH_INDEPENDENT_ADMISSION; extracted arithmetic only; production realization unavailable",source_sha256=hashlib.sha256(source).hexdigest(),results=results),indent=2))
