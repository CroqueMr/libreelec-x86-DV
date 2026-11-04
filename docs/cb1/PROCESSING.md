# Processing and metadata

CB1 reconstructs source images, applies the selected processing mode and prepares
output metadata. Kodi retains decoding, audio, subtitles and playback timing.

Native HDR10/HLG/SDR and [stereoscopic 3D](3D.md) remain outside CB1 conversion.
See [hardware support](HARDWARE.md) for supported integrated and dedicated GPUs.

## Reference and Master Reference

Both modes reconstruct the Dolby Vision source, including the applicable matched
FEL, and send TV-Led Dolby Vision with the source display-management metadata.

| Mode | Reconstruction | TV profile |
| --- | --- | --- |
| Dolby Vision Reference | Fixed performance-oriented reconstruction and input-chroma interpolation | Not required |
| Dolby Vision Master Reference | Exact source-domain reference arithmetic and dedicated FEL filters | Not required |

Reference accepts very small image differences for substantially higher rendering
performance. Master Reference aims for bit-perfect playback within its admitted
source/output contract. It does not establish equality to a certified player's
physical HDMI output. Resizing is a spatial operation, not an identity transform.

Master Reference has its own format checks. Global profile support does not mean
every profile is accepted by every rendering mode. Unsupported Master inputs use
the existing output-selection fallback; they are not silently reconstructed by
the reference algorithm.

The source-tree focus is [Master Reference](../../CB1/docs/MASTER-REFERENCE.md).
Expert settings select YCbCr or IPT-PQc2 Master output. This changes the payload
inside the RGB8 Dolby Vision tunnel, not the HDMI container. Profile 5 uses the
shared direct IPT path in both Master variants.

## Metadata use

| Metadata | Reference / Master | HDR10 Rendering | HDR10 Rendering Reference | Adaptive |
| --- | --- | --- | --- | --- |
| RPU mapping / residual | Reconstruct source | Reconstruct source | Reconstruct source | Reconstruct source |
| L1 scene min/max/average | Forward to TV | Scene guidance | Scene guidance | Expansion strength and output scene descriptors |
| L3 offsets | Forward to TV | No creative trim pass | Retained, not executed | Apply once before curve construction |
| L2 CM2.9 trims | Forward to TV | Not applied | Compatible creative controls | Guide added light and color restraint |
| L5 active area | Preserve picture/borders | Preserve picture/borders | Preserve picture/borders | Exclude borders from expansion/analysis |
| L6 mastering / light levels | Forward when applicable | Source reference / HDR10 signaling | Static fallback / signaling | Source descriptors |
| L8 CM4 trims | Forward to TV | Not applied | Retained; available L2 compatibility only | Target responses and color restraint |
| L9 / L10 | Forward when applicable | No creative anchor selection | Source mastering gamut; no full L8 render | Resolve compatible creative anchors |

Visible menus and subtitles use full-raster output L5 signaling so the TV does
not hide them in the black bars. This does not expand the source picture.

## Units

L1 values are **12-bit PQ codes, not nits**. With `E` as inverse ST 2084:

```text
scene luminance = E(L1_code / 4095)
```

`M` is the source mastering/reference maximum. `T` is the configured display
peak. Neither is a direct measurement of the current scene or the physical TV.

## Dolby Vision to HDR10 Rendering

HDR10 Rendering uses source mastering information and valid scene statistics. It reconstructs
the Dolby Vision image, applies scene-guided spline tone mapping and perceptual
gamut mapping, then encodes BT.2020/PQ HDR10.

- No manual TV profile and no invented display peak.
- No L2/L8 creative trim pass.
- No inverse tone mapping to force dim scenes to the mastering maximum.
- Missing scene statistics use valid static source descriptors.

Dynamic Dolby Vision metadata cannot be transported as dynamic metadata in a
standard HDR10 signal. Its contribution must be reflected in pixels before output.

## Dolby Vision to HDR10 Rendering Reference

HDR10 Rendering Reference maps to its separately configured display peak `T`,
black floor and gamut. Enter the peak manually and choose an OLED/LCD/projector
black preset or a custom black level. Presets are estimates, not measurements.
P3-D65 is the default gamut. Disable the TV's dynamic tone mapping for this mode
to avoid a second dynamic mapper.

Valid raw L1 maximum/average guide the explicit PQ-domain curve. L3 offsets are
not added in this runtime. L1 minimum is descriptive, not a physical display-black
measurement. Missing or unusable L1 uses valid static descriptors from this frame;
corrupt or contradictory metadata remains guarded.

The native ST2094-10 curve compresses scenes above the target; the native clip
curve avoids inverse expansion otherwise. Both use the configured black floor
and display peak. Compatible L2 primary controls shape the tone LUT with protected
black/peak endpoints, rather than a linear RGB offset. Chroma processing is bounded
in the target gamut. L8-only sources do not receive a full CM4 creative render;
L8 spatial and secondary controls remain unexecuted.

Mapping is applied once. The final BT.2020/PQ output and scaling do not add a
second scene tone map. Output HDR10 metadata describes the virtual rendering
target; unknown MaxCLL/MaxFALL remain zero rather than invented measurements.
A target above the source mastering peak does not automatically brighten the
whole film to that target.

## Adaptive HDR Mapping from Dolby Vision

Adaptive transforms reconstructed linear BT.2020 pixels, then updates scene
metadata to describe the transformed image. It is not a metadata-only filter.
The TV still performs its final Dolby Vision display mapping.

