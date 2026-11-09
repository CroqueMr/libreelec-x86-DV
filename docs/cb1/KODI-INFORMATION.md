# Kodi video information

The Player information panel uses three columns: Input (original file),
Processing (accepted work), and Output (accepted signal). It uses native source/output facts and the
[AudioEngine source and sink report](AUDIO-INFORMATION.md). Source format is
shown in the Input heading; committed output telemetry identifies Output.
Native SDR, HDR and HLG remain separate from a source converted to another format.
Unknown output is labelled Kodi output; requests, pending changes and fallbacks
remain in a separate Mode change section.

The panel distinguishes file metadata, metadata used by CB1 and metadata sent to
the TV. Forwarded metadata is not described as unused solely because CB1 does
not apply it locally. CM2.9/CM4 status includes the live Auto/Auto 2 decision.

Source and output are separate facts. Existing `VideoPlayer.HdrType/HdrDetail`
and `ListItem.HdrType/HdrDetail` describe the original source. HDR10 converted
to Dolby Vision remains an HDR10 source; Dolby Vision converted to HDR10 remains
a Dolby Vision source. Library stream details are not rewritten by output selection.

## Native data ownership

- Native demux, decoded pictures and stream details supply source information.
- `CDataCacheCore` owns one coherent `VideoProcessingInfo` value. `CProcessInfo`
  forwards publication without retaining another copy.
- The renderer publishes accepted output at its existing presentation boundary.
  Requested or prepared output is not reported as active output.
- Stream open, reset and flush invalidate the information generation. Pictures
  retain their captured generation; obsolete publications are rejected.
- Failed commit/restoration information preserves the last accepted output.
- Summaries refresh at up to 2 Hz; accepted mode and format changes publish
  immediately. No additional image analysis or GPU readback is performed.

The custom Player information panel reads this native cache. Its properties are
display values, not a second playback-data store. Hardware utilization sampling
remains demand-driven. Closing or disabling the panel does not remove native facts.

Stereoscopic layout and 3D-output selection remain Kodi-owned. They are not
reported as a CB1 conversion or Dolby Vision output.
[Player controls](PLAYBACK.md) · [AMD HDMI 3D](3D.md).

## Information labels

Labels are registered in Kodi's existing `Player.Process(...)` provider.

| Key | Meaning |
| --- | --- |
| `videooutputhdrtype` | Accepted output: `sdr`, `hdr10`, `hdr10plus`, `hlg` or `dolbyvision`; empty when unknown |
| `videoprocessingmode` | Accepted processing mode |
| `videoprocessingengine`, `videoprocessingcircuit` | Accepted engine and circuit versions |
| `videoprocessingfallback` | Processing failure/fallback reason |
| `videodvcmversion` | Original Dolby Vision metadata version |
| `videodvparsedblocks` | Original parsed metadata blocks |
| `videodvappliedblocks` | Original blocks used by accepted processing |
| `videodvtransmittedblocks` | Metadata blocks transmitted by accepted output |
| `videodvprofile`, `videodvlevel`, `videodvversion`, `videodvlayers` | Original Dolby Vision stream facts |
| `videosourcebits` | Original decoded source precision |
| `videooutputformat`, `videooutputbits` | Accepted output format and precision |
| `video.sidedata` | Lazy JSON/base64 snapshot of original source metadata on the accepted video frame |

Generated AI metadata describes output, not original Dolby Vision metadata.
Ordinary Kodi output HDR state is left unknown when the presentation owner does
not attest it. Source labels remain available. Existing decoder pixel-format
labels retain their original meaning.

Skins can use the native source labels unchanged. These additional processing
labels do not automatically add new elements to third-party skins.

## Audio information

The audio heading combines the source codec and validated immersive profile.
Source precision, channels, bed/objects, presentation and dialnorm are independent
of the actual PCM, passthrough/RAW or transcoded output. Missing fields are hidden.
Packet observation is read-only; it does not change gain, audio timing or devices.
[Fields, parsing limits and provenance](AUDIO-INFORMATION.md).

## Original source payloads

`Player.Process(video.sidedata)` is independent of the custom panel and CB1 output.
Decoded pictures hold immutable references. Only a successfully rendered,
accepted presentation publishes a new snapshot; failed or obsolete work cannot
replace it. Pause retains the snapshot. Open, seek, flush and reset invalidate its
generation. JSON/base64 is constructed once, on demand, outside the presentation
lock. It is not limited by the 2 Hz summary throttle.

| Key, when present | Format before base64 |
| --- | --- |
| `dovi.config` | Explicit 24-byte decoder configuration record |
| `dovi.rpu` | Original HEVC escaped NAL62 with header, or AV1 Dolby T.35 payload |
| `mdcv` | 24-byte mastering-display SEI record |
| `cll` | 4-byte content-light record |
| `hdr10plus` | Validated version1, single-window ST2094-40 T.35 record |

Missing, invalid or oversized sections are omitted independently. Original RPU
bytes are not replaced by generated AI or adjusted output metadata. Track topology
and CoreELEC flags are omitted when not established by the source owner.

TinyPPI requires a separate platform/output-label adaptation and matching x86-64
native dependencies. This label alone does not make the unmodified extension
compatible. Reference-dependent RPU parsing and other HDR10+ variants remain
unqualified; no alternate parser is added to Kodi.

## Player information integration (2026-11-09)

PR92 at `346f41853906dbbca754771c961b3536fc4ca80c` was rebased against the
RC4 matched Kodi source. Its decoder hunk moved by 109 lines; no stale source
replacement was used. The generation-checked immutable side-data snapshot and
per-stream FEL/MEL/guessed-primaries clears were absent on this base and retained.
Reset clears guessed primaries too. Input keeps unused HDR10+ alongside DV RPU
facts; Processing never shows grey unused levels. Levels use numeric order in
all three columns. Output L2/L8 target lists are shown only when the accepted
transmitted mask forwards those unchanged authored blocks; legacy synthesized
output excludes them. SDR carries no DV transmitted blocks.

Each field stays on one line and its full value scrolls horizontally. Up/Down
and Page Up/Page Down scroll column inventories together, bounded independently
by each column's contents. This keeps maximum RPU inventories accessible rather
than cutting off source facts. Empty metadata sections collapse. The native
Kodi dialog fallback remains available when enhanced information is disabled.

Focused qualification: seven column contract tests and 22 process information
tests pass against a separate copied matched Kodi tree, including compiled RPU
capture/target formatting, FEL reset, pending-output and skin recovery checks.
RPU capture uses the existing FFmpeg test prefix. This is native source testing,
not physical display qualification. An actual panel capture is still required
on the new combined preview image; no new image was running during this edit.
