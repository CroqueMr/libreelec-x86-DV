# NVIDIA startup: R580 candidate and KMS ordering

Local candidate based on RC3 (`80a9ab2d6218e0e83fb8e0ee4127bd5c60eced26`).
Not a claim of a successful physical GTX or Xonar boot.

## Matched driver families

- Maxwell/Pascal/Volta use R580 **580.196.07**: vendor userspace and closed RM,
  source-built modeset core and patched DRM of exactly the same release.
- Turing and newer retain R615 **615.78.08**. PCI classification and the existing
  policy for mixed families are unchanged. There is still one coherent family
  loaded per boot; this is not an attempt to load both `nvidia.ko` families.
- Before replacing the R580 core or DRM files, compare their vendor sources to
  the matching source archive. A retry also accepts the exact already-patched
  files, including the authoritative private KAPI header. Keep the closed-flavour
  DRM licence declaration and proprietary RM unchanged.

The matched R580 build and version choice follow the working implementation of
[Hades](https://github.com/hadesdevls/LibreELEC-Hades/blob/8ed4131907792183d73643975e22d96da3219786/packages/graphics/nvidia-legacy/package.mk),
by hadesdevls (recipe: GPL-2.0-only). Our existing transport patches are retained;
no Hades Kodi/DV processing code or GPLv3 component is imported. NVIDIA's
proprietary files retain their own licence. The R580 return-thunk fix was already
present in RC3 and is not a new fix here.

## Graphical-client ordering

Issue [#88](https://github.com/CroqueMr/libreelec-x86-DV/issues/88) shows Kodi's GUI
creation failing before `nvidia-drm` finishes initialising. Its installer capture
also shows the graphical client starting before NVIDIA KMS. Removing the Xonar
changes the reported outcome, but the captures do not demonstrate an ALSA fault.

For a supported NVIDIA display device only, the early selector generates a
systemd oneshot that runs native `modprobe nvidia-drm`. Kodi and the installer
both want and start after that service. There is no sleep, global udev settle,
sound-card blacklist, output override or rendering change. `Wants`, not `Requires`,
lets native Intel/AMD startup proceed if a secondary NVIDIA device fails.

The service has a 30-second start timeout; this is not a guarantee that the
kernel can cancel an uninterruptible GPU probe. Network/SSH services do not
depend on this unit. Module errors and unit completion remain in the native
boot journal and existing NVIDIA diagnostics.

## Evidence and remaining validation

Software checks exercise both families, non-display/audio PCI functions,
unknown IDs, Intel/AMD, source mismatch rejection and retry. Both complete
NVIDIA patch stacks replay on their pinned archives. All four R580 modules
compile against the RC3 kernel; no module is loaded by these checks.

Before release: cold/warm boots with GTX-only, hybrid graphics and RTX5090 plus
Xonar, installed and installer modes. Confirm one coherent driver family, KMS
completion before the graphical client, native output selection and working
audio. Recheck an NVIDIA-load failure with an Intel/AMD output available.

The Surface log attached to #72 also contains USB read errors, FAT failures and
SquashFS decompression failures, before module loading. A corrupted/unreadable
system image is a separate condition: changing driver selection cannot repair
those bytes. Keep it separate from the GTX-only reports and the #88 startup race.
