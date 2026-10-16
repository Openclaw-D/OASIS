"""Run the owned editor target with bounded concurrency and retain its actual result."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import time
from native_build_paths import build_locations

ROOT = Path(__file__).resolve().parents[1]
project, archive = build_locations()
argv = [
    "/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh",
    "OasisNativeEditor", "Mac", "Development",
    "-Project=" + str(project),
    "-WaitMutex", "-NoHotReloadFromIDE", "-architecture=arm64",
    "-NoUBA", "-MaxParallelActions=3",
]
started = time.monotonic()
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
log_path = ROOT / "logs" / (stamp + "-native-editor-build.txt")
with log_path.open("w") as log:
    process = subprocess.Popen(argv, cwd=project.parent, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    print("Build PID:", process.pid, "Log:", log_path, flush=True)
    for line in process.stdout:
        log.write(line)
        log.flush()
        if line.startswith("[Adaptive Build]"):
            continue
        print(line if len(line) <= 600 else line[:180] + " ... [full line retained in log]\n", end="", flush=True)
    code = process.wait()
receipt = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "argv": argv, "exit_code": code,
    "elapsed_seconds": round(time.monotonic() - started, 3),
    "log": str(log_path), "build_passed": code == 0,
    "runtime_verified": False,
}
(ROOT / "logs/native-editor-build-latest.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2), flush=True)
raise SystemExit(code)
