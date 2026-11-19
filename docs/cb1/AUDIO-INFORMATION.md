# Audio information

Source and Kodi output are reported separately. These fields do not change decoding,
passthrough, volume, timing, or device selection.

| Field | Source |
| --- | --- |
| Codec, immersive profile, channels, rate, precision | Selected demux stream, then verified source headers/profile |
| Bed / objects, presentation | Declared TrueHD Atmos or E-AC-3 OAMD program structure |
| Dialnorm | Validated source header, in LKFS; not applied gain |
| Bitrate | Accepted source-packet measurement; announced rate marked `(stream)` |
| Transport, PCM format, output channels | One locked snapshot of AudioEngine's actual sink |
| Sent codec | Shown for transcode or a transmitted core differing from the source |

Unknown details are hidden. An explicit zero object count remains visible.
Passthrough and transcoded data show `RAW`, never IEC carrier channels or rate as
source audio. Source Atmos can remain visible when Kodi decodes it to stereo PCM;
that does not mean Atmos reaches the speakers. Objects describe the program, not
active speakers or a measured renderer. DTS:X does not imply a guessed height layout.

The observer reads at most the first 512 accepted packets, capped at 64 KiB each,
and resets at stream changes. It validates lengths and header/frame CRCs before
publishing bitstream details. It does not rewrite packets, decode audio a second
time, scan files, or inspect packets on UI refresh.

Read-only program and EMDF parsing is adapted from
[AVDVPlus AEStreamInfo.cpp](https://github.com/avdvplus/xbmc/blob/e0614d7a6713369bbcfe42152223f1cdaec3dbf1/xbmc/cores/AudioEngine/Utils/AEStreamInfo.cpp),
GPL-2.0-or-later. Source file notices are retained. Dialnorm defeat, packet rewriting,
CRC rewriting, inferred DTS:X speaker counts, and skin code are not imported.

Synthetic checks cover PCM, TrueHD/Atmos, AC-3/E-AC-3, DTS-HD/DTS:X, DTS core,
transcode, unknown sinks, absent audio, stream changes, malformed/truncated packets,
and concurrent sink reconfiguration. Generated FFmpeg samples supplement header
fixtures. These tests do not qualify an AVR, optical link, TV decoder, or physical
Atmos output.
