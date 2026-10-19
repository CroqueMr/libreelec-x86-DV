# Beta4 Debug diagnostics

Diagnostics are automatic in `kodi.log`. Kodi's global debug mode is not required.

- Correlated source/frame identity, BL/FEL dimensions, L1/L5, OSD, Fast and async state.
- Final pre-swap framebuffer samples, all three metadata copies and packet CRCs.
- Submitted GBM framebuffer layout and live DRM plane, connector and CRTC properties.
- Measured readback and atomic-submit durations.

Probes run at startup, after OSD/source changes and every 10 seconds. They are limited to 32 per stream, at least 500 ms apart. The shared diagnostic budget is capped at 128 regular lines per 30 seconds.

Framebuffer samples are not a physical HDMI capture. An accepted asynchronous submission does not prove that the sampled framebuffer is already displayed; the log reports pending state explicitly.

GPU readbacks can cause brief playback stalls. Use a normal release for performance comparisons.

For developers, `DVBRIDGE_DEBUG_DIAGNOSTICS=0` disables the extra probes. `DVBRIDGE_DIAGNOSTICS=0` disables the full diagnostic supplement. A normal build omits `projects/Generic/filesystem/usr/share/kodi/system/dvbridge-debug`.
