# HDR10+ playback and conversion

Supported: native HDR10+ playback, Dolby Vision-to-HDR10+ conversion and explicit
metadata-guided HDR10+-to-Dolby Vision conversion.

| Source | Output | Processing |
| --- | --- | --- |
| HDR10+ | HDR10+ | Original pixels and frame-owned FFmpeg metadata. |
| HDR10+ | Dolby Vision, explicit metadata-guided mode | Source pixels retained; compatible source statistics preferred, AI only for incomplete statistics. Authored curves and saturation maps are not translated. |
| Dolby Vision | HDR10+ | BL/EL/RPU reconstruction, image statistics and representable luminous trims. |
| Unsupported transport | HDR10 | Dynamic metadata cleared; fallback reported. |

Intel, AMD and NVIDIA use their supported native-HDMI driver routes, an accepted
dynamic-metadata transaction and at least 10-bit output. Native and converted
HDR10+ share the output contract. HDR10+ stays native by default, including with
a saved general HDR10 AI preference. Dolby Vision conversion requires explicit
selection of the metadata-guided mode and an admitted Dolby Vision output.
[Driver/output matrix](../../docs/cb1/DRIVER-COVERAGE.md).

## Metadata conversion

This section describes **Dolby Vision to HDR10+**. The reverse direction is
described [below](#hdr10-to-dolby-vision).

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

Native and generated metadata support receiver versions 0 and 1. Generated V0
uses measured 5th/10th percentiles. Generated V1 retains its existing 0/255 defaults
for the additional system fields.
Native V1 also accepts its Y99 luminance and Y100nit percentage fields. The latter
is transmitted without luminance quantization; values 101..254 remain rejected.
Changing receiver version cancels pending conversion metadata before reuse.

## HDR10+ to Dolby Vision

- Use validated single-window MaxSCL for the source peak, not the HDR10+ target display peak.
- With a complete valid distribution, estimate mean PQ from that distribution and AverageMaxRGB; content minimum is zero and no GPU/AI analysis is needed.
- With valid sparse statistics, retain compatible source values and use the existing CB1-L1L3 LightGBM estimates for missing values.
- Fold estimated L3 once and emit neutral output L3. Preserve known mastering minimum separately from content minimum.
- Keep decoded pixels without an enhancement grade. The existing DV transport conversion and quantization still apply.
- Do not translate authored Bezier curves, saturation operations or multiple spatial windows into invented DV trims.

Source snapshots and generated metadata belong to the same presented picture.
Invalid or missing metadata after activation retains native fallback until a
source/mode reset, without carrying a previous scene's RPU.
[Full algorithm](ALGORITHMS.md#hdr10-metadata-guided-reference-output).

## Verification

Software tests cover byte layout, rational units, curve quantization, invalid
inputs, L1/L3/L2/L8 coverage, frame ownership and HDR10 fallback. Intel N100 and
AMD 3200U GPU witnesses cover active-area statistics, BL/FEL/P5 reconstruction,
cancel/retry and unchanged analyzed pixels. Driver tests cover packet ownership,
accepted depth, failed commits and restoration. These checks are not Dolby or
HDMI certification.

## References

- [SMPTE ST 2094-40](https://pub.smpte.org/pub/st2094-40/st2094-40-2020.pdf).
- [Qualcomm HDR10+ system field description, section 0170/Table 2](https://patents.google.com/patent/EP4591567A1/en), citing HDR10+ specification 1.6. This is supporting implementation evidence, not HDMI certification.
- FFmpeg `AVDynamicHDRPlus`, its LGPL parser and serializer.
- [Amlogic public HDMI quantization implementation](https://nest-open-source.googlesource.com/manifest_repos/kernel/+/1650886512330522da41d487bb2ce75fd5da5ec8/drivers/amlogic/media/enhancement/amvecm/hdr/am_hdr10_plus.c), cross-checked, not copied.

The original project helpers use GPL-2.0-or-later. Upstream component licenses remain unchanged.
