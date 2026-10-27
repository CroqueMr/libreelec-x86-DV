# Preview2-C: remaining startup and container reports

Start at frozen Preview2-A, commit f28e9ac4d3a6b47754a833277addb16d00e77521.
Keep its tag and archives unchanged. Execute directly on a separate local branch.

## Scope

Reproduce and correct MKV FEL black startup, ISO FEL initial startup and BDMV
Play failures from #26/#29. Investigate the declared dual-track MP4 that remains
HDR10 and the HDR-first/DV availability sequence from #23. ht2tweak waits for a
new RC1 report. GPU workload, drivers, Adaptive, filters and creative algorithms
are excluded. Film pixels, source RPU and clocks must remain unchanged.

## Approach

Trace actual demux, codec and native navigation owners before adding a patch.
Reuse FFmpeg framing and the existing CBlurayDovi assembler. Do not relax packet
validation, invent timestamps, pair unrelated video tracks, or add playback
fallbacks to hide failures. Unknown or missing exact media stays explicitly open.

A demonstrated failing sequence must preserve the native caller conditions and
the reported input class. Add a small regression at its owning boundary, watch
RED, fix only that owner, run GREEN and the integration suite. Reject ineffective
prototypes. Keep software and physical playback evidence distinct.

## Delivery

RC1 Preview2-C local source candidate, one independent final review, native
translation-unit build checks and matching source receipts. No publication.
Hardware tests may use existing test hosts but must preserve profiles and restore
any stopped service. No claim that an unavailable reporter file is fixed.
