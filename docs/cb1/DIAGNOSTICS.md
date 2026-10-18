# Playback diagnostics

Supplemental diagnostics are enabled in `kodi.log` without global debug logging.
`DVBRIDGE_DIAGNOSTICS=0` disables the supplement for developer builds. No upload is
performed. The supplement does not change playback admission, retries or timeouts.

For an issue, attach `kodi.log` with the build version, exact CPU/GPU, display,
HDMI connection chain, source format and selected mode. For 3D, include the source
layout and selected output mode. Distinguish visible stutter, reported drops,
skips and timing warnings; they do not necessarily describe the same event.

The shared budget permits 24 ordinary lines per sliding 30-second playback window.
The first failure and final summary have one exemption each. Lines are bounded to
1 KiB including space for Kodi's normal prefix; suppression and truncation counts
are reported. Pause and disabled Dolby Vision do not trigger waiting warnings.

| Fact | Meaning |
| --- | --- |
| DV property absent / zero / one / unknown | Separate states of the cached DRM property inventory |
| Request, test, commit | Separate transaction stages; a successful test is not an accepted commit |
| Accepted commit cache | Software state, not a measurement of the physical HDMI signal |
| Maximum bpc | Requested ceiling, not measured cable encoding |
| FEL presented | Filter/backend of an accepted reconstructed frame; selection alone is not execution |
| Backend unscoped | Graphics callback has no proven source-frame association |

Capability caches refresh after an accepted same-size frequency transition. This
does not force 60 Hz or establish the cause of a particular 120 Hz cold-start report.
Unknown connection generation and link type remain unknown.

NVIDIA signal diagnostics include the accepted vendor InfoFrame blob and
dithering state. These are cached accepted properties, not HDMI measurements.
The framebuffer format can be RGB8 for the DV tunnel or half-float for HDR10;
framebuffer precision does not establish wire depth. NVIDIA wire depth remains
driver-selected unless independently measured. No total-GPU or NVDEC percentage
is substituted for an unavailable per-client rendering counter.

The kernel collector reports open/read errors, overruns, relevant-message counts
and whether the retained cursor was drained. `requested_from_boot_us` is the
requested window start. `coverage_scope=retained-cursor` and
`history_before_cursor=unknown` do not guarantee complete historical coverage of
the preceding 60 seconds. Silence is not proof that no earlier event occurred.
