# Shared scaling choice and final qualification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans inline. One requested final independent Astra xhigh challenge, not a reviewer per task.

**Goal:** Finish renderer-wide native Kodi scaling first, qualify performance and stability, then resume the wider candidate review.

**Architecture:** Preserve Kodi output/geometry authority and original filters. Reuse Kodi's existing hardware bilinear and common native scaling-method control, including vanilla/fallback playback. Do not retain a private CB1 scaling selector or duplicate a native filter under a new name.

**Tech Stack:** Existing C/GLSL CB1, native Kodi GLES adapter/settings, pinned libplacebo/FFmpeg, WSL complete-image build and existing dual-host HDMI observer.

**Spec:** `docs/superpowers/specs/2026-10-26-scaling-choice-qualification-design.md`.

## Global constraints

- Baseline/source control `66a2e3f9fe`, branch `candidate/rc1-preview-g-kodi-native-scaling`.
- No publication, PR mutation, forced clocks or driver changes for scaler experiments.
- Native filter algorithms, source metadata/model/creative curves and exact Master reconstruction unchanged.
- One existing Kodi scaling-method choice for all playback; no CB1-only selector, Fast module or per-resolution quality rule.
- Remove failed trials and verify again after simplification. Do not count fallback as the requested route.

## Review focus

1. Scaler changes while GPU preparation is pending must invalidate old output without losing source leases.
2. Zoom/fractional geometry must reach final sampling once, with correct masks and metadata; no packed-byte interpolation.
3. One1:1 route or vendor optimization must not bypass the selected backend when actual fitting is required.
4. HDR10+ sink capability and original source HDR type must be exposed through native Kodi owners, not a panel-only label.
5. Laptop connector selection remains native and DV availability follows the actual selected HDMI link, not the first GPU.

## Task 1: Remove the superseded private scaler trial

**Files:** `CB1/src/dvbridge_render.c/.h`, `CB1/tests/native_spatial.c`, target/render controls and existing source receipts.
**Consumes:** Existing borrowed-frame callback, target geometry and source-grid processing.
**Produces:** Native-only source, no private bilinear API/selector, unchanged source receipts.

- [x] Test the private prototype and distinguish stage-only packing fusion from a universal scaler improvement.
- [x] Remove the rejected API, settings, strings, preparation wiring and prototype-only tests, including the native build mirror.
- [ ] Verify exact return to reviewed native product source, ownership receipts and all engine/integration tests.
- [ ] Record hardware performance honestly; no inference of complete movie FPS from the private scale/pack microbenchmark.

## Task 2: Complete native scaling integration qualification

**Files:** Existing owning patches for `DVOutputSettings.h`, `DVBridgeGLES.cpp`, settingsXML/en-GB strings; native integration tests.
**Consumes:** Task1's native-only source and installed native control66a2e3f9fe.
**Produces:** One original Kodi filter selection, preserved controls and honest renderer-wide scaling evidence.

- [ ] Verify original Kodi selection controls bilinear/convolution, including source geometry/filter invalidation, no private quality switch and separate FEL selection.
- [ ] Measure native hardware bilinear on both hosts across CB1, vanilla and fallback. Compare native filter stages without calling a packing-specific fusion a new universal scaler.
- [ ] Recheck native GPU fitting, original shader/kernel identities, genuine1:1 Master controls and source/target dimensions.
- [ ] Full suites, owning-patch replay, complete image and delivered payload verification. Reuse the unchanged inspected native image when product source is identical; no needless reinstall.

## Task 3: Dual-host performance and hostile interaction

**Files:** Existing private benchmark/session helpers and a compact qualification report, no telemetry branches in product.
**Consumes:** Inspected image and the immutable native/stabilized controls.
**Produces:** Explicit per-route A/B metrics and stable interaction evidence.

- [ ] Pin actual media identities, formats, source/output sizes, selected scaler and effective route. Include720p,1080p,near-UHD Dragon/crop, FEL30 and Gemini60; use native output timings, not guessed whitelist strings.
- [ ] Short screens first, then extended cadence windows; measure native scaling and prior stabilized controls with matching settings on both CPUs.
- [ ] Exercise zoom/shift, mode/scaler changes during zoom and pending preparation, subtitle/notification/O cycle, seek/pause/Home/stop/relaunch. Verify no process restart, GPU reset, stale geometry or restoration leak.
- [ ] Resolve concrete bugs using RED/GREEN and requalify after cleanup. Keep known native timing refusals explicit; no hidden force-UHD workaround.

## Task 4: PR intent and algorithm/native exposure audit

**Files:** Compact audit dossier; fix only demonstrated integration defects in existing owners.
**Consumes:** Current GitHub PR metadata/diffs and the current candidate.
**Produces:** Per-PR preserved/superseded/missing map, with test/file evidence.

- [ ] Inspect all PRs and compare intended behavior, not only commit ancestry or exact patch text.
- [ ] Audit HDR10+ metadata/parser/transport/native capability and source labels, DV-to-HDR10+ mapping, HDR10 Expert trim/luminance domains, Adaptive guidance and laptop display selection.
- [ ] Check complete source receipts and absence of debug-only/skin/test payloads in image. No physical HDR10+/NVIDIA/3D claims without hardware.

## Task 5: Requested Astra xhigh challenge and closure

**Files:** Source-based review package and durable challenge/qualification reports.
**Consumes:** Stable built candidate, stress/performance evidence, PR map and exact source range.
**Produces:** Independent Astra xhigh dossier covering every user-requested axis, prioritized findings with concrete references and uncertainty.

- [ ] Dispatch only after Tasks1-4 establish a credible build. Request real architectural alternatives, not rubber-stamp approval or unsupported Dolby certification claims.
- [ ] Regrade findings by user effect. Fix important demonstrated defects with tests and full non-regression checks; preserve a clear list of recommendations and hardware gaps.
- [ ] Keep branch/image local, restore test settings, remove failed/private temporary payloads, and report actual remaining limits. No release or GitHub publication.
