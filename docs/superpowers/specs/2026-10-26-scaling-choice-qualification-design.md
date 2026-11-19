# Shared CB1 scaling and final integration qualification

Execution authorized by the user on2026-10-26. Continue inline, with Ponytail
cleanup and the requested final independent Astra xhigh challenge. No publication.

## Contract

- Preserve native PreviewG source/image `66a2e3f9fe` as the control.
- Updated user scope: scaling selection belongs to native Kodi playback,
  including vanilla SDR/HDR10, fallback and CB1, not a CB1-only setting.
  Finish scaling before the broader qualification/audit work.
- Native uses the existing original Kodi classes/kernels and saved native filter
  selection, unchanged. Custom is explicitly named custom; it does not replace
  Kodi's filter implementation or introduce per-mode/per-resolution quality tiers.
- Kodi already exposes GPU bilinear through its native scaling-method setting.
  Compare that implementation before inventing another scaler. A new option is
  justified only by measured benefit and clean renderer-wide integration.
  FEL enlargement remains a separate processing operation.
- Kodi owns mode selection, whitelist, crop, zoom, aspect and output dimensions.
  Never scale packed Dolby transport bytes. Process on the source grid, then
  resize once before packing/output quantization; preserve true1:1 bypass.
- Master stays exact before final fitting. Each selected scaler defines resized
  pixels; record differences from native explicitly, not as reconstruction loss.
- Rejected trial: a CB1-only bilinear switch bypassed the native fitting callback.
  Its stage-only benefit was fusion with Dolby transport packing, not a new
  universal scaler. Remove the setting/API/trial and retain native Kodi filters
  unless a genuinely renderer-wide alternative demonstrates a useful gain.
- Keep any new scaler only after full-pipeline measurements show useful gains on
  both pinned hosts. Otherwise remove the trial and retain unmodified native scaling,
  accepting lower cadence on small GPUs rather than disguising a downgrade.

## Prior measured spike

1080-to-UHD scale+pack medians: native17.694ms vs fused6.903ms on N100;
native21.679ms vs fused5.143ms on3200U. Tested Intel output identical; AMD maximum
one luma/two chroma12-bit codes. These are not movie FPS or complete fidelity proof.

## Acceptance

1. One native scaling selection, no CB1-only selector/API. Native bilinear and
   convolution filters, invalidation and cancellation tested on vanilla, fallback,
   Standard, P5, Master, Adaptive, Basic/Expert and AI. Record unsupported hardware.
2. Complete image/runtime receipts match. Same media/output/settings A/B tests
   against native control and the earlier stabilized image; report FPS, missed
   HDMI intervals, GPU load and fence-based margins, with queue semantics clear.
3. Intensive AMD/Intel interaction:720p,1080p,near-UHD/cropped Dragon, FEL30,
   Gemini60, zoom and shift, mode changes while zoomed, O cycle, subtitles,
   seek, pause/resume, Home and stop/restart. Restore test settings and minimize TV.
4. Audit all existing GitHub PR intents against current source and tests. Never
   merge/push merely to claim coverage. Record preserved, superseded or missing.
5. Only after the build is credible, dispatch Astra xhigh for a deeply critical
   dossier: native Kodi/component boundaries, cleanliness, HDR10+ native and
   DV conversion plus capability/source labels, HDR10 Expert fidelity, Adaptive
   expansion, native laptop multi-monitor/HDMI behavior and overall priorities.
   Distinguish missing physical HDR10+/laptop hardware from code validation.

## Alternatives

- Native-only is the safe retained alternative if custom has no complete gain.
- A shared explicit optimized bilinear backend is the user-selected experiment.
- Patching native shaders, hidden per-circuit substitutions or returning to a
  forced4K selector are excluded.
