# Installer boot logs and Xonar STX II

RC4 Preview Update 2 retains all ten Xe3 backports and excludes the PR92 panel.

## Installer logs

Installer mode intentionally keeps `/storage` in RAM. Setting journald to
`Storage=persistent` cannot make that storage survive a restart, and the
normal `var-log.mount` intentionally excludes installer mode.

The installer collector starts after journald and before udev, independently
of the graphical clients. It records the current boot's complete journal and
follows new messages in `/flash/cb1-boot-logs/current.log`. At the next start,
that file becomes `previous.log`. Both are readable from the boot partition
on another computer, including after a failed boot. The header records the
kernel, system version, boot ID and command line.

Collection is limited to installer mode on its already mounted local FAT
boot partition. It never mounts another disk or changes `/storage`. Each
file is capped at 8 MiB; at most current and previous are retained. Collection
lasts at most ten minutes, reserves 128 MiB free for updates, flushes the
current file every second and restores the original read-only mount on exit.
Each journal record is flushed through the byte limiter immediately; a quiet
follow stream must not leave its final messages in a userspace output buffer.
An unavailable, full or read-only medium cannot block normal boot. A sudden
power loss can still lose recent writes; the collector cannot run before
journald or preserve a failure that prevents the kernel from scheduling it.
Logs are kept locally and may contain machine details; they are not uploaded.

## On-screen diagnostics

On detected NVIDIA display hardware, the native pre-udev driver selector raises
the kernel console log level, replays the early kernel messages to /dev/console,
and enables systemd status output. Kernel messages include audio/PCI events;
this does not depend on identifying a Xonar card. Kodi start/exit markers are
also sent to the console. These existing diagnostics remain enabled.

The journal collector is a separate durable copy, not a new crash-screen UI.
Once a graphical client owns the display, text is not guaranteed to remain
visible; a GPU/display failure or complete kernel lockup can prevent further
output. A silent driver failure cannot be turned into a message by logging.
On Intel/AMD hardware the existing normal console policy is retained; installer
file collection works independently of the GPU vendor.

## Comparison with Hades RC8

Compared against Hades RC8 commit `8ed4131907792183d73643975e22d96da3219786`:

| Component | CB1 Update 2 | Hades RC8 |
| --- | --- | --- |
| Linux | 7.2.6 plus CB1/Xe3 patches | 7.3.1 plus its patch stack |
| NVIDIA R615 | 615.78.08 | 615.78.08 |
| Virtuoso/oxygen C and header files | 28 files match upstream 7.3.1 byte-for-byte | None of 125 selected kernel patches touches that driver or mentions Xonar/CMI8788/ASM108x |
| Relevant kernel options | Virtuoso/oxygen modules, PCI MSI, IRQ remapping enabled | Same options enabled |
| Early persistent diagnostic journal | Installed-system NVIDIA diagnostics | Hades explicitly excludes installer mode too |
| NVIDIA startup ordering | Explicit `nvidia-kms.service` before Kodi/installer | No equivalent explicit service found in the pinned startup sources |

The previously confirmed mixed-kernel boot in Hades issue14 was a separate
failure; its later GRUB fix is not evidence of an audio-driver fix. The CB1
x86_64 USB image uses Syslinux. A targeted Xonar change is not established by
the reported successful Hades boots. Keep the card and MSI behavior intact
until a failed-boot trace distinguishes NVIDIA initialization, the PCI bridge,
interrupt handling and the graphical client.

References: [CB1 issue88](https://github.com/CroqueMr/libreelec-x86-DV/issues/88),
[Hades issue14](https://github.com/hadesdevls/LibreELEC-Hades/issues/14),
[Hades early journal owner](https://github.com/hadesdevls/LibreELEC-Hades/blob/8ed4131907792183d73643975e22d96da3219786/packages/sysutils/busybox/scripts/init).
