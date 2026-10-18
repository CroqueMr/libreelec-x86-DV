# R1.0.0 Beta4 build

Requires a Linux x86-64 build host and LibreELEC build dependencies.

Extract `R1.0.0-Beta4-sources.tar.zst` and
`R1.0.0-Beta4-vendor-inputs.tar.zst` into the same directory, then run:

```sh
cd libreelec-x86-DV
python3 scripts/verify-beta4-sources.py
CB1_HDR10_AI=yes PROJECT=Generic ARCH=x86_64 OFFICIAL=no make image
```

The source archive contains the release recipes, complete patched Kodi, FFmpeg,
libplacebo and Linux sources, CB1, the LightGBM model and dependency downloads.
The vendor archive contains firmware and NVIDIA redistribution inputs.
Original licenses and author notices are retained.

One Generic x86-64 image contains the Intel/AMD display paths, experimental
dedicated-GPU support and AMD HDMI 3D patches. Separate GPU-specific images are
not required. [Hardware coverage](HARDWARE.md) · [3D playback](3D.md).

The four patched component snapshots are used without reapplying their patches.
Source inventories and binary-payload identifiers are recorded in
`config/beta4-release-source.json` and `config/beta4-sources/`.

These archives are the corresponding source for Beta4. The GitHub release target
alone does not contain all candidate changes. Binary hashes may differ when
rebuilt because of timestamps, build paths and toolchain differences.
