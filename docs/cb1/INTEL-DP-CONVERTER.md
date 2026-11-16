# Intel: Dolby Vision through an onboard DP-to-HDMI converter

Some gen11+ mini PCs have no native HDMI. Their HDMI sockets are DisplayPort
outputs with an onboard DP-to-HDMI protocol converter (PCON) behind them. Kodi
sees a `DP-n` connector, and native-HDMI Dolby Vision admission refuses it.

`linux-9950-intel-dp-pcon-dv.patch` adds a converter route for Standard
(TV-led) Dolby Vision on such ports. The NUC7i7BN (Kaby Lake), whose HDMI
socket is behind a MegaChips MCDP2800 LSPCON, gets a separate route in
`linux-9951-intel-lspcon-ls-dv.patch`: see
[NUC7i7BN: LSPCON in level-shifter mode](#nuc7i7bn-lspcon-in-level-shifter-mode).

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

LSPCON ports (Skylake/Kaby Lake MCDP2800 and similar) don't use this route. A
NUC7i7BNB with MCDP2800 firmware 1.77 was tested with the same SDP forms: it
forwards the HDR10 SDP but drops the Dolby VSIF from both the VS and GMP DIPs.
That board uses the level-shifter route below instead.

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

## NUC7i7BN: LSPCON in level-shifter mode

The NUC7i7BN's HDMI socket is DP port B behind a MegaChips MCDP2800 LSPCON.
In its usual PCON mode the chip drops the Dolby VSIF (above). In level-shifter
mode it repeats the GPU's own TMDS, so the native-HDMI Dolby Vision path
reaches the TV unchanged. `linux-9951-intel-lspcon-ls-dv.patch` (applies after
9950) switches modes per modeset:

- The DP connector gets `DVBRIDGE_DV_STANDARD_LAB`. With it set,
  `intel_ddi_compute_output_type()` returns HDMI, and the HDMI compute path
  builds the DV AVI and the Dolby VSIF, sent from the GPU's own DIPs.
- The HDMI enable path switches the LSPCON to level-shifter mode through the
  standard dual-mode register (I2C 0x40, offset 0x40) over the AUX DDC
  (`intel_lspcon_set_ls_dv()`). The HDMI disable path switches it back to
  PCON mode. Without DV the port is the usual PCON-mode DP connector (4K60,
  HDR10).
- The port's `intel_hdmi` takes the DP connector, with dual-mode type LSPCON
  and a 340 MHz TMDS limit. Level-shifter mode stops at 340 Mchar/s and gen9
  HDMI at 300 MHz, so Dolby Vision on this route is 4K up to 30 Hz.
- The shared link policy admits the route through `verified_bridge`
  (`native_hdmi` stays false on an LSPCON port). RGB8, full range, CTA timing,
  no HDR blob and progressive still apply.
- In level-shifter mode the LSPCON doesn't answer native AUX. DP detect reports
  the HPD state only and keeps the EDID, short HPD pulses and DP link checks
  are skipped, and `intel_lspcon_resume()` leaves the chip alone.
- Readout accepts an HDMI-mode DDI on that DP connector. The port's InfoFrame
  hooks use the GPU's DIPs for the HDMI-mode output and the LSPCON hooks
  otherwise.

Where it is enabled:

- `i915.dv_lspcon=-1` (default): boards in the DMI allowlist, currently board
  vendor `Intel Corporation`, board `NUC7i7BNB`.
- `i915.dv_lspcon=1`: any gen9/10 LSPCON port. Experimental.
- `i915.dv_lspcon=0`: off.
- In both enabled cases the chip is checked at modeset: a MegaChips `MC2800`
  with firmware 1.77.

### Evidence

| Board | Chip | TV | Result |
| --- | --- | --- | --- |
| Intel NUC7i7BN (Kaby Lake GT3, board `NUC7i7BNB`) | MCDP2800 HW 2.2, FW 1.77, level-shifter mode | LG OLED55C3 | Dolby Vision logo and the correct test picture at 4K23.976 RGB8 |

These are a volunteer's results from lab images (NUC Display Lab v0.3.1-dvlab
and v0.4.0-dvlab, reports 15 and 17):

| Step (report 17) | Dolby VSIF | TV |
| --- | --- | --- |
| No VSIF (control) | no | no Dolby Vision, the raw tunnel |
| DV-A | yes | Dolby Vision, correct test picture |
| DV-B (same picture, only the metadata changed) | yes | Dolby Vision, darker than DV-A |
| DV-A again | yes | Dolby Vision, brighter again |

What this does and doesn't show:

- It shows that the signalling works through the MCDP2800 in level-shifter
  mode, and that the TV uses the transported metadata (the A/B pair differs
  only in metadata).
- The lab switched modes by re-probing i915, not with this patch's in-modeset
  switch. **The in-modeset switch is not verified on hardware.** It ships in
  LibreELEC-yblod 0.3.5 compile-tested only, and the same is true here.
- Not tested: TV off/on and suspend/resume during Dolby Vision, Kodi playback
  on this board, and a soundbar/AVR in between.
- The C3 also showed Dolby Vision for a frame with broken tunnel metadata CRCs,
  so the logo alone doesn't prove the metadata is intact.
