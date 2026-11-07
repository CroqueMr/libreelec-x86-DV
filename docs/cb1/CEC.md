# HDMI CEC on Generic x86_64

Generic builds libCEC's Linux CEC API alongside its existing Pulse-Eight USB
backend. Kodi discovers adapters through the native peripheral bus and keeps
polling for removable adapters. A CPU model alone does not provide CEC: the
board or converter must expose a supported controller and wire the CEC signal.

The enabled Linux routes are:

- DRM DP-AUX CEC tunneling on a compatible DP/USB-C-to-HDMI converter, when its
  capabilities and actual CEC wiring allow it. MST is not qualified.
- The SECO onboard CEC driver, restricted by its native UDOO x86/SECO DMI,
  ACPI, PCI and firmware checks.

USB Pulse-Eight adapters continue using libCEC. The kernel's alternate USB
backend and unrelated GPIO/SoC drivers are not enabled. Kernel CEC remote-key
injection is also left disabled; Kodi/libCEC owns key handling, avoiding a
second input path.

The existing Tinker-specific patch that stops scanning after discovering a
Linux adapter is excluded on Generic. Other projects retain their existing
selection. A device appearing as `/dev/cecX` is not by itself proof that the
board has connected its CEC pin or that the TV accepts commands.

If an adapter is discovered, use Kodi's normal **System > Input > Peripherals**
CEC settings. Enable CEC on the TV/receiver as appropriate. Hosts without a
working controller retain their normal keyboard/remote behavior.

Recipe tests exercise the native package selection, both kernel configurations
are resolved with Linux's `olddefconfig`, and libCEC is compiled with both
Linux and USB APIs. Electrical operation, TV remote keys, standby/wake and AVR
interoperability still require testing on the affected hardware.
