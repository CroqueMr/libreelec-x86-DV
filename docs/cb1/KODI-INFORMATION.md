# Kodi video information

The RC3 Player information panel uses these native source/output facts and the
[AudioEngine source and sink report](AUDIO-INFORMATION.md). It reads in three
columns: Input (what the file carries), Processing (what CB1 does with it) and
Output (what leaves the box). Each heading names the video, then the audio or the
engine; the output type is the accepted `videooutputhdrtype`, and an output Kodi
does not attest is shown as Kodi output. Long values wrap instead of scrolling.
The panel grows with its tallest column and keeps a 24 px margin above it; a
column that would pass it is cut above the meter strip, never the headings.

Dolby Vision metadata levels appear as chips: in the file, used by CB1 (unused
ones greyed) and sent to the TV. Forwarded metadata is not described as unused
solely because CB1 does not apply it locally. CM2.9/CM4 status includes the live
Auto/Auto 2 decision.

Source metadata also lists the values FFmpeg parsed from the latest sampled RPU:
L2 and L8 trim targets, L3 offsets, the L4 anchor, L9 source primaries, L10 target
displays, the L11 content type and white point, and the L254 and L255 mode and
version. An L8 target resolves as CB1 resolves it, a preset target display first,
else the file's L10 definition; targets are named to three significant digits, the
precision of a 12-bit PQ code. Layers names the base-layer compatibility and the
enhancement layer as Kodi's decoder classifies it (FEL or MEL), and the FEL row,
which also names the FEL upscaler, appears only for sources with an enhancement
layer. The HDR10 link minimum is listed under Output. Input shows the decoder's
colour tags (primaries, transfer and range; primaries Kodi guessed are marked
assumed), except for profiles 5 and 10.0, which are IPT-PQc2. An HDR10+ source
shows its latest picture's target display, MaxSCL, average MaxRGB and Bezier
curve; while CB1 renders a Dolby Vision source from its RPU, the file's HDR10+ is
unused and not listed.

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
