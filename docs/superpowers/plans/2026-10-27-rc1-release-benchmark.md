# RC1 Diagnostics and Benchmark Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then one fresh independent review of the product changes.

**Goal:** Deliver a locally frozen complete DV-R1.0.0-RC1 image and an honest Beta5/RC1 hardware benchmark.
**Architecture:** Native FFmpeg/Kodi diagnostic owners, existing image recipe and native updater, existing paired-media HDMI observer.
**Tech Stack:** C/C++, FFmpeg 9, Kodi 22 RC1, Python, native DRM trace/fences.
**Spec:** `docs/superpowers/specs/2026-10-27-rc1-release-benchmark-design.md`

## Global Constraints

No pixel, metadata, timing, driver or rendering-policy change. Preserve frozen
Preview2-A/C and published Beta5. No publication. Source zoom is exactly 100%.
Do not report missing counters or invalid output as zero drops or a valid run.

## Review Focus

Concurrent startup facts and stale presentation identities must not mislabel a stream.
Repeated seeks/retries must not turn startup diagnostics into per-frame logging.
Codec tags and references must not expose source URLs or permit log injection.
Incomplete traces, wrong effective routes or zoom must invalidate comparisons.
GUI counters must not silently introduce a panel into no-GUI measurements.

### Task 1: Bounded native diagnostics and RC1 identity

**Files:** Existing FFmpeg MOV association patch, Kodi native demux/decoder and
diagnostic patches, focused tests, source receipts and release defaults.
**Interfaces:** MOV exposes its private declared track relationships; Kodi logs
native codec tags and once-only decoder milestones; accepted presentation is
owned by the existing diagnostic session.

- [ ] Run the clean 208-test baseline. Extend actual-owner logging regressions
      for numeric codec tags, dependency rejection, once-only startup milestones,
      valid first presentation, retries/seeks and unavailable/disabled diagnostics.
- [ ] Observe RED. Add the minimum owner changes and preserve all media decisions.
- [ ] Run GREEN, full integration, source replay, native compilation and receipts.
- [ ] Identify DV-R1.0.0-RC1 in defaults, metadata and release tests; obtain one
      fresh independent review and resolve important findings with RED/GREEN.
- [ ] Commit and freeze the product source before benchmarking.

### Task 2: Complete image and comparable measurement pilot

**Files:** Reuse native image/inspection scripts; task-local preflight, benchmark
adapter and tests in `work/rc1-final-benchmark-20261027`.
**Interfaces:** Frozen source commit -> image hashes -> native updater -> pinned
host identity -> route/zoom-checked measurement -> raw evidence.

- [ ] Build the complete image through the native recipe. Inspect tar/disk
      payload identity, boot/initramfs, model/ABI and delivered version strings.
- [ ] Verify N100/3200U identities, update directories, recovery payloads and
      user settings. Verify Beta5 archive against its published receipt.
- [ ] Extend the existing observer with CPU-core/total sampling and GUI progress
      variants, using the same observer for both images. Unit-check CPU deltas,
      headroom aggregation and unknown/reset counters before the full matrix.
- [ ] Pilot exact native drop-counter collection without displaying a panel;
      validate progress-bar/no-GUI states and Normal zoom for every source type.
- [ ] Install and smoke-test RC1 through native updates on both hosts. Do not
      replace mounted boot payloads. Reject mismatching binaries or invalid HDMI.

### Task 3: Paired full matrix and delivery

**Files:** Compact raw results, aggregate table and benchmark notes in the task
directory; no change to frozen product code during the matrix.
**Interfaces:** Published Beta5 and frozen RC1 share source hashes, passages,
view, output rate, display profile and observation definitions.

- [ ] Run all compatible circuits with 4K/1080p sources on both hosts. Collect
      three steady samples; retain gross failures and unavailable routes.
- [ ] Run Master/Standard P7 FEL30, P5 30 and Gemini59.94 with native controls
      visible and hidden. Validate route, zoom and GUI for each window.
- [ ] Recompute CPU/GPU/drop/headroom summaries from raw evidence; pair by device,
      source, route and GUI state. Flag regressions rather than altering RC1.
- [ ] Restore frozen RC1 and original profiles/views on both hosts. Verify
      binaries and idle state, remove generated probes, keep concise evidence.
- [ ] Present the full comparison and material limits. No GitHub writes.
