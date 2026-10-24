"""Lens A r10: does the plain-data read-back refuse an honest experiment the scientific core produces?
Build experiments with full evaluations (results with validity, validation, constraint checks) from the core's own
test helpers, and read them through a static and a following BudgetReader."""
import json, sys
import tests.test_core_scientific_audit_batch43 as B43
import tests.test_scientific_core as C
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners as ow
from engcore.scientific.experiments import EvaluationStatus, ExperimentBudget, ScientificExperiment
from engcore.scientific.results.validation import unverified_report

cases = {}
e1 = ScientificExperiment("exp-rich-1", C.build_algebraic_problem(), ExperimentBudget(max_observations=9))
for i, load in enumerate((5.0, 3.0, 2.5), 1):
    e1.record(C._evaluation(i, load, assessed=True))
e1.record(C._evaluation(4, 1.0, status=EvaluationStatus.FAILED))
cases["core_assessed_and_failed"] = e1
cases["batch43_validation"] = B43._experiment(B43._evaluation(1, 2.0, validation=unverified_report()),
                                              B43._evaluation(2, 3.0))
e3 = ScientificExperiment("exp-meta", C.build_algebraic_problem(), ExperimentBudget(max_observations=3),
                          metadata={"campaign": "c1", "tags": ("a", "b"), "seed": 7, "ratio": 0.5, "flag": None})
e3.record(C._evaluation(1, 4.0))
cases["tuple_metadata"] = e3
plain_fn = getattr(ow, "_plain", None)
for name, exp in cases.items():
    d = exp.to_dict()
    plain = plain_fn(d) if plain_fn else "n/a"
    bad = []
    def walk(x, path):
        t = type(x)
        if t is dict:
            for k, v in x.items():
                if type(k) is not str: bad.append((path, "key", type(k).__name__))
                walk(v, f"{path}.{k}")
        elif t in (list, tuple):
            for i, v in enumerate(x): walk(v, f"{path}[{i}]")
        elif t not in (str, int, float, bool, type(None)):
            bad.append((path, t.__name__))
    walk(d, "")
    out = []
    for label, reader in (("static", BudgetReader({}, {exp.experiment_id: exp})),
                          ("following", None)):
        try:
            if reader is None:
                reader = BudgetReader.following(lambda exp=exp: ({}, {exp.experiment_id: exp}))
            r = reader.read(OwnerKind.EXPERIMENT, exp.experiment_id)
            back = ScientificExperiment.from_dict(r.payload["experiment"])
            out.append(f"{label}: READ rev={r.revision} digest_roundtrip={ow._sha_json(back) == r.record_digest}")
        except Exception as exc:
            out.append(f"{label}: REFUSED {type(exc).__name__}: {str(exc)[:160]}")
    print(name, "plain:", plain, "non-plain:", bad[:5])
    for o in out:
        print("   ", o)
