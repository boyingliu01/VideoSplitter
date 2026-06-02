"""Fix grading.json files to include summary field expected by aggregate script."""
import json
import os

WORKSPACE = r"E:\Private\skill开发\ffmpeg-video-workspace\iteration-1"
configs = [
    ("eval-convert-format", "with_skill"),
    ("eval-convert-format", "without_skill"),
    ("eval-resize-video", "with_skill"),
    ("eval-resize-video", "without_skill"),
    ("eval-video-info", "with_skill"),
    ("eval-video-info", "without_skill"),
]

for eval_name, config in configs:
    path = os.path.join(WORKSPACE, eval_name, config, "run-1", "grading.json")
    if not os.path.exists(path):
        print(f"MISSING: {path}")
        continue
    with open(path) as f:
        data = json.load(f)

    expectations = data.get("expectations", [])
    passed = sum(1 for e in expectations if e["passed"])
    total = len(expectations)

    data["summary"] = {
        "pass_rate": passed / total if total > 0 else 0.0,
        "passed": passed,
        "failed": total - passed,
        "total": total
    }

    # Also read timing
    timing_path = path.replace("grading.json", "timing.json")
    if os.path.exists(timing_path):
        with open(timing_path) as f:
            timing = json.load(f)
        data["timing"] = timing

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[{eval_name}/{config}] {passed}/{total} passed")

print("Done")
