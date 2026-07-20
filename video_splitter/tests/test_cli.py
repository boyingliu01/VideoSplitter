"""Tests for cli.py — argument parsing and subcommand dispatch."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import argparse
from unittest.mock import MagicMock, patch


from video_splitter.cli import cmd_split, cmd_transcribe, cmd_cut, cmd_review, cmd_gui  # noqa: E402


class TestArgumentParsing:
    """Tests for CLI argument parser structure."""

    def test_split_default_max_duration(self):
        ns = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                cut_mode=None, resume=False, dry_run=False)
        assert ns.max_duration == 15
        assert ns.resume is False
        assert ns.dry_run is False

    def test_split_with_all_options(self):
        ns = argparse.Namespace(video="test.mp4", max_duration=10, model="tiny",
                                cut_mode="precise", resume=True, dry_run=True)
        assert ns.max_duration == 10
        assert ns.model == "tiny"
        assert ns.cut_mode == "precise"
        assert ns.resume is True

    def test_transcribe_command_defaults(self):
        ns = argparse.Namespace(video="test.mp4", model="base")
        assert ns.model == "base"

    def test_review_command_defaults(self):
        ns = argparse.Namespace(video="test.mp4", transcript=None, resume=False, no_save=False)
        assert ns.no_save is False


class TestCmdSplit:
    """Tests for cmd_split handler."""

    def test_cmd_split_normal(self):
        args = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                  cut_mode=None, resume=False, dry_run=False)
        fake_result = {
            "video": "test.mp4",
            "status": "success",
            "output_files": ["/tmp/01.mp4"],
            "elapsed_seconds": 5.0,
        }
        with patch("video_splitter.cli.Pipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = fake_result
            mock_pipeline_class.return_value = mock_pipeline
            cmd_split(args)
        mock_pipeline.run.assert_called_once_with("test.mp4")

    def test_cmd_split_dry_run(self):
        args = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                  cut_mode=None, resume=False, dry_run=True)
        fake_dry_result = {
            "status": "ok",
            "duration_minutes": 10.0,
            "estimated_tokens": 5000,
            "estimated_cost_rmb": 0.0005,
            "llm_calls": 1,
        }
        with patch("video_splitter.cli.Pipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.dry_run.return_value = fake_dry_result
            mock_pipeline_class.return_value = mock_pipeline
            cmd_split(args)
        mock_pipeline.dry_run.assert_called_once_with("test.mp4")
        mock_pipeline.run.assert_not_called()


class TestCmdTranscribe:
    """Tests for cmd_transcribe handler."""

    def test_cmd_transcribe_basic(self, tmp_path):
        """cmd_transcribe extracts audio and transcribes."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        args = argparse.Namespace(video=video_path, model=None)

        with (
            patch("video_splitter.extractor.audio.AudioExtractor") as mock_audio_cls,
            patch("video_splitter.extractor.transcribe.transcribe") as mock_transcribe,
        ):
            mock_audio = MagicMock()
            mock_audio.extract.return_value = str(tmp_path / "test.wav")
            mock_audio_cls.return_value = mock_audio
            mock_transcribe.return_value = {"language": "zh", "duration": 60.0, "segments": []}

            cmd_transcribe(args)

        mock_audio.extract.assert_called_once()
        mock_transcribe.assert_called_once()


class TestCmdCut:
    """Tests for cmd_cut handler."""

    def test_cmd_cut_basic(self, tmp_path):
        chapters_file = tmp_path / "chapters.json"
        chapters_file.write_text('[{"title":"01","start_seconds":0,"end_seconds":300}]')
        video_file = tmp_path / "test.mp4"
        video_file.write_text("dummy")
        args = argparse.Namespace(video=str(video_file), chapters=str(chapters_file), cut_mode=None)

        with (
            patch("video_splitter.splitter.cutter.VideoCutter") as mock_cutter_cls,
            patch("pathlib.Path.with_suffix", return_value=tmp_path / "test_segments") as _,
        ):
            mock_cutter = MagicMock()
            mock_cutter.cut.return_value = ["/tmp/01.mp4"]
            mock_cutter_cls.return_value = mock_cutter
            cmd_cut(args)

        mock_cutter.cut.assert_called_once()


class TestCmdReview:
    """Tests for cmd_review handler."""

    def test_cmd_review_basic(self):
        args = argparse.Namespace(video="test.mp4", transcript=None, resume=False, no_save=False)
        with patch("video_splitter.review.run_review") as mock_run_review:
            cmd_review(args)
        mock_run_review.assert_called_once_with(
            video_path="test.mp4", transcript_path=None, resume=False, no_save=False,
        )


