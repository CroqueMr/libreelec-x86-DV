# Experimental Pascal HDMI transport

Status: software-qualified prototype, not hardware-qualified Dolby Vision support.

## Build

Set `CB1_NVIDIA_PASCAL=yes` in a separate Generic OpenGLES build environment.
This selects NVIDIA **580.178.04** instead of **615.78.08**. Do not reuse an
existing image's staged modules or userspace libraries across these variants.
The default build is unchanged. This prototype does not select drivers at boot.

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
Package tests check default/opt-in dependency selection and installation.
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
