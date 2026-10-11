# Source transport and shared reshaping

| Change | Scope | Result |
| --- | --- | --- |
| Source-domain packed output | Eligible 4K single-layer and MEL Dolby Vision output, including metadata-based Enhanced | Avoid source colour decoding, PQ round trips and canonical RGB re-encoding |
| Identical MMR interval compaction | Shared libplacebo reshaping in Dolby Vision and HDR10 conversion circuits | Remove redundant per-pixel segment selection |
| Optional bilinear input chroma scaling | CB1 Native/Enhanced DV, DV to HDR10 and HDR10 to DV AI, including intermediate RGB, GUI and enlarged input | Avoid separate chroma convolution; Off restores the reference chroma filter without disabling other optimizations |

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

The optional bilinear filter changes input chroma interpolation, not metadata or
the luma enlargement filter, including FEL luma. Bilinear is not pixel-identical
to Lanczos. It is selected per chroma plane in the shared libplacebo input stage;
RGB composition and output-plane sampling remain unchanged. A matched private
renderer header/library pair is required.
Kodi exposes one Advanced setting, `Dolby Vision fast rendering`,
disabled by default. It affects the next prepared picture and does not change
VAAPI FEL admission, GUI composition or metadata. Native Kodi playback, SDR,
3D and vanilla fallback do not enable it.

## Verification boundary

Metadata tests cover source/canonical isolation, CM4/L5 bytes, rejection and
presentation state. GPU controls cover P8/MEL source codes, GUI transitions and
MMR boundaries and coefficient updates. Existing Native/Basic frozen controls
remain unchanged. These controls do not establish HDMI cadence or TV conformance.

The source-domain design extends the previously attributed YBLOD pre2 transport
approach through CB1's existing libplacebo path. No OpenCL backend is added.
