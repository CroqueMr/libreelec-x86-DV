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
