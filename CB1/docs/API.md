# Player integration

CB1 is an in-process C library. The current consumer is Kodi's GBM/GLES path.

| Header | Interface |
| --- | --- |
| `dvbridge_core.h` | Source reconstruction and output preparation |
| `dvbridge_policy.h` | Output mode, preset and manual display profile |
| `dvbridge_render.h` | Frame-bound processing and presentation transactions |
| `dvbridge_creative.h` | CM2.9/CM4 processing and metadata coverage |
| `cb1_hdr10_ai.h` | Optional asynchronous HDR10 analysis and inference |
| `cb1_circuit.h` | Engine and circuit version identifiers |

The caller binds the stream, picture, policy revision and timestamp to each
input. It owns the graphics context and output surfaces. Prepared output becomes
active only after accepted presentation; canceled work does not replace the
committed state.

FFmpeg metadata and libplacebo frame types cross the interface. This is not a
stable binary plugin ABI. Use the dependency revisions and patches from the same
CB1 lock. Other players require a native adapter.

CB1 does not control audio, input devices, player menus or HDMI connectors.

## Source-domain transport

`dvbridge_prepare_source_output` prepares metadata for pixels retained in the
source opponent domain. It preserves exactly representable Q13/Q14 colour
matrices and the source diagonal. It requires full-raster 3840x2160 1:1 geometry,
PQ, a 12-bit full-range representation and canonical black offsets. Rejection
does not advance presentation state.

The optimized packed renderer uses this path for compatible single-layer and
MEL sources. Active FEL reconstruction retains its existing route. Incompatible
geometry, source representation or GUI composition uses canonical RGB output.
Admission is automatic; no separate player setting is required. HDR10
conversion and AI output retain their existing routing.

`dvbridge_renderer_set_fast_chroma` selects bilinear input chroma enlargement in
every CB1 circuit, independently of optimized transport admission. This includes
DV to HDR10 and HDR10 to DV AI. Off restores the reference chroma filter. Luma,
including enlarged FEL luma, RGB/output scaling, reshaping, FEL VPP, metadata and
intermediate precision remain unchanged. The default library preference is off;
Kodi supplies its user preference. Native Kodi and vanilla fallback do not use it.
