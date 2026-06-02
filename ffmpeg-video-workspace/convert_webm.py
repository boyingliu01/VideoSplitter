import importlib
import sys
import os
import subprocess
import json

sys.path.insert(0, r'E:\Private\skill开发')
mod = importlib.import_module('ffmpeg-skill')
FFmpegSkill = mod.FFmpegSkill
ffmpeg = FFmpegSkill()

input_path = r'E:\Private\skill开发\ffmpeg-video-workspace\test-files\test_input.mp4'
output_path = r'E:\Private\skill开发\ffmpeg-video-workspace\iteration-1\eval-convert-format\with_skill\outputs\output.webm'

os.makedirs(os.path.dirname(output_path), exist_ok=True)

ffmpeg.convert_format(input_path, output_path, video_codec='libvpx-vp9', audio_codec='libopus')

assert os.path.exists(output_path), 'OUTPUT FILE DOES NOT EXIST'
size = os.path.getsize(output_path)
assert size > 0, f'OUTPUT FILE IS EMPTY (size={size})'
print(f'Output file size: {size} bytes')

result = subprocess.run(
    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', output_path],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
audio_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)

assert video_stream is not None, 'No video stream found in output'
assert audio_stream is not None, 'No audio stream found in output'
assert video_stream['codec_name'] == 'vp9', (
    f"Video codec is {video_stream['codec_name']}, expected vp9"
)
assert audio_stream['codec_name'] == 'opus', (
    f"Audio codec is {audio_stream['codec_name']}, expected opus"
)

print(f"Video codec: {video_stream['codec_name']}")
print(f"Audio codec: {audio_stream['codec_name']}")
print('SUCCESS')
