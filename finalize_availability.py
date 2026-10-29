"""Submit only a run identity; backend independently verifies public GitHub evidence."""
import json
import os
from pathlib import Path
from run_catalog import api

event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
run = event["workflow_run"]
result = api({"action": "finalize", "run_id": run["id"], "run_attempt": run["run_attempt"]})
if result.get("ok") is not True:
    raise RuntimeError("Availability confirmation failed")
print(json.dumps(result))
