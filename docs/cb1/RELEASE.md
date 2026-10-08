# R1.0.0 Beta2 - Major performance improvements

Changes since Beta1.

## Playback and performance

- Improved frame pacing for native Dolby Vision and DV Enhanced, including Profile 7 FEL with subtitles.
- Added optional asynchronous frame preparation, limited to one next frame.
- Reduced redundant GPU processing and repeated Enhanced metadata calculations.
- Improved recovery after seeks, pause/resume and rendering-mode changes.
- Fixed DV frame preparation remaining disabled after an HDR10 AI fallback.

## Rendering and controls

- Refined Natural and Signature processing.
- Automatically selects a compatible 2160p Dolby Vision output when the interface runs at 1080p.
- Separate settings for Enhanced Player information and Quick rendering switch.
- **O** cycles through player information, rendering selection and fullscreen video. Kodi's native information panel is also supported.

## Diagnostics

- Added lightweight HDMI and display-route logging, including converter information when available.

Optimizations apply to compatible CB1 rendering paths. Native Kodi and fallback
scheduling remain unchanged.

Settings: **Player > Videos**. Standard Dolby Vision is the default.

## Downloads

- `.img.gz`: clean installation on a USB drive or SSD.
- `.tar`: native LibreELEC update; copy to `/storage/.update/` and restart.
- Source archives: matching build sources, dependency downloads and license notices.
  Not needed for installation.

Source builders should extract both source archives into the same directory.
See [build instructions](BUILD.md).

Keep a backup before updating. Performance depends on hardware and content.

## Known issues

- On lower-powered GPUs such as Intel N100, displaying the GUI over Dolby Vision playback can cause stuttering.
- Some 59.94 FPS Dolby Vision sources still drop frames on N100.
- Enhanced presets need further tuning to produce a more noticeable visual effect.
- Profile 5 black-screen reports on some AMD and Intel Xe configurations remain under investigation.
- Newly enabled Intel families and AMD support require hardware testing.

Report issues with the CPU/GPU, display, connection chain, build version and
`kodi.log`.
