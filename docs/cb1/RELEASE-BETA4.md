# R1.0.0 Beta4 - Major pipeline optimizations, Master Reference and NVIDIA support

## Rendering modes

- **Dolby Vision Standard**: accepts near-imperceptible image differences to deliver substantially higher rendering performance.
- **Dolby Vision Master Reference**: new TV-Led pipeline aiming for bit-perfect playback, preserving the original pixels and metadata. The N100 handles all tested sources in this mode, including 4K FEL remuxes and 4K60 content.
- **Dolby Vision Adaptive HDR Mapping**: replaces Natural and Signature with a single mode. Expands highlights and selected midtones using the original metadata and configured display capabilities, with shadow protection and temporal stabilization.
- Adaptive processing also supports **HDR10 input through AI-generated Dolby Vision metadata**.

## Performance

- **AMD Performance**, performance improvement on AMD CPUs thanks to dedicated rendering pipelines optimization.
- **Major performance improvements to HDR10 to Dolby Vision AI**, reducing analysis overhead, redundant processing and preparation delays.
- **Substantially optimized Dolby Vision to HDR10 Basic and Expert**, including FEL reconstruction and direct presentation.
- Optimized Master Reference by removing redundant reconstruction, intermediate surfaces and copies without changing the reference calculations.
- Improved Adaptive processing through reduced memory traffic, streamlined shaders and earlier FEL preparation.
- Added **automatic fast rendering**, using a 2.5 ms presentation-margin threshold. Player information reports its active state.
- Master Reference remains non-Fast. Automatic performance recovery can switch to Standard when necessary, with a notification.

## Image processing

- Corrected Expert output-volume limiting, including BT.2020 peak-brightness overshoot.
- Improved Expert handling of missing or inconsistent L1 statistics and compatible L8 trims.
- Corrected the processing domain of CM4 trim commands in HDR10 Expert.
- Improved Adaptive pixel/metadata consistency and addressed reported darkening and brightness instability.

## Hardware and 3D

- Added an **NVIDIA backend for Turing and newer**, including NVDEC integration, HDMI Dolby Vision signaling and shared CB1 processing.
- Improved Dolby Vision capability detection on supported Intel HDMI paths.
- Corrected Blu-ray 3D stereo-output selection when native HDMI 3D modes are unavailable.
- Added progressive 1080p half-side-by-side HDMI modes at 24, 50 and 60 Hz.
- Retained separate native 3D playback, outside Dolby Vision processing.

## Playback and interface

- Fixed an L10 metadata-parser freeze affecting some Dolby Vision files.
- Improved startup, seeking, BL/EL pairing and recovery after interrupted preparation.
- Fixed rendering-mode transitions, stale textures and unfinished-frame cancellation.
- Corrected L5 handling with menus and overlays.
- Improved native Kodi format reporting for skin integration.
- Simplified Player information: actual TV-Led/Fast state, relevant display-profile fields and supported render-engine usage.
- Quick rendering selection remains available through the **O** panel cycle.

## Known issues

- Screenshots are unavailable in Dolby Vision Master Reference.
- Heavy conversions and visible menus can still exceed N100 rendering capacity, particularly at 60 FPS.
- Adaptive rendering remains subject to visual refinement.
- Dedicated AMD Radeon RX 5000/6000/7000 and NVIDIA GeForce GTX 16 / RTX 20/30/40/50 support is experimental.
- Repeated timing warnings have been reported on some MVC Blu-ray ISOs; investigation is ongoing.

[Current hardware coverage](HARDWARE.md) · [AMD HDMI 3D setup](3D.md)

## Credits

- **[dangerouslaser](https://github.com/dangerouslaser)**: Global rendering-engine optimizations.
- **[hadesdevls](https://github.com/hadesdevls)**: NVIDIA support, adapted from LibreELEC Hades.
- **[CinemaOne](https://github.com/cinema-ONE)** and **[popcornmix](https://github.com/popcornmix)**: upstream Blu-ray 3D work used for the AMD integration and stereo-output fixes.
