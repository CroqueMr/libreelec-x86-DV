# Native HDMI output and paused HDR10/AI transitions

## Native HDMI admission

Control: product source226721ab1a. Kodi receives two1920x1080/60 timings with
identical clock and porches but opposite sync polarity. Both have the same
native resolution/whitelist key. The first is not CTA and has no AVI VIC.
The DV drivers reject that timing: Intel encoder configurationEINVAL, AMD
stream validationENOMEM. Framebuffer/source/destination are all1920x1080.

Fix: retain Kodi's original catalog, whitelist and selected timing. Only the
existing DV atomic mode transaction uses the advertised CTA alias with identical
clock, geometry and porches. Ordinary restoration uses the original timing.
The existing display-info CTA table is reused. No forced resolution, driver
relaxation, RGB policy override or video/filter changes. Distinct clock/porches/
rates,3D layouts, unique PC timings and DisplayPort modes remain untouched.

Executable regression covers unchanged GetModes, both polarity orders and
fractional clocks, DV-only alias selection, accepted-mode identity, activation/
restoration flags and no premature receipt change. Independent CTA fixtures
avoid dependency on a local LibreELEC object cache. Kodi links against the
actual pinned CTA library. Runtime hardware uses that real linked library.

The initial global-catalog prototype passed six native1080p DV and ten UHD
observations, but was rejected in final review: it could change ordinary
Auto RGB range with Kodi limited-range output. No image with that global
catalog change is installed or published. The narrower atomic-only correction
is in final qualification, including a matched limited-range native1080p SDR
control. Renderer/filter code and kernel validation remain unchanged.

## Paused transitions

Fresh control reproduction: HDR10 AI Reference, pause/zoom/resume/pause, then
native/AI toggles. Ryzen3200U completes six switches without restart and remains
paused. N100 aborts playback after the first native/AI cycle; Kodi itself stays
up. A fatal output status is consumed by VideoPlayer before the later native
switch can complete.

Cause: the strict Master no-fallback guard was also applied to a plain HDR10
source during AI/native preparation. A transient ineligible import therefore
became a fatal DV-source failure. The guard now requires an actual DV source;
P5/strict Master failures remain fatal, and AI keeps its existing readiness
and fallback lifecycle. No model, queue, delay, pixels or metadata changes.

Executable lifecycle regression RED then GREEN; all14 AI re-entry tests and
the full202-test integration suite pass. Kodi link and source/staging receipt
checks pass. Runtime candidate: six paused/zoomed native/AI switches pass on
both machines, without restart or unpause, followed by exact settings and
binary restoration.

## Delivered image qualification

Source44f921cabae5e1ca36c19c49d911c12896f9aee0, private RC1 PreviewG.
Native TAR/disk/boot/ABI inspection passes. Both machines installed through
the native LibreELEC updater and match all eight component hashes. Kernel,
libplacebo, FFmpeg, settings schema and AI model remain unchanged from control.
The four changed Kodi owners replay exactly from pinned sources with zero fuzz.

202 integration tests pass. Engine tests:223 executed/pass,15 environment-
dependent skips, no failures. Astra xhigh's single Important finding was fixed
with an executable RED/GREEN regression and the complete integration suite;
no Critical or Minor findings remained from that review.

Final-image observations,10-second steady windows:

| HDMI output / case | N100 fps | Ryzen3200U fps | Extra presentation intervals |
|---|---:|---:|---:|
|1080p60 / P5 Standard|60.00|60.00|0 /0|
|1080p60 / P5 Master|60.06|60.00|0 /0|
|1080p60 / Adaptive DV|59.97|59.90|0 /0|
|UHD / Master FEL30|29.99|29.99|0 /0|
|UHD / Master Gemini59.94|59.95|59.88|0 /0|
|UHD / Standard1080p P5 input|59.94|59.93|0 /0|
|UHD / vanilla HDR10|59.95|59.91|0 /0|

Native1080p vanilla HDR10 also passes on both. A matched SDR control enables
Kodi limited RGB and connector Auto: the original PC timing flags0xA, native
range policy and output remain identical before/after. DV alone uses the
advertised CTA alias flags0x5. This SDR24-to60 range control intentionally uses
native3:2 pulldown; its cadence-mismatch warnings are not a60-fps claim.

On both machines, strict Master preference is selected with fallback disabled
before testing HDR10 native/AI: six paused/zoomed toggles pass with kernel DRM
properties confirming actual HDR10 and DV commits. Playback time is identical
across all six toggles, speed remains0 and Kodi PID is unchanged. Four running
toggles, seek, information panel, Home/video and stop also pass. Settings and
temporary observer/runtime overrides are restored.

### Remaining throughput limit

N100 HDR10-to-DV AI Reference,4K30 input at60-Hz output:23.42 fps on the delivered
image versus23.11 fps with the frozen226721ab1a control binary, same libraries,
media and observer. GPU occupancy88.4% versus88.8%; the same deadline misses
remain. This is not resolved by the two availability/transition fixes. AMD
passes that window at29.98 fps. No claim that every AI circuit reaches30 fps.

The scope is N100/3200U and bounded observations, not universal hardware support,
indefinite zero drops or external Dolby capture certification. Master rendering
code, filters and metadata calculations are unchanged. Evidence, component and
artifact hashes, metrics and decisions are in the companion JSON. No publication.

Both machines finish on the idle SDR GUI with no pending update or runtime
override. Owned observer outputs and private snapshots are removed. The rejected
global-catalog image and temporary control extraction were deleted (about2 GB);
the final image and frozen control remain. The named candidate branch is retained.
