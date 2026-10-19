# R1.0.0 Beta4 Debug

Changes since Beta4.

## Diagnostics

- Automatic diagnostics in `kodi.log`; no debug setting required.
- Added correlated BL/FEL, L1/L5, Fast/async and OSD state.
- Added final-framebuffer metadata recovery, copy/CRC checks, video samples, GBM layout and live DRM properties.
- Bounded probes at startup, OSD transitions and during playback. Readback time is recorded.

## Playback and compatibility

- Fixed redundant processing for scaled Dolby Vision Adaptive sources, including 1080p to 4K.
- Improved separate BL/EL association in MKV, dual-track MP4 and dual-PID TS/M2TS.
- Preserved native SDR tone mapping when HDR output signalling is rejected.
- Improved output-surface cleanup and recovery after failed window creation.
- Improved FEL decoder renewal when the VAAPI wrapper changes but the display device remains the same.
- Corrected valid HDMI EDID extension-count overrides shared by the player and drivers.
- Added regression coverage for 3840×2160 Dolby Vision mode selection.

## Known issues

- J4125 black video without the OSD remains under investigation. This build adds evidence, not a confirmed fix.
- Diagnostic GPU readbacks can briefly interrupt playback. Do not use this build for performance comparisons.
- Compatibility fixes still require confirmation on affected hardware.

Report the CPU/GPU, display, HDMI route, build version and `kodi.log`.
