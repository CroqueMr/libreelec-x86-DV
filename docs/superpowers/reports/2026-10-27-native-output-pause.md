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
binary restoration. Complete-image qualification remains pending.
