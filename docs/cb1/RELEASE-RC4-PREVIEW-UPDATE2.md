# R1.0.0 RC4 Preview - Update 2

> Work-in-progress build, not a stable release.

## Changes since Update 1

- Improved Intel Xe3 / Wildcat Lake display initialization and I2C handling, with the required upstream dependencies.
- Preserve installer boot logs on the USB boot partition, including the previous attempt after a failed boot.
- Retain on-screen NVIDIA boot diagnostics, including kernel audio/PCI messages when emitted.

This is the normal Generic x86_64 image for Intel, AMD and supported NVIDIA
systems. It includes the existing ISO/menu, HDR10+, VAAPI and NVIDIA changes
from Update 1. NVIDIA work retains credit to
[Hades / hadesdevls](https://github.com/hadesdevls/LibreELEC-Hades).
The experimental Player information redesign in PR92 is excluded.

## Installation and logs

Use the `.img.gz` for a new USB installation, or the `.tar` through LibreELEC's
normal update procedure. Installer boots save `cb1-boot-logs/current.log` and
`previous.log` on the FAT boot partition, readable on another computer. See
[installer logging and Xonar comparison](INSTALLER-LOGS-XONAR.md) for limits.

## Qualification limits

Xe3 changes are tested and compiled backports, not confirmation that issue93
is fixed on the affected HP. The Xonar STX II startup hang remains under
investigation; Hades RC8 uses the same 28 Virtuoso/oxygen source files and no
Xonar-specific patch was identified. Console text depends on a working kernel
and display; files improve diagnosis when screen text is unavailable.

[Blu-ray menu corrections](BLURAY-MENU-SCOPE.md) apply to shared reader and
navigation behavior. Complete compatibility with every BD-J disc, BD-Live and
physical stereoscopic menus is not claimed.
