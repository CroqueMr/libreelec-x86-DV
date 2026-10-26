# Shared scaling choice and final qualification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans inline. One requested final independent Astra xhigh challenge, not a reviewer per task.

**Goal:** Finish the common CB1 resizing integration, qualify native/custom performance and stability, then challenge the entire candidate independently.

**Architecture:** Preserve Kodi output/geometry authority and native filter implementation. Keep source-grid processing and reuse the common final rendering boundary for an explicit optimized bilinear alternative. No circuit copies or new queues.

**Tech Stack:** Existing C/GLSL CB1, native Kodi GLES adapter/settings, pinned libplacebo/FFmpeg, WSL complete-image build and existing dual-host HDMI observer.

**Spec:** `docs/superpowers/specs/2026-10-26-scaling-choice-qualification-design.md`.

## Global constraints

- Baseline/source control `66a2e3f9fe`, branch `candidate/rc1-preview-g-kodi-native-scaling`.
- No publication, PR mutation, forced clocks or driver changes for scaler experiments.
- Native filters, vanilla/fallback, source metadata/model/creative curves and exact Master reconstruction unchanged.
- One shared choice, native default; no Fast/Auto module or per-resolution quality rules.
- Remove failed trials and verify again after simplification. Do not count fallback as the requested route.

## Review focus

1. Scaler changes while GPU preparation is pending must invalidate old output without losing source leases.
2. Zoom/fractional geometry must reach final sampling once, with correct masks and metadata; no packed-byte interpolation.
3. One1:1 route or vendor optimization must not bypass the selected backend when actual fitting is required.
4. HDR10+ sink capability and original source HDR type must be exposed through native Kodi owners, not a panel-only label.
5. Laptop connector selection remains native and DV availability follows the actual selected HDMI link, not the first GPU.

## Task1: Common engine choice and evidence gate

**Files:** `CB1/src/dvbridge_render.c/.h`, `CB1/tests/native_spatial.c`, target/render controls and existing source receipts.
**Consumes:** Existing borrowed-frame callback, target geometry and source-grid processing.
**Produces:** `dvbridge_renderer_set_bilinear_scaling(renderer,bool)`; default false.

- [ ] Add failing real tests: custom must bypass the native callback only at final fitting, use explicit bilinear parameters, retain identity and reset to native. Preserve unchanged Master controls.
- [ ] Implement the smallest common switch in final rendering; do not disable source-grid orchestration or change FEL filters.
- [ ] Run all engine tests and real-GPU target/crop witnesses. Prototype complete-pipeline timing with the existing private Kodi candidate slot before accepting a product setting.
- [ ] Retain only measured gains; otherwise remove the custom trial. Simplify and rerun.

## Task2: Native settings/frame-boundary integration

**Files:** Existing owning patches for `DVOutputSettings.h`, `DVBridgeGLES.cpp`, settingsXML/en-GB strings; native integration tests.
**Consumes:** Task1's engine switch.
**Produces:** `dvbridge.videoscaler` integer0(native)/1(optimized bilinear), native default, existing preference revision ownership.

- [ ] Failing tests: persistence/default, invalid-value normalization, unchanged output/model/FEL selections and revision changes on native/custom/native.
- [ ] Wire one frame preference into all CB1 prepare owners; cancellation/reuse must consume the same revision. Add only bounded transition diagnostics.
- [ ] Keep normal Kodi filter preference saved and untouched; no skin code or duplicated circuit selectors.
- [ ] Full suites, fresh owning-patch replay, complete image and delivered payload verification; install through native updater only.

## Task3: Dual-host performance and hostile interaction

**Files:** Existing private benchmark/session helpers and a compact qualification report, no telemetry branches in product.
**Consumes:** Inspected image and the immutable native/stabilized controls.
**Produces:** Explicit per-route A/B metrics and stable interaction evidence.

- [ ] Pin actual media identities, formats, source/output sizes, selected scaler and effective route. Include720p,1080p,near-UHD Dragon/crop, FEL30 and Gemini60; use native output timings, not guessed whitelist strings.
- [ ] Short screens first, then extended cadence windows; measure native/custom and prior stabilized controls with matching settings on both CPUs.
- [ ] Exercise zoom/shift, mode/scaler changes during zoom and pending preparation, subtitle/notification/O cycle, seek/pause/Home/stop/relaunch. Verify no process restart, GPU reset, stale geometry or restoration leak.
- [ ] Resolve concrete bugs using RED/GREEN and requalify after cleanup. Keep known native timing refusals explicit; no hidden force-UHD workaround.

## Task4: PR intent and algorithm/native exposure audit

**Files:** Compact audit dossier; fix only demonstrated integration defects in existing owners.
**Consumes:** Current GitHub PR metadata/diffs and the current candidate.
**Produces:** Per-PR preserved/superseded/missing map, with test/file evidence.

- [ ] Inspect all PRs and compare intended behavior, not only commit ancestry or exact patch text.
- [ ] Audit HDR10+ metadata/parser/transport/native capability and source labels, DV-to-HDR10+ mapping, HDR10 Expert trim/luminance domains, Adaptive guidance and laptop display selection.
- [ ] Check complete source receipts and absence of debug-only/skin/test payloads in image. No physical HDR10+/NVIDIA/3D claims without hardware.

## Task5: Requested Astra xhigh challenge and closure

**Files:** Source-based review package and durable challenge/qualification reports.
**Consumes:** Stable built candidate, stress/performance evidence, PR map and exact source range.
**Produces:** Independent Astra xhigh dossier covering every user-requested axis, prioritized findings with concrete references and uncertainty.

- [ ] Dispatch only after Tasks1-4 establish a credible build. Request real architectural alternatives, not rubber-stamp approval or unsupported Dolby certification claims.
- [ ] Regrade findings by user effect. Fix important demonstrated defects with tests and full non-regression checks; preserve a clear list of recommendations and hardware gaps.
- [ ] Keep branch/image local, restore test settings, remove failed/private temporary payloads, and report actual remaining limits. No release or GitHub publication.
