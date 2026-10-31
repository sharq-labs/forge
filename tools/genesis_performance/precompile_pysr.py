"""Trace the PySR bridge using only analytic synthetic arrays; never import Forge."""
import json
import pathlib
import sys
import tempfile
import time

import numpy as np
from pysr import PySRRegressor
from pysr.julia_import import jl

output=pathlib.Path(sys.argv[1])
jl.seval('Base.cumulative_compile_timing(true)')
rows=[]
for units in (False, True):
    x=np.linspace(1.0,3.0,32)
    X=np.column_stack((x,1.0+np.sin(x)**2))
    y=np.log(2.0+X[:,0]/X[:,1]) if units else 2.0+X[:,0]/X[:,1]
    with tempfile.TemporaryDirectory(prefix='public-pysr-trace-') as scratch:
        model=PySRRegressor(niterations=40,populations=8,population_size=33,maxsize=20 if units else 15,
            binary_operators=['+','-','*','/'],unary_operators=['exp','log'],deterministic=True,
            parallelism='serial',random_state=0,progress=False,verbosity=0,output_directory=scratch)
        before=list(jl.seval('Base.cumulative_compile_time_ns()'))
        started=time.perf_counter()
        model.fit(X,y,variable_names=['x0','x1'],**({'X_units':['m','m'],'y_units':'1'} if units else {}))
        elapsed=time.perf_counter()-started
        after=list(jl.seval('Base.cumulative_compile_time_ns()'))
        front=[(int(r['complexity']),float(r['loss']),str(r['sympy_format'])) for _,r in model.equations_.iterrows()]
        rows.append({'units':units,'fit_s':elapsed,'compile_ns_delta':[a-b for a,b in zip(after,before)],'equations':front})
output.write_text(json.dumps({'label':'PUBLIC_SYNTHETIC_TRACE_NOT_THROUGHPUT','rows':rows},indent=2))
print(json.dumps({'rows':[{k:v for k,v in r.items() if k!='equations'} for r in rows]}))