### Source guidance

- L1/L3 provide effective scene brightness.
- Compatible L8 anchors take precedence over L2; up to two anchors bracket the
  display reference using PQ-distance weights.
- Trim responses are evaluated in their own target domain, rather than applying
  the creative grade twice.
- With usable L1 but no creative trims, neutral trim guidance permits expansion.
  No L2/L8 creative controls are fabricated.
- Missing usable scene analysis or failed source-bound validation retains the
  original image/metadata pair.

### Expansion

For a scene peak `high`, average `mid` and smoothstep `H`, the curve builds 257
knots. Trim retention `r` is bounded to `[0.5, 1.15]`; absent trims use `r=1`.

```text
S = H(100, 400, high) * (1 - 0.5*H(0.04, 0.30, mid/max(high, epsilon)))
exponent = 2 + 2*H(0.04, 0.30, mid/max(high, epsilon))
reference = min(M, max(100, high))
```

The integrated retention curve is normalized at `reference`. When the TV has
headroom above that scene reference, highlights receive additional light.
A bounded midtone term can add up to the profile's `0.12*(M-10)` scale, weighted
by scene strength, trim retention and a smooth midtone window. This is a curve
coefficient, not a fixed 12% increase to every pixel.

Color-control magnitudes restrain added light rather than applying another
saturation/hue grade. A common RGB gain preserves linear chromaticity. A soft
shoulder limits added light to available channel headroom without reducing
source values already above the display target.

Pixels at or below **10 nits**, and pixels outside L5, bypass expansion. Dark
scenes are not automatically forced to fill the TV's range.

### Output metadata and stability

Effective authored L1 passes through the applied neutral-axis curve. Output L3
is neutral after folding; compatible source trims remain present. The declared
envelope covers the original source and transformed output.

Frame extrema validate the output but do not replace authored L1 every frame.
Curve/color changes share a time-based budget, advanced only by matching
presented pictures. This limits brightness pumping; seeks and mode changes reset
the temporal state. GUI and subtitles are composed after content analysis.

The current display path uses FP16 intermediates where selected by this Adaptive
policy. It is separate from Master Reference's exact reconstruction contract.

## HDR10 to Dolby Vision AI

One bundled **CB1-L1L3 0.1 LightGBM model** serves Reference and Adaptive AI.
GPU analysis builds luminance, color, spatial and temporal descriptors. A
normalized 222-feature vector produces L1/L3 estimates; output projection keeps
the predictions ordered and covers the measured peak.

Inference uses one CPU thread, without Python during playback. Lookahead and
scene handling associate predictions with their corresponding pictures. Seeks
and mode changes invalidate old predictions.

### Reference AI

Reference adds no enhancement grade. It converts the HDR10 source into the
Dolby Vision transport and sends estimated L1/L3 with the corresponding image.
It does not recover the studio's original RPU, generate authored L2/L8 trims or
guarantee a visual improvement over HDR10 on every display. Transport conversion
is not a promise of bit-identical HDR10 storage.

### Adaptive AI

AI L1/L3 guide the shared expansion executor. There are no authored L2/L8
anchors, so retention is neutral and trim-derived color restraint is absent.
RC3 uses the same scene-guided expansion logic as authored-Dolby Vision Adaptive,
including its bounded midtone term, with neutral trim retention and no invented
creative anchors. Shadows at or below 10 nits stay protected. Expansion depends
on scene guidance and display headroom, not just whether the display peak exceeds
the source mastering maximum.

Output L1 follows the applied scene curve, while measured output statistics
validate the bounds; L3 is not applied twice. Unknown
mastering remains unknown; a conservative internal envelope is not exposed as
a fabricated mastering claim.

Reference AI and Adaptive AI therefore share the model, but do not apply the
same pixel treatment. No claim of equivalence to authored Dolby Vision is made.

## HDR10+ to Dolby Vision

This mode preserves the decoded picture and uses the existing Reference output.
For a complete single-window source, MaxSCL supplies the scene peak and the
weighted percentile distribution plus AverageMaxRGB estimate mean PQ. Known mastering
minimum is preserved separately; content minimum defaults to zero.

Complete source statistics avoid GPU image analysis. Incomplete statistics use
bounded estimates, with source-translated and estimated values kept separate. Scene descriptions are committed only with
their matching presented picture. Invalid or missing metadata after activation
keeps native fallback until a source or mode reset, avoiding repeated switching.

HDR10+ target curves, saturation operations and multiple spatial windows are not
universally translated to Dolby Vision. Native HDR10+ playback remains Kodi's
default path and does not activate this conversion.

## Performance controls and output

Each circuit owns its input-chroma recipe. Async prepares at most one future
picture without changing native Kodi/fallback playback scheduling.
Master keeps its Reference GPU FEL filters. From RC3, other applicable modes
select VAAPI, Bilinear (GPU) or Reference (GPU).
[Compare FEL upscalers](FEL-UPSCALING.md), including the Nearest neighbour method removed
in RC3. [Settings](PLAYBACK.md).

Dolby Vision uses an RGB8 byte tunnel carrying higher-precision video and
metadata, not ordinary 8-bit SDR. HDR10 conversion requires a driver-validated
10-bit-or-higher output. [Hardware](HARDWARE.md).

Full source equations and execution details are in
[CB1 algorithms](../../CB1/docs/ALGORITHMS.md).
