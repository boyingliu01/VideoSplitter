"""
Grading script for ffmpeg-video skill evaluation.
Evaluates all 6 runs against assertions using ffprobe and file checks.
Outputs grading.json for each run directory.
"""
import subprocess
import json
import os

WORKSPACE = r"E:\Private\skill开发\ffmpeg-video-workspace\iteration-1"

def run_ffprobe(filepath):
    """Run ffprobe on a file and return JSON output."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", filepath],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)

def check_assertion(name, passed, evidence):
    return {"text": name, "passed": passed, "evidence": evidence}

def grade_convert_format(run_dir):
    """Grade eval-0: convert-format"""
    output = os.path.join(run_dir, "output.webm")
    results = []

    # 1. output-webm-exists
    exists = os.path.exists(output) and os.path.getsize(output) > 0
    results.append(check_assertion(
        "output-webm-exists",
        exists,
        f"File exists: {os.path.exists(output)}, size: {os.path.getsize(output) if os.path.exists(output) else 0} bytes"
    ))

    if not exists:
        results.append(check_assertion("output-webm-valid", False, "File does not exist"))
        results.append(check_assertion("output-has-vp9-video", False, "File does not exist"))
        results.append(check_assertion("output-has-opus-audio", False, "File does not exist"))
        return {"expectations": results}

    # 2. output-webm-valid
    probe = run_ffprobe(output)
    results.append(check_assertion("output-webm-valid", probe is not None, f"ffprobe readable: {probe is not None}"))

    if probe is None:
        results.append(check_assertion("output-has-vp9-video", False, "ffprobe failed"))
        results.append(check_assertion("output-has-opus-audio", False, "ffprobe failed"))
        return {"expectations": results}

    # 3. output-has-vp9-video
    video_codecs = [s["codec_name"] for s in probe.get("streams", []) if s["codec_type"] == "video"]
    has_vp9 = "vp9" in video_codecs
    results.append(check_assertion("output-has-vp9-video", has_vp9, f"Video codecs: {video_codecs}"))

    # 4. output-has-opus-audio
    audio_codecs = [s["codec_name"] for s in probe.get("streams", []) if s["codec_type"] == "audio"]
    has_opus = "opus" in audio_codecs
    results.append(check_assertion("output-has-opus-audio", has_opus, f"Audio codecs: {audio_codecs}"))

    return {"expectations": results}

def grade_resize_video(run_dir):
    """Grade eval-1: resize-video"""
    output = os.path.join(run_dir, "output_720p.mp4")
    results = []

    # 1. output-mp4-exists
    exists = os.path.exists(output) and os.path.getsize(output) > 0
    results.append(check_assertion(
        "output-mp4-exists",
        exists,
        f"File exists: {os.path.exists(output)}, size: {os.path.getsize(output) if os.path.exists(output) else 0} bytes"
    ))

    if not exists:
        results.append(check_assertion("output-resolution-is-720p", False, "File does not exist"))
        results.append(check_assertion("output-is-valid-video", False, "File does not exist"))
        return {"expectations": results}

    # 2 + 3. Probe
    probe = run_ffprobe(output)
    results.append(check_assertion("output-is-valid-video", probe is not None, f"ffprobe readable: {probe is not None}"))

    if probe is None:
        results.append(check_assertion("output-resolution-is-720p", False, "ffprobe failed"))
        return {"expectations": results}

    # Check resolution
    video_streams = [s for s in probe.get("streams", []) if s["codec_type"] == "video"]
    if video_streams:
        w = video_streams[0].get("width", 0)
        h = video_streams[0].get("height", 0)
        is_720p = w == 1280 and h == 720
        results.append(check_assertion("output-resolution-is-720p", is_720p, f"Resolution: {w}x{h}"))
    else:
        results.append(check_assertion("output-resolution-is-720p", False, "No video stream found"))

    return {"expectations": results}

def grade_video_info(run_dir):
    """Grade eval-2: video-info"""
    info_file = os.path.join(run_dir, "info.json")
    results = []

    # 1. info-json-exists
    exists = os.path.exists(info_file)
    parseable = False
    if exists:
        try:
            with open(info_file, "r") as f:
                data = json.load(f)
            parseable = True
        except Exception:
            data = {}
    else:
        data = {}
    results.append(check_assertion(
        "info-json-exists",
        exists and parseable,
        f"File exists: {exists}, parseable: {parseable}"
    ))

    if not parseable:
        results.append(check_assertion("info-contains-duration", False, "JSON not parseable"))
        results.append(check_assertion("info-contains-resolution", False, "JSON not parseable"))
        results.append(check_assertion("info-contains-codec", False, "JSON not parseable"))
        results.append(check_assertion("info-contains-fps", False, "JSON not parseable"))
        return {"expectations": results}

    # 2. info-contains-duration
    has_duration = data.get("duration", 0) > 0
    results.append(check_assertion("info-contains-duration", has_duration, f"duration={data.get('duration')}"))

    # 3. info-contains-resolution
    has_res = data.get("width", 0) > 0 and data.get("height", 0) > 0
    results.append(check_assertion("info-contains-resolution", has_res, f"width={data.get('width')}, height={data.get('height')}"))

    # 4. info-contains-codec
    codec = data.get("codec", "")
    has_codec = bool(codec)
    results.append(check_assertion("info-contains-codec", has_codec, f"codec={codec}"))

    # 5. info-contains-fps
    has_fps = data.get("fps", 0) > 0
    results.append(check_assertion("info-contains-fps", has_fps, f"fps={data.get('fps')}"))

    return {"expectations": results}

if __name__ == "__main__":
    configs = [
        ("eval-convert-format", "with_skill", grade_convert_format),
        ("eval-convert-format", "without_skill", grade_convert_format),
        ("eval-resize-video", "with_skill", grade_resize_video),
        ("eval-resize-video", "without_skill", grade_resize_video),
        ("eval-video-info", "with_skill", grade_video_info),
        ("eval-video-info", "without_skill", grade_video_info),
    ]

    all_passed = True
    for eval_name, variant, grade_fn in configs:
        run_dir = os.path.join(WORKSPACE, eval_name, variant, "outputs")
        result = grade_fn(run_dir)
        grading_path = os.path.join(WORKSPACE, eval_name, variant, "grading.json")
        with open(grading_path, "w") as f:
            json.dump(result, f, indent=2)
        passed = sum(1 for e in result["expectations"] if e["passed"])
        total = len(result["expectations"])
        print(f"[{eval_name}/{variant}] {passed}/{total} passed")
        if passed != total:
            all_passed = False

    if all_passed:
        print("\nALL ASSERTIONS PASSED")
    else:
        print("\nSOME ASSERTIONS FAILED — check grading.json files")
