# Intel: Dolby Vision through an onboard DP-to-HDMI converter

Some gen11+ mini PCs have no native HDMI. Their HDMI sockets are DisplayPort
outputs with an onboard DP-to-HDMI protocol converter (PCON) behind them. Kodi
sees a `DP-n` connector, and native-HDMI Dolby Vision admission refuses it.

`linux-9950-intel-dp-pcon-dv.patch` adds a converter route for Standard
(TV-led) Dolby Vision on such ports.

## How it works

The converter already turns DP InfoFrame SDPs from the transcoder's DIPs into
HDMI InfoFrames: that is how HDR10 reaches the TV (GMP DIP, DRM InfoFrame).
The route sends the Dolby VSIF the same way:

| Packet | DIP | Form on the DP link |
| --- | --- | --- |
| Dolby VSIF (OUI 00-D0-46, signal = 1) | GMP | `00 81 1d 4c` + version, length, PB1..PB26 |
| DV AVI (CTA VIC, RGB, full range, no colorimetry) | AVI | `00 82 1d 4c` + version, length, payload |

The VS DIP is not used, because on the verified converter it blanks the HDMI
output. The SDP carries PB1..PB26 (the DP InfoFrame SDP length); PB27 of the
Dolby VSIF is reserved, and the driver checks that it is zero.

At modeset the connector must be a DP branch device with an HDMI DFP and an
HDMI sink, and the shared link policy (`drm_dvbridge_validate()`) applies with
`verified_bridge` in place of `native_hdmi`: RGB8, full range, CTA timing, no
HDR blob, progressive. The retry of `intel_dp_compute_formats()` that ignores
the converter's TMDS limit is skipped for Dolby Vision. Readout maps both SDPs
back to HDMI InfoFrames, so the state checker compares them as usual.

## Where it is enabled

- `i915.dv_pcon=-1` (default): boards in the DMI allowlist only.
- `i915.dv_pcon=1`: every gen11+ HDMI-capable DP port that isn't LSPCON or eDP.
  This is experimental: an unverified converter may show no picture, or drop
  the VSIF so that the TV shows the raw tunnel.
- `i915.dv_pcon=0`: off.

LSPCON ports (Skylake/Kaby Lake MCDP2800 and similar) are not affected. A
NUC7i7BNB with MCDP2800 firmware 1.77 was tested with the same SDP forms: it
forwards the HDR10 SDP but drops the Dolby VSIF from both the VS and GMP DIPs.

## Verified

| Board | Converter | TV | Result |
| --- | --- | --- | --- |
| INUSUAL INUC 11i5FL (Tiger Lake, board `CM11EBV58W`), both HDMI sockets | Onboard PCON, blank branch ID, DFP `0b f0 02 00` | Sony Bravia 7 (TV-led DV, VSVDB v2) | Dolby Vision at 4K23.976 and 4K59.94 with an RGB8 tunnel test frame; Dolby Vision playback in Kodi |

The test frame came from the NUC Display Lab
([dangerouslaser/nuc-hardware-lab](https://github.com/dangerouslaser/nuc-hardware-lab),
v0.3.0-dvlab, report 13). Kodi playback was checked on LibreELEC-yblod
0.3.4-test1, which carries the same kernel change.

To add a board, confirm Dolby Vision on the TV with `i915.dv_pcon=1`, then
add its DMI board vendor and name to `intel_dp_pcon_dv_dmi[]`.

## Known limits

- Through this route the Sony accepted frames whose tunnel metadata CRCs were
  broken, so the TV's Dolby Vision logo alone doesn't prove that the metadata
  arrives intact. Check the picture as well.
- The converter has no sink CRC, so the link can't be checked bit for bit.
- DV-to-HDR10 conversion on these ports keeps its existing DP rules. It is
  not part of this change.
