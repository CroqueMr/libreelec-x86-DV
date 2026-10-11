# DV-R1.0.0-Beta3 - Major stability and performance improvements, plus AMD Blu-ray 3D support

Smooth Dolby Vision playback on N100, from demanding 4K 60 FPS remuxes to 4K FEL remuxes. Drop-free steady-state playback was achieved on the tested content, with Dolby Vision fast rendering enabled for demanding 60 FPS playback.

Changes since Beta2.

## Rendering and performance

- Optimized Dolby Vision HDMI packing, avoiding redundant colour-conversion and PQ processing.
- Reused the active HDMI mode during playback instead of requesting a modeset for every frame.
- Optimized menu and subtitle composition, overlay caching and transparent-colour blending.
- Reduced repeated metadata reshaping calculations by merging identical MMR intervals without changing their coefficients.
- Added automatic VAAPI FEL upscaling where supported, with shader fallback. Applies to Dolby Vision Native, Enhanced and HDR10 conversion.
- Added **Dolby Vision fast rendering**, disabled by default. Significantly reduces rendering load with fine colour-detail differences expected to be almost imperceptible during playback. Disabling it restores the reference chroma filter.
- Isolated CB1 rendering from Kodi picture adjustments. Native playback and fallback retain Kodi's settings.

Dolby Vision transport and GUI optimizations incorporate work from [dangerouslaser](https://github.com/dangerouslaser/libreelec-yblod/tree/yblod-0.2-pre2), adapted to the shared CB1 rendering pipeline.

## Dolby Vision detection and output

- Fixed rendering modes incorrectly marked unavailable when the Kodi interface runs at 1080p. [#20](https://github.com/CroqueMr/libreelec-x86-DV/issues/20)
- Fixed redundant Dolby Vision HDMI handshakes at playback startup. [#21](https://github.com/CroqueMr/libreelec-x86-DV/issues/21)
- Fixed output-surface cleanup when switching to native HDR10, HLG or SDR, including crashes during subsequent interface-resolution changes.
- Improved startup-frame cancellation and GPU-resource cleanup when stopping playback or recreating the renderer.
- Improved audio-engine acknowledgement during HDMI display changes when the audio sink is not yet configured.
- Retained previous Profile 5, 1080p playback, Enhanced stability and Blu-ray ISO Dolby Vision detection fixes.

## HDR10-to-Dolby-Vision AI

- **Major performance improvements** through optimized image analysis, asynchronous scheduling and combined rendering/HDMI packing.
- Fixed startup sequencing that could block the first video output.
- Improved prediction-worker scheduling and queue hand-off.
- Reduced image-analysis overhead using source-plane sampling and deferred statistics/readback.
- Moved future-frame analysis outside the current-frame presentation lock.
- Combined rendering and HDMI packing for compatible Standard-AI output.
- Fixed reuse of failed output preparations after geometry changes.
- The LightGBM model and fallback deadlines remain unchanged.

## Controls and diagnostics

- Fixed live presentation counters incorrectly reporting zero. [#22](https://github.com/CroqueMr/libreelec-x86-DV/issues/22)
- Added bounded AI fallback diagnostics covering processing stage, status, queue coverage and preparation counters.

## Blu-ray 3D playback on AMD

- Added software H.264 MVC decoding and Kodi Blu-ray 3D playback.
- Added paired-eye presentation, eye swapping, mono fallback and native stereo-output selection.
- Preserved authored subtitle-depth information where available.
- Added AMD HDMI 3D signalling for display-advertised modes.
- Kept 3D sources outside CB1, including mono playback: no Dolby Vision conversion, AI processing or FEL upscaling.
- Added malformed-MVC parser checks and recovery from rejected stereo-output transitions.

3D support incorporates work from [CinemaOne](https://github.com/cinema-ONE/LibreELEC.tv/tree/8f7810a9d203856c2475d3fd947c013151aff786) and [popcornmix](https://github.com/popcornmix).

## Known issues

- Lower-powered GPUs such as N100/N150 can stutter when displaying the GUI over Dolby Vision playback.
- HDR10-to-Dolby-Vision AI conversion may fall back to native HDR10 when processing cannot keep up.
- Enhanced presets need further tuning for a more noticeable effect.
- AMD HDMI 3D output and retail MVC disc navigation require hardware testing.

## Next focuses

- Improve the efficiency of HDR-to-Dolby-Vision and Dolby-Vision-to-HDR conversion pipelines.
- Make the Enhanced rendering modes fully functional.
- Integrate compatibility fixes and address newly reported support issues.

Report issues with the CPU/GPU, display, connection chain, build version and `kodi.log`.
