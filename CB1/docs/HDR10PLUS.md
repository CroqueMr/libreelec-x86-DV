# HDR10+ output

Experimental. No HDR10+ display or HDMI analyzer is available for validation.

| Source | Output | Processing |
| --- | --- | --- |
| HDR10+ | HDR10+ | Original pixels and frame-owned FFmpeg metadata. |
| Dolby Vision | HDR10+ | BL/EL/RPU reconstruction, image statistics and representable luminous trims. |
| Unsupported transport | HDR10 | Dynamic metadata cleared; fallback reported. |

Intel and AMD require native HDMI, an admitted dynamic-metadata transaction and
at least 10-bit output. NVIDIA HDR10+ transport is not implemented. HDR10+ to
Dolby Vision is not included.

## Metadata conversion

- Analyze every pixel in the active film area before GUI composition or mapping.
- Measure linear-light channel maxima, average maxRGB and a 256-bin histogram.
- Resolve L1/L3 and applicable L8 or L2 controls through the existing creative resolver.
- Fit one luminous curve, not both trim families. Reject unrepresentable color/spatial controls.
- Validate the transmitted, quantized curve on gray and colored probes with a
  maximum normalized PQ error of 2/1023. This is not an image-wide error guarantee.
- Keep descriptive statistics when a curve cannot be represented; report omitted coverage.
- Do not tone-map pixels before sending the curve. The receiver applies it once.

The curve reference is 992 nits, the largest nonzero value represented by the
selected HDMI field. It does not clip pixels or describe the TV's brightness.
The top transmitted percentile supplies the receiver's normalization because
this payload does not transmit MaxSCL.

Unsupported multi-window, saturation-map and nonmonotone quantized native curves
use HDR10. Packets belong to the same atomic transaction as their framebuffer.
Seek, source changes, rejected imports and teardown clear stale metadata.

## Qualification

Software tests cover byte layout, rational units, curve quantization, invalid
inputs, L1/L3/L2/L8 coverage, frame ownership and HDR10 fallback. Intel N100 and
AMD 3200U GPU witnesses cover active-area statistics, BL/FEL/P5 reconstruction,
cancel/retry and unchanged analyzed pixels. Physical HDR10+ packet latching,
appearance and full playback cadence remain unqualified.

## References

- [SMPTE ST 2094-40](https://pub.smpte.org/pub/st2094-40/st2094-40-2020.pdf).
- FFmpeg `AVDynamicHDRPlus`, its LGPL parser and serializer.
- [Amlogic public HDMI quantization implementation](https://nest-open-source.googlesource.com/manifest_repos/kernel/+/1650886512330522da41d487bb2ce75fd5da5ec8/drivers/amlogic/media/enhancement/amvecm/hdr/am_hdr10_plus.c), cross-checked, not copied.

The original project helpers use GPL-2.0-or-later. Upstream component licenses remain unchanged.
