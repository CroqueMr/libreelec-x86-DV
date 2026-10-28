# Pascal HDMI transport

Supported: NVIDIA GeForce GTX 10 series, using the matched R580 driver in the Generic image.

## Build

The Generic image contains NVIDIA **580.178.04** and **615.78.08** in isolated
payloads. LibreELEC selects one matching module, firmware and userspace stack
before systemd/udev. No separate Pascal image or build flag is required.

Selection uses the intersection of the pinned NVIDIA PCI-device lists for R580,
not retirement hints alone. A known NVIDIA boot VGA GPU
takes priority; otherwise a sole known family is selected. On mixed-family
machines without a unique known boot GPU, R615 is selected with a boot diagnostic;
the other family is unavailable. This does not select the connected monitor.
An unknown NVIDIA boot GPU gets no automatic NVIDIA module overlay. Intel/AMD-only
machines retain Mesa and do not load an NVIDIA overlay. Cross-family NVIDIA
hotplug requires a reboot. User module overlays cannot replace the matched stack.

The proprietary R580 resource manager and userspace libraries are retained.
The matching public R580 modeset core is rebuilt from source, with its private
DRM/KAPI adapter. The four modules, EGL, GBM, CUDA and NVDEC use the same version.
Pascal does not use the Turing-and-newer open resource manager.

## Transport

The connector exposes `NV_HDMI_VSIF_METADATA`, `max bpc` and `dithering mode`,
using the shared NVIDIA backend. No separate CB1 rendering implementation is required.

The private kernel-only modeset request carries the VSIF through native NVKMS
validation and commit. It does not change public userspace ioctl structures.
The native Pascal HDMI packet writer emits the VSIF. RGB8, full range, neutral
output transfer and disabled dithering are required. HDR metadata and a DV
override cannot be active together. A normal modeset clears the private override.

No vendor binary is patched. Source notices and the R580 redistribution license
are retained. NVIDIA RM and userspace remain proprietary.

## Supported outputs

| Output | Transport |
| --- | --- |
| Dolby Vision V1 / V2 | RGB8 tunnel and validated native HDMI vendor packet |
| HDR10 / HLG | Native NVIDIA output with separate PQ/HLG capability checks |
| Native or converted HDR10+ | Native HDMI YCbCr 4:2:2 at 10 bits, with frame-associated metadata |

HDR10+ requires a single native HDMI head without conflicting VRR, 3D, HDMI-VIC
or vendor-packet ownership. [Output requirements and limits](DRIVER-COVERAGE.md).

## Verification

Host tests exercise blob ownership, invalid requests, VSIF bounds, the actual
R580 HDMI builder and Pascal packet packer, including the HDMI checksum.
Package tests check both fixed dependencies, complete installation, explicit PCI
selection, conflicting overlays, repeated setup and incomplete-stack failures.
The complete-image checks verify both driver branches, their firmware, userspace
libraries, dependencies, module versions and early-boot selection. These checks
do not constitute Dolby or HDMI certification.

## Source versions

| Component | Source |
| --- | --- |
| Release | R1.0.0 RC1, one Generic image |
| NVIDIA proprietary payload | `580.178.04` |
| Public modeset sources | NVIDIA `c8e699821c23e4335bf23330a54a23d15cfb95e9` |
| Driver patch | `packages/graphics/nvidia-pascal-modeset/patches/nvidia-pascal-modeset-9000-dv-transport.patch` |

The new code is limited to transport and packaging. CB1 algorithms, generated
metadata, codecs and existing Intel/AMD/NVIDIA rendering paths are unchanged.
