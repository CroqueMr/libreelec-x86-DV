**Update 3 | 2026-11-02 16:24 CET (Paris)**

### Update 3 changes

- Player information separates File metadata, Used by CB1 and Sent to TV.
- Clearer CM4 option names and actual CM4 status, without conversion arrows.
- Removed reserved blank row space from metadata fields.
- Fixed a Settings-to-playback freeze during automatic refresh-rate changes.
- Preserved the desktop return resolution without opening a display-confirmation dialog during playback.
- Fixed missing startup intent on the later Kodi renderer resolution request, avoiding a separate SDR timing switch before HDR activation.
- Added bounded HDMI startup diagnostics. Movie pixel processing and metadata are unchanged.

> **Work-in-progress build:** this preview evolves as fixes are added. Code cleanup is not complete. This is not a stabilized release.
>**Update 2 | 2026-11-02 13:19 CET (Paris)**



### Update 2 changes since Update 1

- Smaller text throughout Player information.
- Simplified metadata blocks: Source blocks and Sent to TV or Used by CB1.
- Fixed text instead of scrolling values, with shorter descriptions and multiline diagnostics.
- Video processing is unchanged.



### Update 2 changes since RC2


### Dolby Vision

- Added GPU bilinear FEL upscaling, replacing the nearest-neighbor fallback when VAAPI scaling is unavailable.
- Added the Reference GPU FEL filter as a selectable option for other conversion modes. Master Reference retains its reference filter.

### Playback and stability

- Fixed cases where stopping playback during a resolution change could leave HDR signaling active instead of returning to SDR.
- Fixed stale HDR10 session reuse after a rejected output activation, ensuring subsequent playback prepares the required output surface.

### Settings

- Separate remembered rendering preferences for Dolby Vision, HDR10 and HDR10+ inputs.
- Automatic fallback no longer replaces the preferred rendering mode.
- Fixed rendering options incorrectly remaining unavailable after stopping a different source format.

### HDR10+

- Fixed source-specific preference selection during continued HDR10+ playback, preventing accidental use of the plain-HDR10 preference.

### Player information

- Corrected misleading "Unused blocks" reporting: metadata forwarded to the TV is no longer marked unused.
- Displays whether CM2.9-to-CM4 conversion is actually active, including live updates for Auto and Auto 2.

### Blu-ray menus

- Updated BD-J Java add-on packaging with matching libbluray 1.5.0 support files.
- Prevented stale or incomplete Java support files from being packaged. Requires the updated JRE add-on attached to this release.

### Diagnostics

- Added targeted diagnostics for deferred playback shutdown and SDR output restoration.

## Work in progress

- Improve HDR10 reliability.
- Fix support issues on some Intel Arc GPUs.
- Fix support issues on NVIDIA GTX 10-series and some RTX 50-series GPUs.
