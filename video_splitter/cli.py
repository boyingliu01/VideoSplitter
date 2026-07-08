"""CLI entry point for video_splitter."""
from __future__ import annotations
import argparse
import logging
import sys
import os
from pathlib import Path
from .config import SplitConfig
from .pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("video_splitter")


def cmd_split(args):
    config = SplitConfig.from_env()
    config.max_segment_duration = args.max_duration
    config.resume = args.resume
    if args.model:
        config.model_size = args.model
    if args.cut_mode:
        config.cut_mode = args.cut_mode

    if args.dry_run:
        pipeline = Pipeline(config)
        result = pipeline.dry_run(args.video)
        print(f"\n=== Dry Run ===")
        print(f"Video: {args.video}")
        print(f"Duration: {result.get('duration_minutes', '?')} min")
        print(f"Estimated tokens: {result.get('estimated_tokens', '?')}")
        print(f"Estimated cost: ¥{result.get('estimated_cost_rmb', '?')}")
        print(f"LLM calls: {result.get('llm_calls', '?')}")
        return

    pipeline = Pipeline(config)
    result = pipeline.run(args.video)
    print(f"\n=== Split Complete ===")
    print(f"Video: {result['video']}")
    print(f"Status: {result['status']}")
    print(f"Segments: {len(result['output_files'])}")
    print(f"Elapsed: {result['elapsed_seconds']}s")
    for f in result.get("output_files", []):
        print(f"  - {f}")
    if result.get("srt_file"):
        print(f"SRT: {result['srt_file']}")


def cmd_transcribe(args):
    config = SplitConfig.from_env()
    if args.model:
        config.model_size = args.model
    from .extractor.audio import AudioExtractor
    from .extractor.transcribe import transcribe
    import json

    audio = AudioExtractor()
    audio_path = audio.extract(args.video)
    transcript = transcribe(audio_path, config)
    out_path = str(Path(args.video).with_suffix(".transcript.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    print(f"Transcript saved: {out_path}")
    print(f"Duration: {transcript['duration']:.0f}s")
    print(f"Segments: {len(transcript['segments'])}")


def cmd_cut(args):
    with open(args.chapters, "r", encoding="utf-8") as f:
        import json
        chapters = json.load(f)
    config = SplitConfig.from_env()
    if args.cut_mode:
        config.cut_mode = args.cut_mode
    from .splitter.cutter import VideoCutter
    from pathlib import Path

    cutter = VideoCutter(config)
    output_dir = str(Path(args.video).with_suffix("_segments"))
    files = cutter.cut(args.video, chapters, output_dir)
    print(f"Cut complete: {len(files)} segments")
    for f in files:
        print(f"  - {f}")


def cmd_check(args):
    """Validate all dependencies and estimate performance."""
    import subprocess
    import time

    print("=== video_splitter check ===")
    issues = []

    # Check FFmpeg
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        print(f"[OK] FFmpeg: {r.stdout.split(chr(10))[0].strip()}")
    except Exception:
        issues.append("FFmpeg not found in PATH")
        print("[FAIL] FFmpeg not found")

    # Check FunASR
    try:
        from funasr import AutoModel
        print("[OK] FunASR: available")
        # Quick benchmark
        import tempfile, wave, time, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        # Generate 10s of 16kHz silent audio
        with wave.open(tmp_path, "w") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
            wf.writeframes(b'\x00' * 16000 * 2 * 10)
        t0 = time.time()
        model = AutoModel(model="paraformer-zh", device="cpu")
        res = model.generate(input=tmp_path)
        elapsed = time.time() - t0
        os.unlink(tmp_path)
        print(f"[OK] FunASR benchmark (paraformer-zh/cpu): {elapsed:.1f}s for 10s audio")
    except Exception as e:
        issues.append(f"FunASR check failed: {e}")
        print(f"[FAIL] FunASR: {e}")

    # Check json-repair
    try:
        from json_repair import repair_json
        print("[OK] json-repair: available")
    except ImportError:
        issues.append("json-repair not installed (pip install json-repair)")
        print("[WARN] json-repair: not installed")

    # Check LLM API config
    config = SplitConfig.from_env()
    if config.llm_api_key:
        print(f"[OK] LLM API key: configured ({config.llm_api_base})")
    else:
        issues.append("No LLM API key (set DEEPSEEK_API_KEY or OPENAI_API_KEY)")
        print("[WARN] LLM API key: not set")

    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("\nAll checks passed!")


def cmd_batch(args):
    """Process multiple videos sequentially."""
    import glob
    videos = glob.glob(os.path.join(args.dir, "*.mp4"))
    if not videos:
        print(f"No .mp4 files found in {args.dir}")
        return

    config = SplitConfig.from_env()
    config.max_segment_duration = args.max_duration
    config.resume = args.resume

    results = []
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {os.path.basename(video)}")
        try:
            pipeline = Pipeline(config)
            result = pipeline.run(video)
            results.append({"video": video, "status": "success", "segments": len(result["output_files"])})
        except Exception as e:
            results.append({"video": video, "status": "error", "error": str(e)})
            logger.error(f"Failed: {video} - {e}")

    # Summary
    ok = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    print(f"\n=== Batch Complete ===")
    print(f"Total: {len(results)}, OK: {ok}, Failed: {failed}")
    for r in results:
        status = "[OK]" if r["status"] == "success" else "[FAIL]"
        print(f"  {status} {os.path.basename(r['video'])} - {r['status']}")


def main():
    parser = argparse.ArgumentParser(description="Video Splitter - Smart topic-based video chaptering")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("split", help="Full pipeline: split video by topic")
    p.add_argument("video", help="Input video path")
    p.add_argument("--max-duration", type=int, default=15, help="Max segment duration in minutes (default: 15)")
    p.add_argument("--model", choices=["paraformer-zh"], help="FunASR model name")
    p.add_argument("--cut-mode", choices=["fast", "precise"], help="Cut precision mode")
    p.add_argument("--resume", action="store_true", help="Skip steps with existing intermediate files")
    p.add_argument("--dry-run", action="store_true", help="Estimate cost without LLM call")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("transcribe", help="Only transcribe audio to text")
    p.add_argument("video")
    p.add_argument("--model", choices=["paraformer-zh"])
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("cut", help="Only cut video using existing chapters.json")
    p.add_argument("video")
    p.add_argument("--chapters", required=True, help="Path to chapters.json")
    p.add_argument("--cut-mode", choices=["fast", "precise"])
    p.set_defaults(func=cmd_cut)

    p = sub.add_parser("check", help="Check dependencies and estimate performance")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("batch", help="Process all .mp4 files in a directory")
    p.add_argument("dir", help="Directory with .mp4 files")
    p.add_argument("--max-duration", type=int, default=15)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(func=cmd_batch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
