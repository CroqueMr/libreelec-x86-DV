# Preview G: native scaling, Expert black and chroma corrections

Code: `226721ab1a918d764a24cb90aaccf429cc489ffc`.
Control: `d3059e908774e728eace5a85eef33ec64fee3707`.
Private build, no publication. Complete-image inspection passed; final hardware qualification is recorded below.

## Changes

- Expert no longer interprets the mastering monitor's minimum luminance as
  an absolute-PQ content floor. Other rendering policies retain their mapping.
- Source chroma siting reaches DV conversion imports and synchronous/prefetched
  FEL VPP input. Existing Master defaults and Y416 adjustment are preserved.
  Raw HDR10 AI ingress remains unshifted because it owns coded-grid reconstruction.
- Non-Master final native fitting uses 16F storage instead of 32F. Kodi's original
  filter choice, kernels, crop and placement remain. Master retains 32F and rejects
  lower precision even after source reconstruction. No extra scaler or setting.

## Complete image and interaction checks

The final image was installed through the native LibreELEC updater on Intel
N100 and AMD Ryzen 3 3200U. Kernel, system, Kodi, libplacebo, FFmpeg libraries and
settings-schema hashes match the inspected receipt on both hosts. No publication.

- 20-second final-image windows pass validity on 6 routes per host: Standard P5,
  Adaptive DV, Master P5, Master FEL30, Master Gemini 59.94 and HDR10→DV AI Reference.
  Validity is not a 60 fps claim: AI Reference measured 45.03 fps N100/59.39 fps AMD.
- Final-image short smoke checks pass on both hosts for FEL→HDR10 Basic/Expert,
  HDR10 vanilla 4K/1080p and SDR vanilla. These are validity screens, not sustained
  cadence measurements.
- 14 DV interaction journeys pass across 720p, cropped near-UHD Dragon, FEL and
  1440p: 654 native UI/RPC actions, 76 mode switches and 36 O-cycles. Zoom, aspect,
  placement, subtitle/notification, pause/seek, Home/video and stop are included.
  Kodi process identity, settings and installed binaries are restored/unchanged.
- Additional final-image Expert/P5/AI journeys pass on AMD; Expert passes on
  N100. A separate N100 paused HDR10-native↔AI-Reference cycle times out waiting
  for output activation. The frozen pre-fix Kodi binary reproduces the identical
  timeout on the same kernel/libraries. This is not counted as a passing journey
  or a new regression. Playback alone is valid. The paused transition remains
  a separate known limitation; no AI scheduling changes are included here.
- Native whitelist output 1920×1080@60 was tested separately from 1080p-source
  scaling to UHD. DV atomic admission is rejected (Intel EINVAL, AMD ENOMEM).
  Standard/Adaptive fall back to HDR10; strict Master does not progress. The
  frozen pre-fix binary reproduces Standard's rejection on both hosts. These
  cases are invalid and provide no DV FPS result. No kernel safety check or
  Kodi output selection was overridden. Native 1080p HDMI DV is not qualified.

- Image source commit: `226721ab1a918d764a24cb90aaccf429cc489ffc`.
- SYSTEM SHA256: `d341aeeb9923ba7d726663022fb24d3ee5d3933870d280c8b2fee5a90bfe09ba`.
- TAR SHA256: `f4e1bbdda1d7d1ef1eb47a9655c5540fab4245b678d2903551e48472c440201e`.
- IMG.GZ SHA256: `176f08dfe4529b2694d3e8f58123037658d80b4edc11fef3dd2472629d5f1834`.

## Matched complete-image playback screen

20-second windows, same files, native normal view, UHD60 output, async enabled.
Both hosts ran the final complete image, commit 226721ab1a. Original and candidate
files, view, duration and output match; no temporary runtime binary was used.

| Mode | N100 before / after FPS | AMD 3200U before / after FPS |
|---|---:|---:|
| P5 Standard 1080p60 → UHD |46.26 /60.03|36.93 /59.98|
| Adaptive 1080p60 → UHD |27.60 /36.58|27.39 /54.85|
| Master 1080p60 → UHD |42.20 /41.95|37.33 /37.28|
| Master FEL30 |29.99 /30.04|30.00 /30.00|
| Master Gemini 59.94 |59.94 /59.98|59.94 /59.94|

