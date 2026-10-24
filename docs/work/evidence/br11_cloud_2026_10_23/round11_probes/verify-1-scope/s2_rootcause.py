"""Root cause check: replace ONLY owners.py's copy.deepcopy (line 409) by a JSON round trip (C parser, no Python
recursion); the deep-metadata spend should then be observed and its restore refused."""
import json, sys, types
sys.path.insert(0, "/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r11/verify-1-scope")
import engcore.mind.world.owners as owners
owners.copy = types.SimpleNamespace(deepcopy=lambda x: json.loads(json.dumps(x)))
import runpy
ns = runpy.run_path("/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r11/verify-1-scope/s1_scope.py", run_name="not_main")
