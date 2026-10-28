# Kodi video information

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