| After | N100 render-engine load / presentation margin p01 | AMD render-engine load / presentation margin p01 |
|---|---:|---:|
| P5 Standard 1080p60 |87.4% /13.87 ms|79.1% /17.70 ms|
| Adaptive 1080p60 |79.3% /−7.76 ms|84.0% /−1.12 ms|
| Master 1080p60 |99.6% /−6.34 ms|99.9% /−10.04 ms|
| Master FEL30 |73.2% /34.34 ms|68.0% /36.24 ms|
| Master Gemini 59.94 |64.4% /17.03 ms|67.5% /8.67 ms|

Presentation margin is the observed GPU-ready-to-deadline margin, including
asynchronous preparation. It is not unused GPU execution capacity. Native GUI
drop/skip counters were unavailable. Zero excess presentation intervals on the
Standard/Master FEL/Gemini screens is not sustained zero-drop certification.

Adaptive 1080p60 still misses 60 fps, particularly on N100. Master 1080p60 remains
bandwidth-limited; its precision was not reduced to hide that limit. Master FPS
differences are below 1% in these windows, not a claimed speedup or a statistical
non-inferiority study.

## Fidelity and software verification

- Native scaler alone at 1080→UHD: N100 10.43→4.37 ms, AMD 11.40→6.05 ms.
  Same native linear filter, different intermediate storage only.
- Synthetic 16F storage witness: worst 2/4095 component-code difference on Intel;
  this AMD witness was identical. This is not a universal two-code bound or a
  perceptual study of every filter/content combination.
- Master fitting matches frozen d305 bit-for-bit in 10 cases per GPU, each with
  33,177,600 components: 720/1080/1440/3838×2020, native linear and Lanczos3 Fast,
  fractional crop/placement and flip. Separate 167-value reconstruction and
  transport witnesses pass both GPUs; input metadata is preserved.
- Real resized YCbCr/IPT Master entry points reject a deliberately 16F callback
  and accept 32F; P5 Standard accepts 16F. RED before the guard correction, GREEN
  afterward on both GPUs.
- LEFT/CENTER/TOPLEFT imports, including P010 BL/EL, preserve the packed Y416 and
  nonsubsampled 4:4:4 exceptions. Both actual adapter prefixes and real imports
  are exercised. Intel VPP blocking/prefetched RGBA16 bytes match at all 3 sitings.
  AMD 3200U rejects Y416 as unsupported and retains the raw path; no AMD VPP claim.
- Expert absolute-PQ ramp tests low luminance with 4 L6 minima, with/without neutral
  trims, and checks source metadata is unchanged. Real Intel/AMD GPU runs pass.
- 238 engine cases, no failures, 15 explicit software-GPU skips. 200 integration
  tests pass. Kodi link, source receipts and fresh 30-patch replay/12 owners pass.

## Independent review and qualification boundaries

Astra xhigh reviewed d3059e9087 through b01f09bd7e and identified 2 Important
findings, both subsequently reproduced and fixed: the
resized-Master precision guard and VPP/prefetch input siting. No Critical finding.
Deferred Minor: the precision-routing test checks its 2 setters consecutively;
independent assertions per entry would improve that test. Real Master rejection
and before/after equality are tested separately.

Decisions and residual risks:

1. Keep 16F outside Master only. Small non-Master rounding is accepted; unseen
   content is not guaranteed to stay within the synthetic maximum.
2. Finite native-fit and separate reconstruction/transport witnesses do not
   certify every transition or proprietary Dolby equivalence. Interactive gates
   supplement them; untested edges remain possible.
3. Physical HDR10+, hybrid/NVIDIA/3D and arbitrary creative trims are outside
   these 3 fixes. They still need their dedicated hardware/content qualification.
4. Runtime resolved filter was not directly instrumented. Selection code and
   kernels are unchanged and independently tested; A/B is not an exhaustive
   playback comparison of every filter.
5. Decoder, kernel, audio and historical PR behaviour were not changed. Component
   hashes and regression/stress gates bound this work, not broader certification.
6. The pre-existing N100 paused native-HDR10/AI transition remains uncorrected.
   Broadening AI scheduling is outside these 3 fixes; it needs its own targeted
   diagnosis. No claim that every possible mode transition passes is made.
7. Native 1080p HDMI DV atomic rejection is also reproduced with the control.
   Changing scanout/driver admission is outside this lot and could compromise
   tunnel integrity. All positive1080p-source FPS values above use UHD output.

## Local delivery and cleanup

The branch and final private image are retained. The frozen d305 image remains
available for comparison. Superseded b01/002 full-image artifact sets and owned
control extraction, 720p media, Dragon copy and subtitle fixtures were removed.
Source recipes, hashes and measured evidence remain in the dated local workspace.
Both hosts retain the final inspected image, original settings restored, native
UHD60 GUI, no active test player and no runtime-binary overlay. No GitHub write.


