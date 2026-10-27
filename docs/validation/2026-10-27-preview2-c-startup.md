# RC1 Preview2-C: startup and container corrections

Base: frozen Preview2-A, `f28e9ac4d3a6b47754a833277addb16d00e77521`.
Branch: `candidate/rc1-preview2-c-startup`. Local source candidate only.

## Changes

| Boundary | Reproduced failure | Correction | Verification |
|---|---|---|---|
| HEVC framing, disc/TS startup | Untimed parameter PES hides the first picture's real PTS/DTS; a large split picture overwrites timestamp history before late recovery. | Capture its existing clock across the first slice's prefix/header, at most seven byte positions. Preserve already valid clocks and genuinely missing clocks. | Eight clock cases across ten packetizations, including partial/zero clocks, three-byte prefixes after a trailing zero, timed middle fragments and unchanged following-picture clocks. Real 4K FEL transport emits 48 pairs, zero missing clocks and zero rejected packets. VCL, EL and RPU bytes match the source. |
| MOV dual-track association | Explicit Profile 7 EL configuration and `vdep` reference are ignored when the EL uses `hvc1` or `hev1`. | Accept these HEVC sample entries alongside `dvhe`/`dvh1`, requiring exactly one distinct declared base. Retain at most two distinct references to detect ambiguity before group construction. | Actual FFmpeg MOV demux and Kodi assembly pass both entries. Missing config, independent tracks, missing base references, reversed/multiple dependency targets, repeated dependency atoms and ambiguous groups stay rejected. Assembled payload and clocks are checked. |

Both regressions failed before the corresponding correction. The failed late
timestamp-recovery prototype was removed. No frame clocks are fabricated, and
no missing-picture validation or layer relationship is relaxed.

## Report status

| Report | Result |
|---|---|
| #26 ISO initial black startup | A real untimed-header/first-picture failure is reproduced and corrected. The reporter's exact ISO is unavailable, so that report is not confirmed resolved. |
| #26 MP4 FEL stays HDR10 | The sample-entry exclusion is reproduced and corrected. Its codec tag and dependency are absent from the supplied inventory; the exact file is unavailable. |
| #26 single-track MKV FEL black screen | Not reproduced with the local Woman at 80s sample. A native N100 VAAPI control submits 96 packets and pairs 95 pictures, one pending tail, zero failures. No decoder pool or timeout change. |
| #29 separate-track MKV | Current failing sample and Beta5 playback log remain unavailable. An older supplied log is a system journal, not evidence of the decoder boundary. No unproven decoder change. |
| #26 BDMV Play does nothing | Navigation failure remains unconfirmed. The log prepares a FEL frame after rejecting its parameter packet, so that rejection alone does not establish a Play failure. |
| #23 HDR-first/DV availability | Frozen Beta5/Preview1 native state methods recover when the next DV codec opens. The supplied log contains HDR playback only. No speculative reset or driver change. |

A Kodi playback control prepared its first FEL frame but failed HDMI commit.
It is inconclusive for visible playback and is not counted as a successful
scanout qualification or a reproduction of the MKV decoder-startup report.

## Qualification

- Full integration suite after the review corrections: **208/208 pass**, 193.010 s.
- Changed FFmpeg HEVC-parser and MOV translation units compile with the real
  LibreELEC toolchain.
- Both owners replay from pinned FFmpeg 9.0 with `--fuzz=0` and match the tested
  host and LibreELEC source bytes. MOV replay includes the existing MVC patch.
- Source staging and integration checksums pass for all 119 staged CB1 files.
- Preview2-A's tag and archives are unchanged. No full Preview2-C image has been
  built, installed or published.

GPU workload, processing shaders, metadata transformation, creative algorithms,
drivers and settings choices remain unchanged. ht2tweak awaits a new RC1 report.

## Independent review

Astra's review of `3783b8b` found two important boundary failures: clocks on a
middle NAL-header descriptor, and multiple declared MOV base targets hidden by
group construction. Both were reproduced as failing owner tests and corrected.
No minor findings were deferred.

The review does not certify unavailable reporter media, all possible seek/EL/RPU
packetizations, physical HDMI playback, sustained hardware performance, a full
image, archive bytes, excluded drivers/GPU behavior or the pending ht2tweak case.
Those remain explicit qualification limits, not resolved reports.

## Scope decisions

- Keep Preview2-A frozen; do not revive the rejected Preview2-B GUI prototype.
  Bringing it back would change the baseline without a valid reproduction.
- Keep ht2tweak pending and GPU/driver/BT/display-policy work excluded. This
  iteration therefore does not resolve those separate behaviors.
- Fix the native HEVC framing owner, not joiner validation. Recover only an
  existing descriptor clock; genuinely untimed pictures remain rejected.
- Do not change decoder pools, delays or capability resets without reproducing
  the failing MKV/BDMV/HDR-first sequence. Those reports may remain unresolved.
- Treat the MOV sample-entry result as a proven mechanism, not proof about the
  unavailable reporter MP4. A different file defect would need its own evidence.

## Regression commands

With the matched FFmpeg test prefix and applied pinned Kodi source configured:

```sh
PYTHONPATH=tests/cb1 python3 -B -m unittest test_hevc_prefix_clock test_dual_carriage
python3 -B scripts/cb1-stage.py --check
python3 -B -m unittest discover -s tests/cb1
```
