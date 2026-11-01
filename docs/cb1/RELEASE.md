# R1.0.0 RC2 - Stability improvement, HDR10+ fixes, BD-J Menu experimental support

Changes since R1.0.0-RC1, including the RC1.1 Debug fixes. CB1 **0.5**.

## Dolby Vision

- Renamed **Dolby Vision Standard** to **Dolby Vision Reference** to reflect its precision-oriented output rather than an entry-level mode. The optimized processing path is retained.
- Added optional **CM2.9 to CM4.0** controls, including Auto/Auto 2 and independent L2-trim suppression. Selection rules adapted from [avdvplus](https://github.com/avdvplus/xbmc); neutral blocks and PQ formulas from [quietvoid/dovi_tool](https://github.com/quietvoid/dovi_tool).
- Fixed Master Reference startup readiness and per-file failure counters for YCbCr and IPT output.
- Fixed HDR10 Expert startup when the required TV profile is incomplete.
- Corrected tiny or misplaced OSD during HDR10-to-Dolby Vision playback.
- Fixed in-band MP4 FEL headers, BL/EL seek recovery in M2TS/ISO and valid duplicate luma pivots in the reported Transformers FEL sample.
- Reduced intermediate storage and redundant processing in HDR10 Basic/Expert and source analysis.

## HDR10+

- Added **HDR10+ to Dolby Vision**: preserve decoded film pixels and use compatible source metadata, with AI assistance when source statistics are incomplete. Distribution estimation and scene comparison adapted from [Hades](https://github.com/hadesdevls/LibreELEC-Hades).
- Corrected native HDR10+ V1 metadata validation and HEVC/Matroska metadata handling.
- Improved Dolby Vision-to-HDR10+ metadata generation and creative-control handling, with targeted packet-progression diagnostics.

## Playback and stability

- Improved return to SDR after playback stops or fails, without artificial audio/video offsets.
- Improved native resolution and refresh-rate selection for cropped and nonstandard source dimensions.
- Added an **Auto** view mode that avoids unnecessary near-native UHD enlargement while retaining normal Kodi scaling for smaller sources.
- Integrated [Christian Hewitt's libplacebo shader-stage correction](https://github.com/chewitt/libplacebo/commit/b776078bef9a7d8ffd1da4001a29457544c5b890). Retained the shared rendering optimizations contributed by [dangerouslaser](https://github.com/dangerouslaser).

## Blu-ray menus, subtitles and 3D

- Add experimental **HDMV and BD-J menus** support
- Added **PGS/DVB subtitle controls** for brightness, saturation, size, placement and vertical offset, adapted from [avdvplus](https://github.com/avdvplus/xbmc).
- Improved AMD HDMI 3D mode entry, switching and return to 2D, building on the work of [CinemaOne](https://github.com/cinema-ONE) and [popcornmix](https://github.com/popcornmix).

## GPU and HDMI support

- Added **AMD DCN4 / RX9000** admission and improved Vega M colour-state preservation.
- Improved **NVIDIA R615/R580** HDR/SDR packet handling, extended EDID ownership and native-TMDS detection; corrected the Pascal return-thunk build contract, adapted from [Hades](https://github.com/hadesdevls/LibreELEC-Hades).
- Improved Intel EDID ownership, BT.2020 YUV signalling, neutral tunnel checks and advertised-CTA HDR10+ selection.
- Added bounded **Intel Display9 Skylake/Kaby Lake** HDR handling, retaining native output-depth and bandwidth checks. Other Display9/LSPCON restrictions remain unchanged.

## Interface and diagnostics

- Kept the compact **Quick Switch** independent of the active skin while retaining native Kodi controls.
- Fixed Quick Switch availability during paused HDR10+ / Dolby Vision transitions, using native source identity separately from per-picture output validation.
- Shortened some player information labels.
- Added bounded diagnostics for decoder stalls, BL/EL imports, HDR10+ progression, audio settings and HDMI transitions.

## Player information and audio

- Expanded audio source information: codec/immersive format, source format and channels, declared bed/objects, presentation, dialnorm, bitrate and language, when available.
- Separated source audio from actual Kodi output: passthrough/RAW, decoded or native PCM, transcode and effective output format/channels. Read-only metadata parsing adapted from [avdvplus](https://github.com/avdvplus/xbmc).
- Compact Video/Audio headings, readable labels across the panel, slightly smaller text and video dimensions without thousands separators.

## Known issues

- RX7600 FEL vertical-detail loss and repeated DV-to-HDR10+ packets remain under investigation.
- Arc B570 black-screen transitions, RTX4070 HDR10 reception and GTX1000 boot compatibility still require confirmation on affected hardware.
- Some disc-specific MP4/BDMV and authored menu paths remain unverified.
- HDR10+ target curves, colour controls and multiple spatial windows cannot all be translated directly into Dolby Vision metadata, work is ongoing to improve current algorithm.

## Next focuses

- Bug fixing following new issues
- Improve HDR10+ support and processing
- Improve hardware support
- Improve BD-J support
- Improve Player Information pannel UI
