# HDR10+ integration

Status: experimental, private candidate. Software checks and component builds do not establish HDMI reception on a television. No compatible HDR10+ sink is available for physical validation.

## Contracts

Native HDR10+ retains the source image and its FFmpeg side data. HDMI carries a 27-byte vendor payload, not the HEVC T.35 payload. Unsupported metadata representations use HDR10 rather than silently removing fields.

Native curves are admitted only with a monotone control polygon after HDMI quantization. This sufficient condition is deliberately conservative: other polygons use the HDR10 fallback even if a fuller curve analysis could prove them monotone.

DV conversion reconstructs BL/EL/RPU first and analyzes the resulting image before GUI composition. L1/L3 are guidance, not replacements for linear RGB statistics. Optional luminous trims require a representable, quantization-tested curve. Unrepresentable color and spatial trims are not claimed as applied.

## Modes

| Input | Output | Processing |
| --- | --- | --- |
| HDR10+ | HDR10+ | Original pixels and dynamic metadata, serialized for HDMI. |
| Dolby Vision | HDR10+ | Reconstructed pixels, measured linear RGB statistics, optional representable luminous curve. |
| Either, unsupported HDMI path | HDR10 | Dynamic metadata removed; the player reports the fallback. |

The private Intel and AMD DRM backends require a compatible HDMI sink, a validated dynamic-metadata property and at least 10-bit output. NVIDIA HDR10+ transport is not implemented. Existing Dolby Vision, HDR10 and SDR algorithms are unchanged.

On AMD, dynamic-packet updates require the primary surface in the same atomic transaction. Packet-only commits are rejected instead of acknowledging metadata that the hardware has not received.

## Dolby Vision conversion

- Analyze every pixel in the selected film area, before GUI composition. Keep the analysis and packet attached to the same picture identity.
- Measure channel maxima, average maxRGB and a 256-bin linear-light distribution. L1 and L3 guide the response; measured statistics are not inferred from those metadata.
- Resolve L8 luminous controls first, or L2 when applicable, through the existing creative-mapping code. Do not apply both families to the same curve.
- Fit a monotone HDR10+ Bezier curve, then validate the quantized HDMI representation on gray and colored probes. Maximum accepted error is 2/1023 in normalized PQ on those probes, not an image-wide guarantee.
- Validation uses receive-side integer expansion, including the maximum knee code. An unrepresentable sub-target endpoint uses descriptive statistics, not a curve that would incorrectly lift it to the curve reference.
- Retain measured descriptive metadata when a curve or trim cannot be represented. Report the omitted coverage. Color, saturation and spatial controls are not silently labeled as supported.
- Leave the reconstructed pixels unmapped: the receiver applies the transmitted curve once. There is no additional Basic/Expert tone-map pass.

The curve reference is 992 nits, the highest nonzero reference representable in the HDMI field used here. This is not a pixel clipping limit or a declaration of the television's brightness. The receiver remains responsible for mapping to its display. The top transmitted distribution percentile supplies the fitting normalization because this HDMI payload does not carry MaxSCL.

## Verification limits

Software tests cover packet bytes, quantization, invalid inputs, source immutability, BL/FEL/P5 reconstruction, trim coverage, frame ownership, transitions and HDR10 fallback. GLES analysis is tested on llvmpipe. These checks do not validate TV appearance, hardware frame latching or Intel/AMD playback performance. A compatible display or HDMI analyzer is required before removing the experimental status.

## Independent references

- SMPTE ST 2094-40:2020, application 4, version 1: https://pub.smpte.org/pub/st2094-40/st2094-40-2020.pdf
- FFmpeg `AVDynamicHDRPlus` and T.35 parser/serializer, LGPL-2.1-or-later.
- HDMI field layout and quantization cross-checked against the Amlogic public implementation (GPL-2.0-or-later OR MIT), not copied:
  - https://nest-open-source.googlesource.com/manifest_repos/kernel/+/1650886512330522da41d487bb2ce75fd5da5ec8/drivers/amlogic/media/enhancement/amvecm/hdr/am_hdr10_plus.c
  - https://nest-open-source.googlesource.com/manifest_repos/kernel/+/1650886512330522da41d487bb2ce75fd5da5ec8/drivers/amlogic/media/vout/hdmitx/hdmi_tx_20/hdmi_tx_main.c

No Hades implementation is used for this feature. Existing third-party licenses and credits remain unchanged. The independent transport helper is GPL-2.0-or-later; current linked CB1 still contains GPLv3-only processing code.
