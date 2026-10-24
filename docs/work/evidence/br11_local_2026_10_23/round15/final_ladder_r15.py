from pathlib import Path
import subprocess
root=Path("/home/dev_kaeem/forge-r15-gate-final")
python="/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python"
runner="/home/dev_kaeem/br11-logs/run_r15_record.py"
def run(label,args):
    return subprocess.run(["python3",runner,label,str(root),python,*args]).returncode
run("regression_completed",["tools/forge_check.py","--regression","--workers","4"])
guards=["tests/mind","tests/test_blind_challenge_guards.py","tests/test_core_api_layering.py",
"tests/test_core_guards.py","tests/test_core_semantic_invariants.py","tests/test_repository_architecture.py",
*[str(p.relative_to(root)) for p in sorted(root.glob("tests/test_trust_boundary_*.py"))],
"tests/test_sria_m5_campaign.py","tests/test_sria_campaign_persistence_v03_adversarial.py","tests/test_sria_budget_ledger_identity.py"]
run("guards_completed",["-m","pytest",*guards,"-q","-n","4","-p","no:cacheprovider","-rfE"])
expensive=[
"benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_careful_identifies_synthetic_pulses_and_recovers_the_parameters",
"benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_mind_runs_end_to_end_on_synthetic_pulses_and_its_traces_replay",
"benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_no_arm_supports_identifiability_when_tau_is_far_outside_the_window",
"benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates",
"tests/domains/kinetics/test_cstr_domain.py","tests/systems/aerospace/test_multirotor_mvr0.py",
"tests/systems/aerospace/test_multirotor_mvr1.py","tests/test_electrical_v01_demo.py","tests/test_heterogeneous_ngspice.py",
"tests/test_sria_e1_electrical.py","tests/test_sria_e2_model_adequacy.py","tests/test_sria_e3_adequacy_obligation.py",
"tests/test_sria_v01_certification_path.py","tests/test_thermal_t1_fidelity_inference.py"]
run("expensive_completed",["-m","pytest",*expensive,"-m","expensive and not campaign","-q","-n","3","--dist","loadfile","-p","no:cacheprovider","-rfE"])


run("fast_clean_final",["-m","pytest","-q","-n","4","--dist","loadfile","-m","not expensive","-p","no:cacheprovider","-rfE"])
