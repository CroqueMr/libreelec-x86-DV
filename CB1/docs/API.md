# Player integration

CB1 is an in-process C library. The current consumer is Kodi's GBM/GLES path.

| Header | Interface |
| --- | --- |
| `dvbridge_core.h` | Source reconstruction and output preparation |
| `dvbridge_policy.h` | Output mode and manual display profile |
| `dvbridge_render.h` | Frame-bound processing and presentation transactions |
| `dvbridge_creative.h` | CM2.9/CM4 processing and metadata coverage |
| `cb1_hdr10_ai.h` | Optional asynchronous HDR10 analysis and inference |
| `cb1_circuit.h` | Engine and circuit version identifiers |
| `cb1_master_reference.h` | Validated raw integer reference descriptor |

The caller binds the stream, picture, policy revision and timestamp to each
input. It owns the graphics context and output surfaces. Prepared output becomes
active only after accepted presentation; canceled work does not replace the
committed state.

FFmpeg metadata and libplacebo frame types cross the interface. This is not a
stable binary plugin ABI. Use the dependency revisions and patches from the same
CB1 lock. Other players require a native adapter.

CB1 does not control audio, input devices, player menus or HDMI connectors.

`dvbridge_render_master_reference` prepares the explicit reference circuit.
`CB1_MASTER_READY` means prepared, not presented. Retain source leases and use
the normal render candidate, presentation commit and GPU retirement. A null
target or unqualified colour-converted route is unsupported, not Standard.
The raw descriptor is copied into dispatch variables before this call returns.
See [Master Reference](MASTER-REFERENCE.md) for admission and output contracts.

Direct-DV Adaptive uses policy API 9. Both preparation entries may
return Pending. Poll before resolving; commit only the matching presented
identity and resolve serial. Generation 3 denotes reconstructed Adaptive HDR Mapping output
with measured LMS/PQ statistics. Authored-Dolby Vision Adaptive HDR Mapping updates its authored
scene analysis through the applied curve; source L3 is folded once and
creative trims remain authored. HDR10 AI Adaptive HDR Mapping keeps absolute analysis.
Generation 2 retains source metadata;
generation 1 remains the legacy AI analysis contract. Algorithm/model names in
snapshots describe the committed producer, not physical display measurements.

READY can retain a source-sized intermediate until final scale/pack. RGB consumers
call `dvbridge_render_dv_policy_rgb` for a cached output-sized PQ image. Repeated
access preserves caller composition; metadata and presentation identity are unchanged.

`dvbridge_render_dv_policy_wait` accepts a bounded timeout in nanoseconds for
authored Adaptive pixel analysis. `dvbridge_render_dv_policy_poll` remains
nonblocking. Neither call advances an unpresented picture or releases an active
source lease.

## Source-domain transport

`dvbridge_prepare_source_output` prepares metadata for pixels retained in the
source opponent domain. It preserves exactly representable Q13/Q14 colour
matrices and the source diagonal. It accepts qualified source-sized and placed
pictures fitted into a 3840x2160 carrier, PQ, a 12-bit full-range representation
and canonical black offsets. Rejection
does not advance presentation state.

The optimized packed renderer uses this path for compatible single-layer and
MEL sources. Active FEL reconstruction retains its existing route. Unsupported
source representations or GUI composition use canonical RGB output.
Admission is automatic; no separate player setting is required. HDR10
conversion and AI output retain their existing routing.

Each circuit owns one fixed input-chroma recipe. Standard and conversion entry
points use their qualified linear chroma filter; Master entry points retain the
exact reference filter. There is no mutable Fast preference or renderer setter.
FEL enlargement, metadata and luma retain their circuit-specific contracts.
Native Kodi and vanilla fallback do not use these CB1 recipes.

## Overlay visibility

HDR10 Adaptive HDR Mapping can fuse PQ conversion, expansion, content statistics and RGB8
transport. The full-precision movie output is written directly to the borrowed
scanout target; metadata insertion uses the existing final framebuffer. Native
PQ is retained for whole-frame source-bound rejection. Packed-only output has
no RGB intermediate. Late GUI changes require normal cancellation and preparation
through the existing composition path.
Every active pixel contributes to output statistics; 2x2 records quantize PQ
statistics to 16 bits. Auxiliary GUI/recovery PQ storage may be half-float.
Neither auxiliary representation is used to quantize the directly packed movie.

`cb1_hdr10_ai_set_coalesced_bounds` selects exact coalesced bounds reduction and
compact source-plane records. Kodi enables it only for HDR10 Adaptive HDR Mapping, after a
stream or policy reset. Pending work cannot be reconfigured. Unsupported compact
storage retains the original record format. AI Reference keeps the original
analysis configuration.

`dvbridge_render_dv_policy_update_overlay` updates borrowed GUI resources and
visibility on unresolved authored-DV or HDR10 AI Adaptive HDR Mapping work. The player must prove the
same source, geometry and policy transaction before calling it. Content analysis
is retained; visibility changes refresh only the outgoing L5 candidate. Resolved,
retiring, quarantined and AI Reference work are not eligible.
GUI-free packed authored Adaptive may omit its expanded RGB cache. The first
late overlay materializes that cache from the retained reconstruction once;
later redraws reuse it without repeating source reconstruction or analysis.
Native source-bound recovery remains available. HDR10 AI is unchanged.
GUI may be sampled during preparation for transport prepacking, but never enters
content statistics. Keep submitted resources valid through completion and order
updates on the same GL context. Every late update invalidates prepacked GUI;
resolve then uses the latest descriptors with the ordinary composition path.

`dvbridge_renderer_set_overlay_visible` (or `dvbridge_set_overlay_visible` on a
core context) tells CB1 that GUI or subtitles will be composed over the next
prepared picture. While set, the transmitted L5 reports the full raster, so the
display does not mask or crop controls and subtitles drawn in letterbox bars.
Only the outgoing DV metadata copy changes: the active-area video mask, which
runs before overlay composition, `dvbridge_active_area`, policy snapshots and
the caller's RPU keep the source margins. A change from the presented state
sets the scene-refresh flag, including on a paused, repeated picture. Invalid,
truncated or duplicate L5 is still rejected before any output is produced. The
default is off; HDR10 output is unaffected. Kodi sets it from GUI and subtitle
visibility.