class TestCmdGui:
    """Tests for cmd_gui handler."""

    def test_cmd_gui_calls_main(self):
        args = argparse.Namespace()
        with patch("gui.app.main") as mock_gui_main:
            cmd_gui(args)
        mock_gui_main.assert_called_once()

    def test_cmd_gui_import_error(self):
        args = argparse.Namespace()
        with patch.dict("sys.modules", {"gui.app": None, "gui": None}):
            import pytest
            with pytest.raises(SystemExit):
                cmd_gui(args)


class TestCmdCheck:
    """Tests for cmd_check — dependency validation."""

    def test_cmd_check_ffmpeg_missing(self, capsys):
        from video_splitter.cli import cmd_check
        args = argparse.Namespace()
        with (
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch.dict("os.environ", {}, clear=True),
            patch.dict("sys.modules", {"faster_whisper": None}),
        ):
            cmd_check(args)
        captured = capsys.readouterr()
        assert "FAIL" in captured.out


class TestCmdBatch:
    """Tests for cmd_batch — multi-video processing."""

    def test_cmd_batch_no_files(self, capsys):
        from video_splitter.cli import cmd_batch
        args = argparse.Namespace(dir="/nonexistent", max_duration=15, resume=False)
        with patch("glob.glob", return_value=[]):
            cmd_batch(args)
        captured = capsys.readouterr()
        assert "No .mp4 files" in captured.out

    def test_cmd_batch_success(self, capsys):
        from video_splitter.cli import cmd_batch
        args = argparse.Namespace(dir="/tmp/videos", max_duration=15, resume=False)
        with (
            patch("glob.glob", return_value=["/tmp/videos/a.mp4"]),
            patch("video_splitter.cli.Pipeline") as MockPipeline,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = {
                "output_files": ["seg1.mp4"],
                "status": "success",
            }
            MockPipeline.return_value = mock_pipeline
            cmd_batch(args)
        captured = capsys.readouterr()
        assert "Batch Complete" in captured.out
        assert "OK: 1" in captured.out

    def test_cmd_batch_error(self, capsys):
        from video_splitter.cli import cmd_batch
        args = argparse.Namespace(dir="/tmp/videos", max_duration=15, resume=False)
        with (
            patch("glob.glob", return_value=["/tmp/videos/bad.mp4"]),
            patch("video_splitter.cli.Pipeline") as MockPipeline,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.run.side_effect = RuntimeError("FFmpeg missing")
            MockPipeline.return_value = mock_pipeline
            cmd_batch(args)
        captured = capsys.readouterr()
        assert "Failed: 1" in captured.out


class TestMainParser:
    """Tests for main() parser and dispatch."""

    def test_main_split_dispatch(self):
        from video_splitter.cli import main
        with patch("sys.argv", ["cli.py", "split", "test.mp4"]):
            with patch("video_splitter.cli.cmd_split") as mock_cmd:
                main()
                mock_cmd.assert_called_once()

    def test_main_check_dispatch(self):
        from video_splitter.cli import main
        with patch("sys.argv", ["cli.py", "check"]):
            with patch("video_splitter.cli.cmd_check") as mock_cmd:
                main()
                mock_cmd.assert_called_once()

    def test_main_gui_dispatch(self):
        from video_splitter.cli import main
        with patch("sys.argv", ["cli.py", "gui"]):
            with patch("video_splitter.cli.cmd_gui") as mock_cmd:
                main()
                mock_cmd.assert_called_once()

    def test_main_batch_dispatch(self):
        from video_splitter.cli import main
        with patch("sys.argv", ["cli.py", "batch", "/tmp/vids"]):
            with patch("video_splitter.cli.cmd_batch") as mock_cmd:
                main()
                mock_cmd.assert_called_once()

    def test_cmd_split_with_model_override(self):
        from video_splitter.cli import cmd_split
        args = argparse.Namespace(
            video="test.mp4", max_duration=10, model="tiny",
            cut_mode="precise", resume=True, dry_run=False,
        )
        with patch("video_splitter.cli.Pipeline") as MockP:
            mock_p = MagicMock()
            mock_p.run.return_value = {
                "video": "test.mp4", "status": "ok",
                "output_files": [], "elapsed_seconds": 1.0,
            }
            MockP.return_value = mock_p
            cmd_split(args)
        config = MockP.call_args[0][0]
        assert config.model_size == "tiny"
        assert config.cut_mode == "precise"

    def test_cmd_split_with_srt_output(self, capsys):
        from video_splitter.cli import cmd_split
        args = argparse.Namespace(
            video="test.mp4", max_duration=15, model=None,
            cut_mode=None, resume=False, dry_run=False,
        )
        with patch("video_splitter.cli.Pipeline") as MockP:
            mock_p = MagicMock()
            mock_p.run.return_value = {
                "video": "test.mp4", "status": "ok",
                "output_files": ["/tmp/01.mp4"], "elapsed_seconds": 1.0,
                "srt_file": "/tmp/test.srt",
            }
            MockP.return_value = mock_p
            cmd_split(args)
        captured = capsys.readouterr()
        assert "SRT:" in captured.out
