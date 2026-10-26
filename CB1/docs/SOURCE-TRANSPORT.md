# Source transport and shared reshaping

| Change | Scope | Result |
| --- | --- | --- |
| Source-domain packed output | Eligible 4K single-layer and MEL Dolby Vision output, including metadata-based Adaptive HDR Mapping | Avoid source colour decoding, PQ round trips and canonical RGB re-encoding |
| Identical MMR interval compaction | Shared libplacebo reshaping in Dolby Vision and HDR10 conversion circuits | Remove redundant per-pixel segment selection |
| Optional bilinear input chroma scaling | CB1 Native/Dolby Vision Adaptive HDR Mapping, DV to HDR10 and HDR10 to DV AI, including intermediate RGB, GUI and enlarged input | Avoid separate chroma convolution; Off restores the reference chroma filter without disabling other optimizations |
| Direct spatial descriptor buffer | HDR10 to Dolby Vision AI, Reference and Adaptive | Remove the intermediate descriptor texture and framebuffer-to-buffer copy |
| Fused AI transport with borders | HDR10 to Reference Dolby Vision AI, unscaled active pictures | Write directly into the packed output without a padded RGB intermediate |

## Pixel and metadata contract

Source-domain output packs the reconstructed opponent values with the original
Q13 YCC and Q14 LMS matrices. The matrices must be exactly representable,
invertible and within the signed wire range. The representation must use PQ,
12-bit full-range samples and canonical black offsets. Output geometry remains
3840x2160 without scaling or translation.

CM2.9/CM4 blocks, active area, CRC, repetition and presentation transactions use
the existing serializer. Native FEL transport remains unchanged. sRGB GUI
composition uses the existing inverse source transform; PQ GUI and unsupported
representations retain canonical RGB composition. Kodi selects compatible
transport and GUI optimizations automatically.

MMR intervals are merged only when their methods, orders, constants and complete
coefficient arrays are bit-identical. Original outer bounds and arithmetic are
preserved. Distinct intervals retain the general shader. This specialization
is shared GLSL code, without an Intel-specific backend or CPU image processing.

Each circuit fixes its input-chroma filter at the libplacebo input stage.
Standard and conversions retain their qualified performance recipe; Master
retains its reference filter. Input-chroma filtering does not change metadata,
the FEL luma enlargement filter or output-plane sampling. A matched renderer
header/library pair is required.

Master-to-Standard recovery is a separate opt-in playback policy, off by default.
It observes accepted presentation readiness; it does not change a filter inside
Master. Native Kodi, SDR,3D and vanilla fallback retain their normal scheduling.

## Verification boundary

HDR10 AI spatial analysis writes the same compact descriptors and motion samples
directly into an SSBO. Reduction order, model inputs, asynchronous retirement and
fallback thresholds remain unchanged.

Fused AI transport also accepts unscaled active pictures centered in the 4K
transport frame. Scaled active pictures retain RGB preparation and resolve.
This extension follows the renderer's existing `optimized_dv` preference.
GPU fixtures preserve RGB input bytes exactly; P010/P012 fixtures differ by at
most one logical 12-bit video code. Border and metadata bytes remain identical.
These limits describe the tested fixtures, not an exhaustive image guarantee.

Metadata tests cover source/canonical isolation, CM4/L5 bytes, rejection and
presentation state. GPU controls cover P8/MEL source codes, GUI transitions and
MMR boundaries and coefficient updates. Existing Native/Basic frozen controls
remain unchanged. These controls do not establish HDMI cadence or TV conformance.

The source-domain design extends the previously attributed YBLOD pre2 transport
approach through CB1's existing libplacebo path. No OpenCL backend is added.
