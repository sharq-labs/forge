"""Executed exact-kernel analysis, not an end-to-end solver or validation."""
from pathlib import Path
import ast, hashlib, json, statistics, time
from fractions import Fraction
from decimal import Decimal, localcontext
from types import SimpleNamespace
import numpy as np
source=Path("src/engcore/domains/thermal_models/conduction1d_transient_fv.py").read_bytes()
tree=ast.parse(source); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="TransientConduction1D"); method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="_step")
start=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="f" for t in n.targets))
end=next(i for i in range(start,len(method.body)) if isinstance(method.body[i],ast.Assign) and any(isinstance(t,ast.Name) and t.id=="exact_allowance" for t in method.body[i].targets))
code=compile(ast.Module(body=method.body[start:end+1],type_ignores=[]),"<exact production kernel>","exec")
def evaluate(capacity,old,new,dt,boundary,powers):
 env=dict(Fraction=Fraction,self=SimpleNamespace(_capacity=capacity,atol=1e-9,rtol=1e-6),old=old,new=new,seconds=dt,boundary=boundary,powers=powers)
 exec(code,env);return env
cases=[("subnormal",[.5,.5],[5e-324]*2,[1e-323]*2,5e-324,[0.,0.],[0.,0.]),("normal",[.2,.3,.5],[300.,340.,290.],[300.1,339.9,290.02],.1,[2.,-.5],[1.,-1.,.2]),("huge_finite",[1e100,1e100],[1e100]*2,[1e100,1e100+1e85],1e100,[1e100,-1e100],[1e100,0.])]
references=[]
for name,c,a,b,dt,bd,p in cases:
 env=evaluate(c,a,b,dt,bd,p)
 with localcontext() as ctx:
  ctx.prec=4000
  d=lambda x:Decimal.from_float(float(x))
  changes=[d(ci)*(d(bi)-d(ai)) for ci,ai,bi in zip(c,a,b)]
  delta=sum(changes,Decimal(0));boundary=d(dt)*sum(map(d,bd),Decimal(0));power=d(dt)*sum(map(d,p),Decimal(0));balance=delta-boundary-power
  exchange=max(sum(map(abs,changes),Decimal(0)),d(dt)*(sum((abs(d(x)) for x in bd),Decimal(0))+sum((abs(d(x)) for x in p),Decimal(0))))
  allow=d(1e-9)+d(1e-6)*exchange
  assert Fraction(balance)==env["exact_balance"]
  assert Fraction(exchange)==env["exact_exchange"]
  assert Fraction(allow)==env["exact_allowance"]
 references.append(dict(case=name,exact_decimal_agreement=True,admitted=abs(env['exact_balance'])<=env['exact_allowance']))
cost=[]
for n in (4,512,8192):
 c=np.full(n,1/n);a=np.full(n,300.);b=a+1e-7;p=np.zeros(n);samples=[]
 for repeat in range(5):
  start=time.perf_counter();env=evaluate(c,a,b,.1,[0.,0.],p);samples.append(time.perf_counter()-start)
 assert abs(env['exact_balance'])>env['exact_allowance']
 cost.append(dict(entries=n,median_seconds=statistics.median(samples),max_seconds=max(samples),repeats=5))
print(json.dumps(dict(source_sha256=hashlib.sha256(source).hexdigest(),classification="exact production kernel versus independent Decimal arithmetic; no solve/physical validation",references=references,cost=cost),indent=2))
