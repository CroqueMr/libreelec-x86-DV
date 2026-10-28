# Driver transport coverage

This matrix describes implemented output admission, not HDMI certification.
The selected connector, display capabilities, actual link depth, bandwidth and
native atomic checks decide whether a mode is available. EDID alone is not a
successful-output receipt.

| Driver / display block | Dolby Vision V1 / V2 | HDR10 / HLG | Native HDR10+ | Dolby Vision to HDR10+ |
| --- | --- | --- | --- | --- |
| Intel Display9, including Kaby Lake | Admitted DV route | No demonstrated native HDMI static-HDR bank | Not admitted | Not admitted |
| Intel Display10 | Admitted DV route | Native selector; converted PQ uses 12 bits | Frame-owned output, native 12-bit route | Same guarded 12-bit route |
| Intel Display11 and newer, i915 / xe | Admitted DV route | Native selector, guarded deep PQ conversions | Frame-owned output, at least 10 bits | Same frame-owned deep output |
| AMD admitted DCN 1.x / 2.x / 3.x families | Admitted DV route | Native AMD output | Frame-owned output, at least 10 bits | Same frame-owned deep output |
| AMD Vega M, DCE11.22 | Supported | Native DCE output | Supported DCE packet path | Supported guarded DCE deep output |
| NVIDIA R615, Turing and newer | Supported | Native output, PQ and HLG capabilities checked separately | Supported commit-coupled native packet routes | Same supported deep-output routes |
| NVIDIA R580, same image | Supported | Native output, PQ and HLG capabilities checked separately | Supported native HDMI 4:2:2 10-bit route | Same supported 4:2:2 10-bit route |

Ordinary native HDR follows each driver's policy, including dithering where
applicable. HDR10+ and CB1 PQ conversions require actual output of at least
10 bits. An 8-bit Dolby Vision tunnel is not used as a deep-colour HDR10 path.
Unlisted hardware or routes are not implicitly admitted.
The private strict-depth flag is a CB1 PQ-conversion contract, not a new HLG
conversion mode. Ordinary HLG uses native driver admission without this flag.

## Depth and topology

Display10 uses its native RGB12 or YCbCr42012 selector, including EDID DC36,
format and bandwidth checks. An 8/10-bit user ceiling is not overridden.
Display9 does not gain HDR10 support by exposing a property it cannot deliver.
Intel DP converters remain subject to their native protocol validation.

AMD DV remains limited to its explicit display-engine allowlist. Vega M is a
separate supported DCE11.22 path; discrete Polaris/Vega and DCN4 are not
promoted to supported DV hardware by these changes. Native HDR admission is
separate from the custom DV allowlist.

R615 retains matched 615.78.08 modules, firmware and userspace. Its native depth
ceiling is 12 bits; EDID and bandwidth still gate selection. This can also raise
automatic SDR/DP/4:2:2 depth. The existing ordinary max-bpc property uses native
automatic selection from 10 upward, not a newly guaranteed hard ceiling.
Strict HDR requests instead honor their requested ceiling: below 10 is refused,
10/11 requests 10, and 12 or more tries validated native 12 then 10.
DV remains explicitly 8-bit. Actual accepted depth is queried, not inferred from
the framebuffer.

NVIDIA HDR10+ uses native packet slots: unreserved legacy slots on Turing/Ampere,
the second shared slot on Ada and advanced slot 9 on Blackwell, outside the
native paired slots 1 through 8.
Conflicting reservations are rejected. Pascal uses one matched R580 stack and
native 4:2:2 10-bit output, not an invented RGB10/12 path. Its HDR10+ route is
limited to a single native HDMI head/display without VRR, stereoscopic, HDMI-VIC,
custom VSIF or converter conflicts. No boot-time mixing of driver stacks is used.

Native NVIDIA HDR10/HLG also requires an available static-HDR packet slot.
Timings that retain an HDMI-VIC vendor packet, active 3D or another VSIF owner
can prevent that packet from being emitted; these combinations are not counted
as working HDR output. This is an unsupported native combination, not a promise
that ordinary HDR fails cleanly before commit. The native mode pool uses the
HDMI Forum UHD_VIC flag to prefer CTA timing; otherwise an HDMI-VIC match can
remain selected. No forced CTA translation or VSIF removal is introduced here.
Strict CB1/HDR10+ output rejects these
conflicts before commit; ordinary HDR retains its native policy and this limit.

## Dolby Vision versions

Intel, AMD and both NVIDIA stacks distinguish modern and legacy V1 signaling.
Legacy V1 uses the 24-byte HDMI vendor payload. CTA timings 93/94/95 use HDMI
VIC 3/2/1 and AVI VIC zero; other admitted timings retain their AVI VIC.
Modern V1 and V2 retain the existing 27-byte Dolby payload unchanged.
AMD continues to reject V0. Invalid and LLDV-only sink blocks remain refused.
V1 receivers without 2160p60 capability are not admitted at that timing.

## HDR10+ frame and failure contract

Receiver V0 packets use the correct percentile semantics; V1 is not relabelled
as V0. The complete 31-byte packet must accompany an enabled primary image.
Metadata-only, TEST_ONLY, DV/3D conflicts and asynchronous flips cannot advance
the packet independently. Native and converted HDR10+ share this contract.

NVIDIA waits for the preceding presentation and the current render fence before
its irreversible native transaction. This is commit-coupled output, not a
verified hardware-FID latch. Kodi uses the blocking native transaction for these
packet updates only; Intel/AMD and non-HDR10+ presentation flags are unchanged.
Live per-head status and actual depth must confirm acceptance. A writer or
late-apply fault suppresses the accepted HDR10+ state and requires an explicit
successful clear. Uncertain occupied slots are not silently reused. Stop and
DV/HDR/SDR transitions restore the output contract.

R615 refuses native VRR reuse of an owned or uncertain legacy slot until a
separate clear succeeds. R580 preserves a slot already taken by a native EMP
owner and retains the HDR10+ fault instead of disabling that owner's packet.
An unresolved native presentation can require driver recovery; no synthetic
flip completion or successful clear is reported.

Intel/AMD capture primary-plane membership before native helpers add inherited
planes. AMD carries CTA timing in AVI when the HDR10+ VSIF replaces an HDMI-VIC
packet. Kodi rejects native HDR10+ staging if its actual drawable falls below
10 bits, while retaining native HDR10 fallback.

## Circuit mapping

| Source / circuit | Required transport |
| --- | --- |
| DV Standard / Master Reference / Adaptive | Admitted DV V1/V2 TV-Led link |
| HDR10 to DV Reference AI / Adaptive AI | Same admitted DV link |
| DV to HDR10 Basic / Expert | Native PQ output, actual depth at least 10 bits |
| DV to HDR10+ | PQ deep output plus frame-owned HDR10+ metadata |
| Native HDR10+ | Same HDR10+ transport, original authored metadata |
| Native SDR / HDR10 / HLG, DV disabled and 3D | Native Kodi and driver path |

This work does not add HDR10+ to DV conversion or alter reconstruction, Master
movie pixels, Dolby metadata, tone mapping, resolution selection or 3D processing.

## Verification

Host tests execute native packet writers, depth selectors, blob lifecycle,
failure injection and restoration. Modified owners and both matched NVIDIA
module stacks are compiled. V1/V2 tests retain frozen modern-V2 packet goldens.

Supported status describes the implemented driver path, not Dolby or HDMI
certification. Display capabilities, output depth and the accepted native
transaction still apply. DP adapters/LSPCON routes do not gain support from
the physical shape of their connector.
