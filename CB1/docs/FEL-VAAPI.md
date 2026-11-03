# FEL hardware upscaling

VAAPI enlarges the half-resolution FEL enhancement layer before CB1 reconstructs the picture. The existing metadata processing, reconstruction and HDMI transport remain unchanged. This applies to FEL input in DV Native, Dolby Vision Adaptive HDR Mapping and DV-to-HDR10 modes. MEL and ordinary HDR10/SDR playback are unaffected.

The adapter uses two reusable Y416 surfaces. Exported DMA-BUF storage is imported as RGBA16 UNORM without a CPU pixel copy. The renderer retains each surface until its existing source-read fence completes. It does not queue additional reconstructed frames.

VAAPI is selected by default where supported. Unsupported output formats, failed imports or failed VPP operations use bilinear GPU FEL reconstruction. Outside the one-ahead path below, a temporarily occupied pool also uses bilinear for the current picture.

Hardware interpolation differs slightly from shader interpolation. This changes enhancement-layer sampling, not Dolby Vision metadata or artistic trims.

The adapter requires VAAPI VideoProc, Y416 output allocation and EGL DMA-BUF import. It probes these operations rather than matching CPU model names. No proprietary Dolby library is used.

## Bounded FEL preparation

Authored Dolby Vision Adaptive HDR Mapping with asynchronous preparation
can prepare one queued FEL layer ahead in the same two surfaces. Import waits for
VPP completion; source-read fences still retain each lease. Stream, picture,
timestamp, pool and processing revisions must match before reuse. Menus, pause,
seeks and mode changes invalidate ineligible lookahead. A busy pool waits rather
than changing the selected filter on this path. Native, Master, HDR10 conversion
and AI do not use this lookahead.

## Optional reconstruction filter

**Kodi > Player > Videos > FEL upscaling**, Expert level:

| Choice | EL enlargement |
| --- | --- |
| VAAPI | Hardware VPP upscaling; bilinear GPU fallback when unavailable or busy |
| Bilinear (GPU) | Bilinear sampling in the existing shader; VPP is bypassed |
| Reference (GPU) | Master's separable FEL interpolation, with FP32 intermediates preserving integer overshoot; VPP is bypassed |

The setting affects the FEL enhancement layer only, before reconstruction. It
does not change BL scaling, the input-chroma recipe, decoding, layer pairing or source metadata.
Non-FEL sources are unaffected. Native, HDR10 Basic/Expert and Adaptive HDR Mapping
use the choice when they reconstruct FEL. A policy change invalidates the affected
import and pending-frame identity. Switching back to VAAPI restores VPP selection.

Accepted-frame diagnostics distinguish the requested choice, executed filter and
backend. VAAPI does not claim a particular driver interpolation kernel. Player
information shows the method used by the accepted frame, not just the preference.
Master keeps its fixed reference filters regardless of this setting. The Reference
choice shares only FEL enlargement, not Master reconstruction. It supports raw
4:2:0 EL planes at half BL size; same-size planes bypass enlargement. Unsupported
layouts or ratios are rejected explicitly rather than labelled Reference.
Reference requires additional GPU passes and memory. Software-GPU checks do
not establish hardware VPP cost, presentation margin or N100 performance.
