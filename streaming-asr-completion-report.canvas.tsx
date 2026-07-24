import {
  Stack,
  Grid,
  Stat,
  Table,
  Divider,
  H1,
  H2,
  H3,
  Text,
  Callout,
  MetricsGrid,
  Timeline,
  type TimelineEvent,
} from "qoder/canvas";

export default function StreamingASRReport() {
  const specItems = [
    {
      feature: "StreamingTranscribeWorker",
      file: "gui/workers/streaming_transcribe_worker.py",
      tests: "15",
      status: "done",
    },
    {
      feature: "Audio + Model Parallel Loading",
      file: "streaming_transcribe_worker.py",
      tests: "incl. above",
      status: "done",
    },
    {
      feature: "Chunk Transcription Loop (30s, dedup, GC)",
      file: "streaming_transcribe_worker.py",
      tests: "incl. above",
      status: "done",
    },
    {
      feature: "ReviewController.merge_segments()",
      file: "gui/controllers/review_controller.py",
      tests: "8",
      status: "done",
    },
    {
      feature: "Seek Priority Transcription",
      file: "gui/widgets/video_player.py",
      tests: "4",
      status: "done",
    },
    {
      feature: "MainWindow Streaming Integration",
      file: "gui/app.py",
      tests: "10",
      status: "done",
    },
    {
      feature: "CT-Transformer Punctuation Model",
      file: "video_splitter/extractor/engines.py",
      tests: "2",
      status: "done",
    },
    {
      feature: "QShortcut Space Key Fix",
      file: "gui/app.py",
      tests: "incl. above",
      status: "done",
    },
  ];

  const timelineEvents: TimelineEvent[] = [
    {
      id: "engines",
      label: "engines.py API",
      description: "load_funasr_model(), transcribe_file_chunk(), _extract_audio_range() — 7 new tests",
    },
    {
      id: "worker",
      label: "StreamingTranscribeWorker",
      description: "Incremental ASR worker with 8 signals, priority reorder, dedup — 15 tests",
    },
    {
      id: "merge",
      label: "merge_segments()",
      description: "Sorted insertion with dedup, index preservation — 8 tests (TDD)",
    },
    {
      id: "widgets",
      label: "Widget Enhancements",
      description: "seeked signal + subtitle status display — 5 tests (TDD)",
    },
    {
      id: "integration",
      label: "MainWindow Integration",
      description: "Full streaming workflow + QShortcut fix — 10 tests (TDD)",
    },
    {
      id: "punctuation",
      label: "Punctuation Model",
      description: "CT-Transformer integration, env var config — 2 tests",
    },
    {
      id: "bugfix",
      label: "Bug Fix + Audit",
      description: "Fixed _on_streaming_complete overwriting user corrections — 1 regression test",
    },
  ];

  return (
    <Stack gap={20}>
      <H1>Streaming ASR Transcription — Completion Report</H1>
      <Text tone="secondary">
        VideoSplitter v0.6.0 — Incremental subtitle display during video playback
      </Text>

      <Divider />

      <MetricsGrid
        columns={4}
        items={[
          { label: "Spec Items", value: "8/8", tone: "success" },
          { label: "Tests Passing", value: "462", tone: "success" },
          { label: "Bug Fixed", value: "1", tone: "warning" },
          { label: "Version", value: "0.5.4 → 0.6.0" },
        ]}
      />

      <Divider />

      <H2>Spec Implementation Status</H2>
      <Table
        headers={["Feature", "File", "Tests", "Status"]}
        rows={specItems.map((item) => [
          item.feature,
          item.file,
          item.tests,
          item.status === "done" ? "Complete" : item.status,
        ])}
        rowTone={specItems.map(() => "success" as const)}
      />

      <Divider />

      <H2>Implementation Timeline</H2>
      <Timeline events={timelineEvents} />

      <Divider />

      <H2>Bug Found & Fixed</H2>
      <Callout tone="warning" title="_on_streaming_complete overwrites user corrections">
        <Stack gap={8}>
          <Text>
            <strong>Root cause:</strong> When streaming transcription completed, the handler called{" "}
            <code>load_transcript(path)</code> which reloaded raw worker output from disk, discarding
            any text corrections the user had made during streaming.
          </Text>
          <Text>
            <strong>Fix:</strong> Use in-memory segments from ReviewController (which already received
            all chunks via merge_segments) instead of reloading. Save the corrected transcript to disk
            directly.
          </Text>
          <Text>
            <strong>Regression test:</strong>{" "}
            <code>test_on_streaming_complete_preserves_user_corrections</code>
          </Text>
        </Stack>
      </Callout>

      <Divider />

      <H2>Files Modified</H2>
      <Grid columns={2} gap={12}>
        <Stack gap={4}>
          <H3>New Files</H3>
          <Text size="small">
            <code>gui/workers/streaming_transcribe_worker.py</code> (289 lines)
          </Text>
          <Text size="small">
            <code>tests/test_streaming_worker.py</code> (15 tests)
          </Text>
        </Stack>
        <Stack gap={4}>
          <H3>Modified Files</H3>
          <Text size="small"><code>gui/app.py</code> — streaming integration, QShortcut</Text>
          <Text size="small"><code>gui/controllers/review_controller.py</code> — merge_segments()</Text>
          <Text size="small"><code>gui/widgets/video_player.py</code> — seeked signal</Text>
          <Text size="small"><code>gui/widgets/subtitle_panel.py</code> — status display</Text>
          <Text size="small"><code>video_splitter/extractor/engines.py</code> — new APIs + punctuation</Text>
        </Stack>
      </Grid>

      <Divider />

      <H2>Test Coverage Summary</H2>
      <Grid columns={3} gap={12}>
        <Stat value="15" label="Streaming Worker" tone="success" />
        <Stat value="8" label="merge_segments" tone="success" />
        <Stat value="4" label="Seek Priority" tone="success" />
        <Stat value="10" label="Streaming Integration" tone="success" />
        <Stat value="2" label="Punctuation Model" tone="success" />
        <Stat value="423" label="Existing (no regression)" tone="success" />
      </Grid>

      <Divider />

      <Callout tone="info" title="Ready for commit">
        <Text>
          All changes are staged. VERSION updated to 0.6.0, CHANGELOG entry added.
          462 tests passing (243 GUI + 219 core). Awaiting user confirmation to commit.
        </Text>
      </Callout>
    </Stack>
  );
}
