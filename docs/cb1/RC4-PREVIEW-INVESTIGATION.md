# RC4 Preview: investigated reports and scope

This preview retains the ISO/menu changes from the A candidate `c29cd1f`,
integrates the reviewed R580/KMS and HDR10+ pacing work, and addresses the
following independently identified software defects. Hardware outcomes that
were not measured are not inferred from host tests.

## Intel VAAPI and YouTube #89

The upstream pix_fmt fallback referenced in #89 was already present. It did
not handle a nonzero but stale 8-bit hint: VAAPI chose 8-bit surfaces even
when FFmpeg's get_format callback offered a decoded 10-bit software format.
The existing CDecoder::Open owner now prefers that software descriptor,
excluding hardware formats, and retains its previous fallback when absent.
Chroma/profile dispatch, renderer pixels and Dolby Vision processing are
unchanged.

The regression compiles the shipped selection code into an actual FFmpeg9
VP9 get_format callback. A generated VP9 Profile2 stream fails before the
change (hint8/decoded10/selected8), and decodes after it. ASan/UBSan also
cover 8/10/12-bit selection and the legacy fallback. This demonstrates the
selection defect; actual YouTube DASH/VAAPI playback on the reporter's GPU
still requires confirmation. The original local-file control used a
different video and is not a same-file A/B test.

The software-format contract is corroborated by Hades' GPL-2.0-or-later
[VAAPI investigation](https://github.com/hadesdevls/LibreELEC-Hades/blob/8ed4131907792183d73643975e22d96da3219786/projects/Generic/patches/kodi/x86/kodi-9290-vaapi-take-the-bit-depth-from-the-format-the-decoder-offers-not-the-hints.patch).
No additional helper, API or header is imported.

## NVIDIA R580 modes and the common EGL-GBM owner

The R580 timing library lacked the integer-rate twins already present on
R615. The exact R580 variant from Hades is retained with its author header.
A host test compiles the real timing libraries of both branches and parses
a CTA-only EDID: fractional rates must remain, and 24/30/60Hz modes must
exist with their correct pixel clocks. R580 fails before and passes after.

EGL-GBM is now built once from NVIDIA's official1.1.4 tag (its ABI filename
is still1.1.3). Its existing package owns the library, links and platform
JSON globally. Both vendor recipes depend on it and cannot overwrite it
with branch-local installer copies; driver-specific EGL/RM components
remain in their selected payload.

Hades' small hook-safety change fixes null attribute handling, output-count
allocation bounds, allocation failure reporting and pbuffer references.
The original function bodies are executed under ASan/UBSan with injected
device/handle boundaries: six of eight checks fail before, all eight pass
after. Installation tests run both actual vendor recipes without vendor
EGL-GBM blobs and verify that the common library survives unchanged.
NVIDIA's original sources are MIT; the added Hades contributions are
offered under GPL-2.0-or-later, selected under GPL2 for this build. Author
headers remain in both patches. No GPLv3-only code or Hades binary is used.

The optional three-buffer FIFO change is not imported: its need and gain
have not been demonstrated for this player's presentation path. The
ownership/safety change does not assert a physical frame-pacing gain.

## RTX4090 photograph

The supplied photograph shows an NVIDIA flip-completion timeout, a warning
from an empty flip queue and a later Kodi segfault. It does not provide a
complete trace, exact installed driver identity or a symbolized Kodi crash.
The initiating fault and its causal relation to the segfault remain open.
No success event is fabricated, no driver warning is suppressed, and no
title-specific or global-restart workaround is added. The user cancelled
the proposed investigation beyond this documented case. The preview must
be retested on the affected setup before this report can be closed.

## Intel Xe3 / Wildcat Lake #93

The pinned7.2.6 kernel already contains Wildcat Lake PCI/display entries;
Mesa26.2.3 contains WCL support; PTL GuC/HuC/GSC firmware is already in the
built-in firmware list. Thus the report does not, by itself, establish
that a missing driver requires a whole-kernel update or force_probe.
Check the final image's actual modules/firmware and compare the affected
device's PCI identity and boot log. No physical Xe3 boot is claimed here.

## N100 delayed start and the separate N150 freeze

The supplied N100 sample is VP9 Profile0/8-bit, not a verified DV sample.
Its log has a26.461s pre-input delay with repeated NAS-name lookup errors,
concurrent thumbnail failures and later buffer stalls. A local/by-IP/by-name
comparison is needed; this is not evidence for an ISO or DV decoder patch.

The N150 log linked from #93 shows repeated failures to open the eight-channel
TrueHD passthrough sink, audio AddPackets timeouts and subsequent video
starvation. Enabling display-sync changes the audio path, so that result
alone does not locate a video timing bug. Do not silently replace the
selected audio format or force display-sync. An audio-device/capability
comparison is still required on that setup. Raw user logs remain private
and are excluded from source/release exports.

Further RGB-range, HDMI recovery, deep-output and VSIF-coexistence changes
from the prior NVIDIA comparison remain separately scoped work; they are
not blindly imported as a fix for any of the reports above.
