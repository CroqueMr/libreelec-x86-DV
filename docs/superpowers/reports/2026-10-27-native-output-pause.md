# Native HDMI output and paused HDR10/AI transitions

## Native HDMI admission

Control: product source226721ab1a. Kodi receives two1920x1080/60 timings with
identical clock and porches but opposite sync polarity. Both have the same
native resolution/whitelist key. The first is not CTA and has no AVI VIC.
The DV drivers reject that timing: Intel encoder configurationEINVAL, AMD
stream validationENOMEM. Framebuffer/source/destination are all1920x1080.

Fix: normalize only opposite-polarity aliases in Kodi's native HDMI mode
catalog, retaining the actual advertised CTA timing. The existing display-info
CTA table is reused. No forced resolution, new selector, driver relaxation or
video/filter changes. Distinct clock/porches/rates,3D layouts, unique PC timings
and DisplayPort modes remain untouched.

Executable GetModes regression: RED on control, GREEN on candidate. Independent
CTA fixture data avoids dependency on a local LibreELEC object cache. Full
201-test integration suite passes; Kodi links against the actual pinned CTA
library. Runtime hardware qualification uses that real linked library.

Private runtime candidate, native1080p HDMI,10-second observation windows:

| Host | Standard P5 | Master P5 | Adaptive DV | Extra presentation intervals |
|---|---:|---:|---:|---:|
| N100 |59.995 fps|59.984 fps|59.981 fps|0 in each window|
| Ryzen3200U |59.969 fps|59.908 fps|59.921 fps|0 in each window|

All six cells valid, no fallback or stall. Additional UHD output cells on both
hosts cover FEL30 Master, Gemini Master,1080p P5 Standard, vanilla HDR10 and
vanilla SDR. All ten observations are valid. These bounded observations are
not a universal zero-drop guarantee. Temporary binaries, observer helpers and
settings were restored on both hosts.

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
binary restoration. Complete-image qualification remains pending.
