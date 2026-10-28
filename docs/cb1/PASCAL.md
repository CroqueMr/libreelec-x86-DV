# Pascal HDMI transport

Status: software-qualified prototype, not hardware-qualified Dolby Vision support.

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
reusing Beta5's NVIDIA backend. No CB1 rendering changes are required.

The private kernel-only modeset request carries the VSIF through native NVKMS
validation and commit. It does not change public userspace ioctl structures.
The native Pascal HDMI packet writer emits the VSIF. RGB8, full range, neutral
output transfer and disabled dithering are required. HDR metadata and a DV
override cannot be active together. A normal modeset clears the private override.

No vendor binary is patched. Source notices and the R580 redistribution license
are retained. NVIDIA RM and userspace remain proprietary.

## Qualification

Host tests exercise blob ownership, invalid requests, VSIF bounds, the actual
R580 HDMI builder and Pascal packet packer, including the HDMI checksum.
Package tests check both fixed dependencies, complete installation, explicit PCI
selection, conflicting overlays, repeated setup and incomplete-stack failures.
These checks do not establish that proprietary RM accepts the packet on a
physical Pascal connector, or that the final scanout preserves every video byte.

Before calling this supported: test HDMI DV entry/exit, SDR/HDR restoration,
TEST_ONLY and failed commits, OSD/subtitles, hotplug, GBM/EGL/NVDEC playback and
the final wire signal on a Pascal card. No such hardware result is available.

## Source versions

| Component | Source |
| --- | --- |
| Base product | Beta5 normal, `abde400bbf8ef754c971f437dc321bdd03a5986b` |
| NVIDIA proprietary payload | `580.178.04` |
| Public modeset sources | NVIDIA `c8e699821c23e4335bf23330a54a23d15cfb95e9` |
| Driver patch | `packages/graphics/nvidia-pascal-modeset/patches/nvidia-pascal-modeset-9000-dv-transport.patch` |

The new code is limited to transport and packaging. CB1 algorithms, generated
metadata, codecs and existing Intel/AMD/NVIDIA rendering paths are unchanged.
