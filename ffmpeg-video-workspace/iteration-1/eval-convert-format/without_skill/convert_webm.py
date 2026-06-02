import subprocess
import os
import sys

input_file = r"E:\Private\skill开发\ffmpeg-video-workspace\test-files\test_input.mp4"
output_file = r"E:\Private\skill开发\ffmpeg-video-workspace\iteration-1\eval-convert-format\without_skill\outputs\output.webm"

os.makedirs(os.path.dirname(output_file), exist_ok=True)

cmd = [
    "ffmpeg",
    "-i", input_file,
    "-c:v", "libvpx-vp9",
    "-c:a", "libopus",
    "-y",
    output_file
]

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("FFmpeg failed:")
    print(result.stderr)
    sys.exit(1)

if not os.path.exists(output_file):
    print(f"FAIL: Output file not found at {output_file}")
    sys.exit(1)

size = os.path.getsize(output_file)
if size == 0:
    print("FAIL: Output file is empty")
    sys.exit(1)
print(f"Output file size: {size} bytes")

probe_cmd = [
    "ffprobe",
    "-v", "error",
    "-select_streams", "v:0",
    "-show_entries", "stream=codec_name",
    "-of", "default=noprint_wrappers=1:nokey=1",
    output_file
]
probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
video_codec = probe_result.stdout.strip()
if video_codec != "vp9":
    print(f"FAIL: Expected video codec vp9, got {video_codec}")
    sys.exit(1)
print(f"Video codec: {video_codec}")

probe_cmd = [
    "ffprobe",
    "-v", "error",
    "-select_streams", "a:0",
    "-show_entries", "stream=codec_name",
    "-of", "default=noprint_wrappers=1:nokey=1",
    output_file
]
probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
audio_codec = probe_result.stdout.strip()
if audio_codec != "opus":
    print(f"FAIL: Expected audio codec opus, got {audio_codec}")
    sys.exit(1)
print(f"Audio codec: {audio_codec}")

print("SUCCESS")
