"""Compile/link the owned arm64 game and retain UBT's actual exit status."""
from datetime import datetime, timezone
import json
import re
import subprocess
import time
from native_build_paths import ROOT, build_locations

project, _ = build_locations()
argv = ["/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh",
        "OasisNative", "Mac", "Development", "-Project=" + str(project),
        "-WaitMutex", "-NoHotReloadFromIDE", "-architecture=arm64",
        "-NoUBA", "-MaxParallelActions=3"]
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
log_path = ROOT / "logs" / (stamp + "-native-game-build.txt")
start = time.monotonic()
with log_path.open("w") as log:
    process = subprocess.Popen(argv, cwd=project.parent, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    print("Game build PID:", process.pid, "Log:", log_path, flush=True)
    for line in process.stdout:
        if re.match(r"\s*export\s+", line):
            continue
        log.write(line)
        log.flush()
        if not line.startswith("[Adaptive Build]"):
            print(line if len(line) <= 650 else line[:180] + " ... [full line retained in log]\n", end="", flush=True)
    code = process.wait()
receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "argv": argv,
           "exit_code": code, "log": str(log_path),
           "elapsed_seconds": round(time.monotonic()-start, 3),
           "ubt_build_passed": code == 0, "runtime_verified": False}
(ROOT / "logs/native-game-build-latest.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(json.dumps(receipt, indent=2), flush=True)
raise SystemExit(code)
