# DV-R1.0.0-RC1 source qualification

Base: Preview2-C, 09ee9116f4f52d534882b020767853fe7f11b15a.

- Native MOV association diagnostics: numeric sample entry and dependency IDs,
  bounded to sixteen candidate tracks, explicit rejection reasons.
- Native Kodi inventory includes the numeric codec tag.
- Decoder startup records BL, EL submission/decode and pairing once per open.
- First accepted presentation records once for the current live stream.
- Playback-open diagnostic generation rejects late events from old decoders.
- Existing shared diagnostic budget and exception isolation remain active.
- No rendering, metadata, output-selection, retry or clock changes.

Validation:

- Baseline: 208 tests passed.
- Final suite: 210 tests passed in 200.297 seconds.
- Five modified Kodi owners replay byte-identically from the pinned source.
- MOV and MVC patches replay byte-identically from FFmpeg 9.0.
- Native decoder/demux translation units and FFmpeg avformat compile/link.
- Release defaults: DV-R1.0.0-RC1; GitHub identity: R1.0.0-RC1.

Complete-image inspection and hardware benchmark are separate gates. This
document does not establish hardware performance or resolve unobserved reports.
