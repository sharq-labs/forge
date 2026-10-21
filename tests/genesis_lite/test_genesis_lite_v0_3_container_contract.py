"""Failing-first proposed evidence contract; synthetic data is not runtime proof.

A PASS baseline describes three separate complete cards. Policy mutants keep raw,
parsed and runtime mount representations synchronized; mismatch mutants do not.
No implementation of the production validator is supplied by these tests.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from benchmarks.genesis_lite.v0_3 import isolation

spec=importlib.util.spec_from_file_location("cp2_probe",Path(__file__).with_name("container_isolation_probe.py"))
probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
PRIVATE=["/tmp","/var/tmp","/run","/dev/shm"]
CAPS=["CapInh","CapPrm","CapEff","CapBnd","CapAmb"]
IMAGE="sha256:89847920916e46363fe52f7cecc3a2b937d34d6b355dd3e8cc14527fe65a8261"


def escape(s):
    return s.replace("\\","\\134").replace(" ","\\040").replace("\t","\\011").replace("\n","\\012")


def raw_mounts(rows):
    return "".join(" ".join([r["id"],r["parent"],r["device"],escape(r["root"]),escape(r["target"]),
                            ",".join(r["options"]),*r["optional"],"-",r["fstype"],escape(r["source"]),
                            ",".join(r["super_options"])])+"\n" for r in rows)


def synchronize(card):
    card["mountinfo"]=raw_mounts(card["mounts"])
    card["runtime_mounts"]=[{k:copy.deepcopy(r[k]) for k in
                             ("id","parent","device","root","target","fstype","source","options","optional")}
                            |dict(private=not r["optional"],backing=("host" if r["target"] in
                                  ("/source","/venv") else "container")) for r in card["mounts"]]


def baseline():
    expected=dict(source_sha="1"*40,image_digest=IMAGE,image_id="2"*64,
                  podman_version="4.9.3",containerfile_sha256="3"*64,
                  launcher_sha256="4"*64,probe_sha256="5"*64,
                  writable_targets=PRIVATE,source_host="/repo",venv_host="/venv-host",
                  source_path="/source",venv_path="/venv",rootless=True)
    cards=[]
    for n,phase in enumerate(["A","B","C"]):
        offset=100*n
        targets=[("/","overlay","ro"),("/proc","proc","ro"),("/source","ext4","ro"),
                 ("/venv","ext4","ro"),*[(t,"tmpfs","rw") for t in PRIVATE]]
        rows=[dict(id=str(offset+i+1),parent=str(offset+1 if i else 0),device=f"0:{i+1}",
                   root="/",target=t,options=[mode,"nosuid","nodev"],optional=[],fstype=fs,
                   source=fs,super_options=["rw"]) for i,(t,fs,mode) in enumerate(targets)]
        # ro mount + rw superblock is a valid read-only view, including bind views.
        rows[2]["root"]="/repository"; rows[3]["root"]="/python-env"
        argv=["podman","create","--pull=never","--rm","--read-only","--read-only-tmpfs=false",
              "--security-opt=proc-opts=ro,nosuid,nodev,noexec","--ipc=private","--network=none",
              "--cap-drop=ALL","--security-opt=no-new-privileges","--userns=keep-id"]
        for t in PRIVATE: argv += ["--tmpfs",t+":rw,nosuid,nodev,mode=1777"]
        paths=dict(HOME="/tmp/home",TMPDIR="/tmp",XDG_CACHE_HOME="/tmp/cache",PYTHONPYCACHEPREFIX="/tmp/pycache")
        argv += ["--volume","/repo:/source:ro","--volume","/venv-host:/venv:ro","--workdir","/tmp"]
        for k,v in paths.items(): argv += ["--env",k+"="+v]
        argv += ["localhost/forge-card@"+IMAGE,"python3","probe.py"]
        canaries=[]
        for i,t in enumerate(PRIVATE):
            mid=rows[4+i]["id"]
            token=(str(i+6)*64)  # distinct fixed fixture tokens, actual runtime uses secrets
            canaries.append(dict(target=t,path=t+"/cp2-token",token=token,actual_mount=mid,
                                  expected_mount=mid,read="READ_ABSENT",write="WRITE_OK" if phase=="A" else "NOT_ATTEMPTED",
                                  readback=token if phase=="A" else None,write_mount=mid if phase=="A" else None,
                                  readback_mount=mid if phase=="A" else None))
        card=dict(phase=phase,id=chr(97+n)*64,provenance=copy.deepcopy(expected),mounts=rows,
                  argv=argv,paths=paths|dict(workdir="/tmp"),status={k:"0" for k in CAPS}|dict(NoNewPrivs="1"),
                  actual_image_digest=IMAGE,actual_image_id=expected["image_id"],ipc="private",
                  network=dict(host_listener="REFUSED",external="REFUSED",interfaces=["lo"]),
                  writes=dict(source="READ_ONLY",venv="READ_ONLY"),canaries=canaries,
                  restart=dict(attempted=True,refused=True,exit_code=125),removed=True,
                  # MINOR-A (D5-A1b): PID 1 of its own PID namespace through its own /proc; not the host's devices
                  pid_namespace=dict(pid=1,nspid=["1"],ns=f"pid:[{4026532300+n}]",visible_processes=1),
                  host_devices=dict(proc="0:59",sys="0:22",pid_ns="pid:[4026532219]"))
        synchronize(card); cards.append(card)
    report=dict(schema="checkpoint2.container_evidence.contract/2",cards=cards,
                positive_controls=dict(host_listener="REACHED",shared_canary=dict(
                    a_write="WRITE_OK",a_token="e"*64,b_read="READ_OK",b_seen="e"*64,
                    a_mount="900",b_mount="901",a_actual="900",b_actual="901",
                    a_id="d"*64,b_id="e"*64,a_path="/shared/cp2-control",
                    b_path="/shared/cp2-control",a_image_digest=IMAGE,b_image_digest=IMAGE),
                host_procfs=dict(pid=1,nspid=["22255","1"],ns="pid:[4026532219]",visible_processes=31,id="f"*64)))
    return report,expected


def validator():
    fn=getattr(isolation,"validate_container_evidence",None)
    assert callable(fn), "MISSING_VALIDATION_CONTRACT: validate_container_evidence(report, expected=...)"
    return fn


def test_complete_per_card_evidence_accepted():
    report,expected=baseline()
    assert validator()(report,expected=expected)==dict(status="PASS",reasons=[])


def test_escaped_readonly_bind_alias_is_admissible():
    report, expected = baseline()
    for card in report["cards"]:
        row = copy.deepcopy(card["mounts"][2])
        row.update(id=str(int(card["mounts"][-1]["id"])+1),
                   root="/repository/sub dir", target="/read only\talias\\")
        card["mounts"].append(row)
        synchronize(card)
        card["runtime_mounts"][-1]["backing"] = "host"
        image_index = card["argv"].index("localhost/forge-card@" + IMAGE)
        card["argv"][image_index:image_index] = ["--volume", "/repo/sub dir:/read only\talias\\:ro"]
        assert probe.parse_mountinfo(card["mountinfo"]) == card["mounts"]
    assert validator()(report, expected=expected) == dict(status="PASS", reasons=[])


@pytest.mark.parametrize("raw", ["bad row\n", "1 0 0:1 / / ro - tmpfs\n",
                                "1 0 0:1 / / ro - tmpfs tmpfs rw\n"*2])
def test_validator_rejects_malformed_raw_inventory(raw):
    report, expected = baseline()
    report["cards"][0]["mountinfo"] = raw
    result = validator()(report, expected=expected)
    assert result["status"] == "BLOCKED" and "MOUNT_INVENTORY_MISMATCH" in result["reasons"]


MUTATIONS=[
 ("empty","EVIDENCE_INCOMPLETE"),("schema","SCHEMA_MISMATCH"),("missing_card","EVIDENCE_INCOMPLETE"),
 ("missing_field","EVIDENCE_INCOMPLETE"),("empty_inventory","MOUNT_INVENTORY_MISMATCH"),
 ("parsed_missing","MOUNT_INVENTORY_MISMATCH"),("raw_missing","MOUNT_INVENTORY_MISMATCH"),
 ("runtime_missing","MOUNT_INVENTORY_MISMATCH"),("parsed_spoof","MOUNT_INVENTORY_MISMATCH"),
 ("runtime_spoof","MOUNT_INVENTORY_MISMATCH"),("duplicate_id","MOUNT_INVENTORY_MISMATCH"),
 ("windows","WINDOWS_WRITABLE_MOUNT"),("host","HOST_WRITABLE_MOUNT"),
 ("shared","SHARED_WRITABLE_MOUNT"),("undeclared","UNDECLARED_WRITABLE_MOUNT"),
 ("unprobeable","UNPROBEABLE_WRITABLE_MOUNT"),("image","IMAGE_DIGEST_MISMATCH"),
 ("image_id","IMAGE_ID_MISMATCH"),("reuse","CONTAINER_REUSED"),
 ("source_rw","SOURCE_WRITABLE"),("venv_rw","VENV_WRITABLE"),
 ("caps","NONZERO_CAPABILITIES"),("nnp","NO_NEW_PRIVILEGES_MISSING"),
 ("network","NETWORK_REACHED"),("ipc","IPC_NOT_PRIVATE"),("home","PATH_OUTSIDE_PRIVATE_MOUNTS"),
 ("cache","PATH_OUTSIDE_PRIVATE_MOUNTS"),("canary_seen","CROSS_CARD_CANARY_REACHED"),
 ("missing_canary","CANARY_COVERAGE_INCOMPLETE"),("read_error","CANARY_READ_ERROR"),
 ("unknown_read","CANARY_COVERAGE_INCOMPLETE"),
 ("not_probed","CANARY_COVERAGE_INCOMPLETE"),("write_failed","CANARY_WRITE_FAILED"),
 ("bad_readback","CANARY_WRITE_FAILED"),("wrong_mount","CANARY_MOUNT_MISMATCH"),
 ("wrong_path","CANARY_PATH_MISMATCH"),("wrong_token","CANARY_TOKEN_MISMATCH"),
 ("shared_control","CANARY_CONTROL_FAILED"),("host_control","NETWORK_CONTROL_FAILED"),
 ("control_missing_id","CANARY_CONTROL_IDENTITY_MISSING"),
 ("control_reused_id","CANARY_CONTROL_IDENTITY_REUSED"),
 ("control_wrong_path","CANARY_CONTROL_PATH_MISMATCH"),
 ("control_wrong_image","CANARY_CONTROL_IMAGE_MISMATCH"),
 ("restart_succeeded","RESTART_NOT_REFUSED"),("restart_unattempted","RESTART_NOT_REFUSED"),
 ("not_removed","CONTAINER_NOT_REMOVED"),("missing_tmpfs","RUNTIME_CONFIGURATION_MISMATCH"),
 ("missing_env","RUNTIME_CONFIGURATION_MISMATCH"),("bind_rw","RUNTIME_CONFIGURATION_MISMATCH"),
 ("stacked_rw","OBSCURED_WRITABLE_MOUNT"),("nested_overmount","CANARY_MOUNT_MISMATCH"),
 ("bind_alias","UNDECLARED_WRITABLE_MOUNT"),
 *[("provenance_"+k,"PROVENANCE_MISMATCH") for k in
   ("source_sha","podman_version","containerfile_sha256","launcher_sha256","probe_sha256",
    "rootless","image_digest","image_id","source_host","venv_host","source_path","venv_path")]]


def mutate(report,expected,name):
    a,b,c=report["cards"]; row=a["mounts"][4]
    if name=="empty": report.clear()
    elif name=="schema": report["schema"]="unknown"
    elif name=="missing_card": report["cards"].pop()
    elif name=="missing_field": del c["status"]
    elif name=="empty_inventory": a["mounts"]=[]; synchronize(a)
    elif name=="parsed_missing": a["mounts"].pop()
    elif name=="raw_missing": a["mountinfo"]="\n".join(a["mountinfo"].splitlines()[:-1])+"\n"
    elif name=="runtime_missing": a["runtime_mounts"].pop()
    elif name=="parsed_spoof": row["fstype"]="9p"
    elif name=="runtime_spoof": a["runtime_mounts"][4]["options"]=["ro"]
    elif name=="duplicate_id": a["mounts"].append(copy.deepcopy(row)); synchronize(a)
    elif name=="windows":
        row.update(fstype="9p",source="C:"); synchronize(a)
        a["runtime_mounts"][4]["backing"]="windows"
        idx=a["argv"].index("--tmpfs"); a["argv"][idx:idx+2]=["--volume","/mnt/c:/tmp:rw"]
    elif name=="host":
        row.update(root="/host/cache",fstype="ext4",source="/dev/sda1"); synchronize(a)
        a["runtime_mounts"][4]["backing"]="host"
        idx=a["argv"].index("--tmpfs"); a["argv"][idx:idx+2]=["--volume","/host/cache:/tmp:rw"]
    elif name=="shared":
        row.update(optional=["shared:42"],root="/host/shared",fstype="ext4",source="/dev/sda1")
        synchronize(a); a["runtime_mounts"][4]["backing"]="host"
        idx=a["argv"].index("--tmpfs"); a["argv"][idx:idx+2]=["--volume","/host/shared:/tmp:rw,rshared"]
    elif name=="undeclared": expected["writable_targets"]=["/tmp"]
    elif name=="unprobeable": a["canaries"][0]["read"]="UNPROBEABLE"
    elif name=="image": a["actual_image_digest"]="sha256:"+"0"*64
    elif name=="image_id": a["actual_image_id"]="0"*64
    elif name=="reuse": b["id"]=a["id"]
    elif name in ("source_rw","venv_rw"):
        label=name.split("_")[0]; a["writes"][label]="WRITABLE"
        target="/"+label
        for r in a["mounts"]:
            if r["target"]==target: r["options"]=["rw"]
        synchronize(a)
        old="/repo:/source:ro" if label=="source" else "/venv-host:/venv:ro"
        a["argv"][a["argv"].index(old)]=old[:-2]+"rw"
    elif name=="caps": c["status"]["CapEff"]="1"
    elif name=="nnp": c["status"]["NoNewPrivs"]="0"
    elif name=="network": b["network"]["host_listener"]="REACHED"
    elif name=="ipc": a["ipc"]="shareable"; a["argv"][a["argv"].index("--ipc=private")]="--ipc=shareable"
    elif name in ("home","cache"):
        key="HOME" if name=="home" else "XDG_CACHE_HOME"
        old=a["paths"][key]; a["paths"][key]="/host-cache"
        a["argv"][a["argv"].index(key+"="+old)]=key+"=/host-cache"
    elif name=="canary_seen": b["canaries"][0].update(read="READ_OK",seen=a["canaries"][0]["token"])
    elif name=="missing_canary": c["canaries"].pop()
    elif name=="read_error": b["canaries"][0].update(read="READ_ERROR",error="EACCES")
    elif name=="unknown_read": b["canaries"][0]["read"]="UNKNOWN"
    elif name=="not_probed": b["canaries"][0]["read"]="NOT_PROBED"
    elif name=="write_failed": a["canaries"][0]["write"]="WRITE_ERROR"
    elif name=="bad_readback": a["canaries"][0]["readback"]="0"*64
    elif name=="wrong_mount": b["canaries"][0]["actual_mount"]="999"
    elif name=="wrong_path": b["canaries"][0]["path"]="/tmp/other-token"
    elif name=="wrong_token": b["canaries"][0]["token"]="0"*64
    elif name=="shared_control": report["positive_controls"]["shared_canary"]["b_read"]="READ_ABSENT"
    elif name=="control_missing_id": del report["positive_controls"]["shared_canary"]["a_id"]
    elif name=="control_reused_id":
        control=report["positive_controls"]["shared_canary"]; control["b_id"]=control["a_id"]
    elif name=="control_wrong_path": report["positive_controls"]["shared_canary"]["b_path"]="/shared/other"
    elif name=="control_wrong_image": report["positive_controls"]["shared_canary"]["b_image_digest"]="sha256:"+"0"*64
    elif name=="host_control": report["positive_controls"]["host_listener"]="REFUSED"
    elif name=="restart_succeeded": c["restart"].update(refused=False,exit_code=0)
    elif name=="restart_unattempted": c["restart"]["attempted"]=False
    elif name=="not_removed": c["removed"]=False
    elif name=="missing_tmpfs": idx=a["argv"].index("--tmpfs"); del a["argv"][idx:idx+2]
    elif name=="missing_env": idx=a["argv"].index("--env"); del a["argv"][idx:idx+2]
    elif name=="bind_rw": a["argv"][a["argv"].index("/repo:/source:ro")]="/repo:/source:rw"
    elif name in ("stacked_rw","nested_overmount","bind_alias"):
        added=copy.deepcopy(row); added.update(id="99",parent=row["id"])
        if name=="nested_overmount": added["target"]="/tmp/cp2-token"
        elif name=="bind_alias": added.update(target="/alias",root="/subdir")
        else: added["options"]=["ro"]
        a["mounts"].append(added); synchronize(a)
        if name=="nested_overmount": a["canaries"][0]["readback_mount"]="99"
    elif name.startswith("provenance_"):
        key=name.removeprefix("provenance_"); c["provenance"][key]=False if key=="rootless" else "mismatch"
    else: raise AssertionError(name)


@pytest.mark.parametrize("name,reason",MUTATIONS)
def test_specific_rejection(name,reason):
    report,expected=baseline(); mutate(report,expected,name)
    result=validator()(report,expected=expected)
    assert result["status"]=="BLOCKED" and reason in result["reasons"],result


@pytest.mark.parametrize("name",[None,"read_error","canary_seen","stacked_rw"])
def test_verifier_process_restart_consistency(name):
    report,expected=baseline()
    if name: mutate(report,expected,name)
    validator()  # explicit missing contract assertion; never import/collection error
    code="import json,sys; from benchmarks.genesis_lite.v0_3.isolation import validate_container_evidence; p=json.load(sys.stdin); print(json.dumps(validate_container_evidence(p['report'],expected=p['expected']),sort_keys=True))"
    outputs=[]
    for _ in range(2):
        done=subprocess.run([sys.executable,"-c",code],input=json.dumps(dict(report=report,expected=expected)),
                            text=True,capture_output=True,timeout=15)
        assert done.returncode==0,done.stderr
        outputs.append(json.loads(done.stdout))
    assert outputs[0]==outputs[1]
    if name:
        assert outputs[0]["status"]=="BLOCKED" and dict(MUTATIONS)[name] in outputs[0]["reasons"]
    else: assert outputs[0]==dict(status="PASS",reasons=[])


def test_baseline_test_fixture_is_complete_and_reconciles():
    report,expected=baseline()
    assert len(report["cards"])==3
    for c in report["cards"]:
        assert probe.parse_mountinfo(c["mountinfo"])==c["mounts"]
        assert {r["target"] for r in c["mounts"] if "rw" in r["options"]}==set(PRIVATE)
        assert len(c["runtime_mounts"])==len(c["mounts"])
        assert c["provenance"]==expected and len(c["canaries"])==4
        assert all(key in c["paths"] for key in ("HOME","TMPDIR","XDG_CACHE_HOME","PYTHONPYCACHEPREFIX","workdir"))
        assert all(t+":rw,nosuid,nodev,mode=1777" in c["argv"] for t in PRIVATE)
        assert "/repo:/source:ro" in c["argv"] and "/venv-host:/venv:ro" in c["argv"]


@pytest.mark.parametrize("name",["windows","host","shared","source_rw","venv_rw","stacked_rw","nested_overmount","bind_alias"])
def test_policy_mutants_preserve_raw_parsed_runtime_agreement(name):
    report,expected=baseline(); mutate(report,expected,name)
    c=report["cards"][0]
    assert probe.parse_mountinfo(c["mountinfo"])==c["mounts"]
    for row,runtime in zip(c["mounts"],c["runtime_mounts"],strict=True):
        for key in ("id","parent","device","root","target","fstype","source","options","optional"):
            assert row[key]==runtime[key]


def test_parser_escapes_bind_roots_and_readonly_view():
    raw="10 1 8:1 /bind\\040root /space\\040tab\\011slash\\134 ro shared:4 - ext4 /dev/sda1 rw\n"
    row=probe.parse_mountinfo(raw)[0]
    assert row["root"]=="/bind root" and row["target"]=="/space tab\tslash\\"
    assert row["options"]==["ro"] and row["super_options"]==["rw"]
    assert row["parent"]=="1" and row["device"]=="8:1"


@pytest.mark.parametrize("raw",["", "1 0 0:1 / / ro - tmpfs", "x 0 0:1 / / ro - tmpfs tmpfs rw",
                                "1 0 x / / ro - tmpfs tmpfs rw", "1 0 0:1 / / rw,ro - tmpfs tmpfs rw",
                                "1 0 0:1 / / ro - tmpfs tmpfs rw extra"])
def test_parser_rejects_malformed_rows(raw):
    with pytest.raises(ValueError): probe.parse_mountinfo(raw)


def test_parser_retains_stacked_and_nested_topology():
    raw="1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 0:2 / / rw - tmpfs tmpfs rw\n3 2 0:3 /sub /nested ro - ext4 /dev/sda rw\n"
    rows=probe.parse_mountinfo(raw)
    assert [r["parent"] for r in rows]==["0","1","2"]
    assert len([r for r in rows if r["target"]=="/"])==2
    assert rows[2]["root"]=="/sub"


@pytest.mark.skipif(sys.platform!="linux",reason="Linux fdinfo")
def test_probe_uses_fd_mount_and_distinguishes_absence_error_and_obscured(tmp_path,monkeypatch):
    import os
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    try: mid=probe.fd_mount_id(fd)
    finally: os.close(fd)
    token="f"*64
    a=probe.observe_marker(tmp_path,"token","A",token,mid)
    assert a["write"]=="WRITE_OK" and a["readback"]==token and a["actual_mount"]==mid
    b=probe.observe_marker(tmp_path,"token","B",token,mid)
    assert b["read"]=="READ_OK" and b["seen"]==token
    absent=probe.observe_marker(tmp_path,"absent","B",token,mid)
    assert absent["read"]=="READ_ABSENT"
    obscured=probe.observe_marker(tmp_path,"never-write","A",token,"-1")
    assert obscured["read"]=="OBSCURED_MOUNT" and not (tmp_path/"never-write").exists()
    original=probe.os.open
    def denied(path,*args,**kwargs):
        if path=="denied": raise PermissionError("EACCES")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(probe.os,"open",denied)
    error=probe.observe_marker(tmp_path,"denied","B",token,mid)
    assert error["read"]=="READ_ERROR" and "seen" not in error
