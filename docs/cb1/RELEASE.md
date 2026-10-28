# R1.0.0 RC1 - Major performance improvements, HDR10+ and wider hardware support

Changes since Beta5.

## Performance

- **Major AMD performance improvements**, including Standard, Master Reference and conversion pipelines.
- Reduced redundant rendering passes, surface imports and memory copies.
- Improved FEL decoding, BL/EL scheduling and asynchronous frame preparation.
- Optimized HDR10-to-Dolby Vision AI and Dolby Vision-to-HDR10 Basic/Expert.
- Dedicated Profile 5 IPT paths: accurate processing in Master Reference and a lighter implementation in Standard.

## Dolby Vision

- Extended **TV-Led V1 compatibility** across Intel, AMD and NVIDIA.
- Improved Standard and Master Reference resource management and presentation timing.
- Removed the Fast On/Off/Auto selector. Each rendering mode now uses its own fixed processing path.
- Added optional automatic **Master Reference → Standard** recovery, disabled by default.
- Added **Disable L2 trims**, disabled by default and limited to Standard and Master Reference.

## HDR10+

- Added **native HDR10+ playback** and **Dolby Vision-to-HDR10+ conversion**.
- Added output paths for Intel, AMD and NVIDIA, including the separate Pascal image.
- Added receiver V0/V1 handling and frame-associated dynamic metadata.
- Improved output-depth validation, packet synchronization and HDR10+/HDR10/Dolby Vision/SDR transitions.
- Added HDR10+ capability reporting in Kodi.

## Native Kodi integration

- Process video at source resolution before using **Kodi’s native scaler and filters**.
- Preserve native zoom, view modes, picture placement, resolution whitelist and refresh-rate selection.
- Keep native playback and fallback behavior outside active CB1 processing.

## Playback and stability

- Corrected chroma positioning and HDR10 Expert near-black handling.
- Improved dual-layer MP4/MKV and dual-PID TS/M2TS detection, pairing and seeking.
- Corrected startup timestamps, decoder replay and rendering-mode transitions.
- Improved return to SDR after stopping playback or a failed start.
- Corrected VAAPI import-cache sizing and surface retention, targeting FEL stalls reported with PGS subtitles.
- Fixed mixed **PGS subtitles and SDR GUI composition in Master Reference**.
- Fixed subtitles disappearing in black bars and missing scrolling notifications.

## Hardware

- Added a separate matched **NVIDIA GTX 10 / Pascal R580 image**.
- Added **AMD Radeon Vega M** output support.
- Improved Intel compatibility and **Arc A/B firmware coverage**.
- Corrected NVIDIA PQ/HLG capability handling and deep-colour output validation.

## Interface and diagnostics

- Restored the compact bottom-right rendering selector, sized to the available modes.
- Improved Player information, source/output reporting and skin compatibility.
- Expanded bounded diagnostics for decoding, FEL pairing, output acceptance and HDMI failures.

## Licensing

- Migrated project-owned CB1 components and the L1/L3 AI model to **GPL-2.0-or-later**, with compatible replacements for affected helpers.
- Third-party licenses remain unchanged. The selected FFmpeg/Kodi builds still carry GPLv3 requirements; the complete image is not GPLv2-only.

## Known limitations

- **Intel N100/N150 and older AMD APUs, including Ryzen 3200U:** heavy conversions and visible menus can exceed GPU capacity.
- **Intel Core 6th–9th generation and 10th-generation Comet Lake, using Display9:** native HDMI HDR10/HLG/HDR10+ is not covered. This does not include 10th-generation Ice Lake.
- **NVIDIA GTX 10, GTX 16 and RTX 20/30 series:** some HDMI-VIC, 3D or vendor-packet combinations prevent native HDR10/HLG signaling.

## Next focuses

- Bug fixing following new issues.
