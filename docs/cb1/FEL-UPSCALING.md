# FEL upscaling

FEL upscaling enlarges the Dolby Vision enhancement layer before combining it
with the base layer. It is **not** the final video upscale: output resolution,
zoom and whole-picture scaling remain controlled by Kodi.
MEL and sources without FEL do not use these filters.

## Filters

| Method | Processing | Use |
| --- | --- | --- |
| **VAAPI** | The GPU's video-processing hardware enlarges the FEL. Interpolation depends on the driver. | Default where supported. Falls back to GPU bilinear when VPP cannot be used. |
| **Bilinear (GPU)** | Blends neighbouring samples directly in the reconstruction shader. | Lightweight alternative without the block replication of Nearest neighbour; also used when VAAPI is unavailable. |
| **Reference (GPU)** | Uses the reference FEL interpolation from Master Reference, with dedicated GPU filtering passes. | Higher reconstruction fidelity at additional GPU and memory cost. Selecting this filter alone does not select the complete Master pipeline. |
| **Nearest neighbour - removed in RC3** | Repeats each sample instead of interpolating between samples. Half-size FEL samples become 2x2 blocks. | Poor quality/performance trade-off: visible stair-stepping and no meaningful speed advantage over bilinear in the matched comparison. Replaced by GPU bilinear. |

## Visual comparison

Same frame and crop from a FEL detail pattern, reconstructed on an Intel N100.
All crops use the same contrast amplification and 3x integer enlargement.

| VAAPI | Bilinear (GPU) | Nearest neighbour - removed | Master Reference |
| --- | --- | --- | --- |
| ![VAAPI FEL reconstruction](images/fel-vaapi.png) | ![GPU bilinear FEL reconstruction](images/fel-bilinear.png) | ![Former nearest-neighbour FEL reconstruction](images/fel-nearest.png) | ![Master Reference FEL reconstruction](images/fel-reference.png) |

These are pre-HDMI luma readbacks, not photographs of HDR playback. Reference
shows the complete Master reconstruction; this is not a filter-only comparison.
The pattern exposes interpolation differences more clearly than typical film
content. Source metadata and output metadata packets match across these examples.

## Selection

In RC3: **Settings > Player > Videos > CB1 - Dolby Vision engine > FEL upscaling**
(Expert level).

Reference, Adaptive HDR Mapping and applicable HDR conversions use the selected
FEL method. **Master Reference always keeps its own Reference GPU filters**,
independently of this setting. Player information reports the method actually
used, not just the saved preference.

[Rendering modes](PROCESSING.md) | [Settings](PLAYBACK.md) |
[VAAPI implementation details](../../CB1/docs/FEL-VAAPI.md)
