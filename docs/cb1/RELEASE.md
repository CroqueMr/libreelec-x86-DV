# R1.0.0 RC3 - HDR rendering, FEL recovery and Blu-ray menus

Changes since **R1.0.0 RC2**. CB1 **0.5**. GPL-2.0-compatible release.

## Dolby Vision

- Added **GPU bilinear FEL upscaling** alongside **Reference GPU**. Master Reference retains its reference reconstruction filters.
- Fixed playback freezing on the reported Saving Private Ryan FEL sample. The enhancement decoder now recovers forward after damaged data, preserves already decoded exact pairs and resumes at a verified random-access picture instead of waiting indefinitely.
- Improved BL/EL pairing after Blu-ray seeks when both tracks contain unmatched preroll. Missing or ambiguous enhancement pictures are never replaced with neighbouring frames.
- Aligned HDR10-to-Dolby Vision Adaptive processing with the DV-source Adaptive logic while retaining its AI-derived source statistics.
- Kept independent playback preferences for **Dolby Vision**, **HDR10** and **HDR10+** sources. Automatic fallback no longer replaces the user's saved choice for the next file.
- Added **Kodi default** consistently to the three playback selectors, leaving normal playback to Kodi without CB1 image processing.

## HDR10 rendering

- Reworked **HDR10 Rendering Reference** around explicit display mapping: manually entered peak brightness, OLED/LCD/projector black presets or a custom black level, and output gamut selection.
- Corrected near-black handling and creative-trim application to preserve shadow steps rather than applying a linear RGB offset that can crush them.
- Added bounded highlight/gamut handling and coherent output metadata, including targets above the source mastering peak.
- Improved HDR10 Rendering startup, resource ownership and transitions back from Dolby Vision; corrected the contrast-state issue reported during live switching.

## HDR10+

- Improved **HDR10+ to Dolby Vision Rendering** metadata mapping with weighted source-distribution estimates, bounded handling of incomplete statistics and continuous scene/seek state. Source video pixels remain unchanged by this metadata conversion.
- Improved conversion startup and playback/seek recovery, with source metadata kept separate from estimated values.
- Retained native HDR10+ playback through **Kodi default**, without activating the conversion pipeline.

## Blu-ray and BD-J menus

- Bundled the Java runtime and the BD-J JAR pair matching the native **libbluray 1.5.0**, avoiding the mismatch with older add-on JARs.
- Fixed UHD menu video dimensions, missing/unknown video-size handling, audio/subtitle language selection and component inventories. Shared Java control fixes adapted from [SamuriHL's CoreELEC work](https://github.com/SamuriHL/CoreELEC/tree/bd95c331afe287a23f1851aab685fb2c6aa4907b/packages/multimedia/libbluray/patches).
- Improved direct-title stream inventory and BL/EL resynchronization without disc-name-specific workarounds.

## Playback, HDMI and hardware

- Improved return to SDR, live connector-state checks and output recovery after failed playback or mode changes.
- Retained pending HDMI modesets until the requested timing is actually committed, including when Kodi temporarily reuses its last working configuration.
- Improved AI frame/pool retirement, re-entry and paused-output resizing, without changing native Kodi scaling filters.
- Added earlier NVIDIA driver-selection and boot diagnostics to distinguish driver initialization, connector selection and damaged boot media.
- Corrected audio channel-map handling and retry state without adding artificial audio/video offsets.

## Interface and Player information

- Renamed **Dolby Vision output** to **Dolby Vision playback**, using the same compact native chooser as HDR10 and HDR10+.
- Clarified **file metadata**, **metadata used by CB1** and **metadata sent to the TV**. Forwarded metadata is no longer misleadingly described as unused merely because CB1 does not apply it locally.
- Clarified CM2.9/CM4 processing status, including live Auto/Auto 2 decisions.
- Reduced text size and shortened crowded fields; removed scrolling text and empty detail rows where information is unavailable.
- Display CPU temperature as **°F / °C** in Player information, independently of Kodi's regional unit setting.

## Maintenance

- Consolidated overlapping Kodi changes into five component-owned patches and removed unused code. The representation-only cleanup was checked against the complete resulting native source tree.
- Expanded regression coverage for playback preferences, HDMI recovery, FEL corruption/seek handling and actual bundled BD-J classes.

## Known issues

- GTX 10-series startup still needs confirmation on affected machines. Some new reports contain boot-media read errors rather than a demonstrated NVIDIA driver failure.
- Damaged FEL files can lose unavailable pictures; playback is stopped if an exact BL/EL association cannot be established safely.
- Disc-specific Java applications and repeated-disc memory behaviour are not universally qualified. Original reporter discs that were not available locally remain unconfirmed.
- Some Intel Arc and NVIDIA RTX 50-series compatibility reports still require affected-hardware validation.

## Next focuses

- Bug fixing following new issues.
- Continue HDR10/HDR10+ and affected-GPU compatibility qualification.
- Extend Blu-ray menu coverage with further authored discs and logs.
