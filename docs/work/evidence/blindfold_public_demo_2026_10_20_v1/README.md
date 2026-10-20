# Public demo evidence

DEMO / NON-FORMAL / SECURITY_BOUNDARY_NOT_PROVEN.
See docs/discovery/BLINDFOLD_DEMO.md for scope and interpretation.
report/index.html is self-contained and embeds report/records.json.
Targeted test history and commands are preserved. demo-complete.patch contains
only this bounded demo's three new files and minimal ACTIVE_PLAN/PROGRESS additions;
it excludes all existing CP2 edits. artifact-checks.json records preservation.
Visual rendering was blocked by local file protocol policy; no workaround used.
Library upload belongs to supervisor; no upload performed by this writer.

Cwd: `/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo`

```sh
PYTHONPATH=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo/src:/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo TMPDIR=/tmp /home/dev_kaeem/venvs/forge312/bin/python -m pytest tests/genesis_lite/test_blindfold_demo.py -q -p no:cacheprovider --basetemp=/tmp/forge-public-demo-test-v1 -rA --tb=short
```
Exit: 1.

Cwd: `/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo`

```sh
PYTHONPATH=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo/src:/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo TMPDIR=/tmp /home/dev_kaeem/venvs/forge312/bin/python -m pytest tests/genesis_lite/test_blindfold_demo.py -q -p no:cacheprovider --basetemp=/tmp/forge-public-demo-test-v2 -rA --tb=short
```
Exit: 0.

Cwd: `/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo`

```sh
PYTHONPATH=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo/src:/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo TMPDIR=/tmp /home/dev_kaeem/venvs/forge312/bin/python tools/forge_blindfold_demo.py --output /home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/public-demo-v1-evidence/report --timeout 30
```
Exit: 0.
