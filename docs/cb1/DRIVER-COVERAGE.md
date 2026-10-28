# Driver transport coverage

These entries describe code admission, not physical HDMI certification.
All output remains subject to sink, topology, format and atomic validation.

| Driver / display block | DV V1 and V2 | Native HDR10+ | DV to HDR10+ |
| --- | --- | --- | --- |
| Intel Display9, including Kaby Lake | Yes | No native static-HDR interface | No |
| Intel Display10 | Yes | Frame-owned transport | No admitted conversion deep-output path |
| Intel Display11 and newer, i915 / xe | Yes | Frame-owned transport | Guarded output, actual depth at least 10 bits |
| AMD admitted DCN families | Yes | Frame-owned transport | Guarded output, actual depth at least 10 bits |
| AMD Vega M, DCE11.22 | Experimental | Native DCE packet path, physical qualification pending | Guarded DCE deep-output path, physical qualification pending |
| NVIDIA R615, Turing and newer | Yes | Not implemented | Not implemented |
| NVIDIA R580, Pascal image | Experimental | Not implemented | Not implemented |

## Dolby Vision V1

Intel, AMD and both NVIDIA stacks distinguish modern and legacy V1 signaling.
Legacy V1 uses the 24-byte HDMI vendor payload. CTA timings 93/94/95 use HDMI
VIC 3/2/1 and AVI VIC zero; other admitted timings retain their AVI VIC.
Modern V1 and V2 retain the existing 27-byte Dolby payload unchanged.
AMD continues to reject V0. Invalid and LLDV-only sink blocks remain refused.
V1 receivers without 2160p60 capability are not admitted at that timing.

## HDR10+ limits

Receiver V0 output is generated with actual percentile semantics, not by
relabelling V1 metadata. V1 output is unchanged. A valid receiver block does
not substitute for a frame-owned metadata transaction or deep-colour output.

Display10 lacks the native 10-bpc HDMI selection used by the current converted
output. Its 12-bpc route needs separate qualification; no forced depth or
bandwidth override is added.

The NVIDIA desktop HALs studied do not provide the required synchronized FID
callback. Several also conflict when static HDR and custom VSIF share a slot.
R580's DV path uses modesets, not per-frame HDR10+ updates. These gaps remain
explicitly unsupported; the candidate does not advertise or silently accept them.

Separate Pascal images use one matched R580 stack. Default images retain R615.
No boot-time driver-stack mixing is provided.

## Validation

Host checks execute the native packet writers, depth selectors, blob lifecycle,
invalid-request and restoration paths. Tests compare modern V2 packet bytes
against frozen goldens. New hardware and physical HDR10+ latching require
the corresponding GPU/display or HDMI analyzer.
