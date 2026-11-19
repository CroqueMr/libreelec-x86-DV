# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2022-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="nvidia-vaapi-driver"
# Hades: 0.0.18 + PR #461 (allocation ABI of drivers 545+) + PR #456 (context, surface and
# dma-buf lifetimes with two decoders, as FEL uses) + the get_device_uuid fix + PR #465 (the
# queue of decoded pictures grows instead of overwriting entries) + #460, #469, #470, #471,
# #472 and #473 (AV1, VP8, VC-1, picture indices, image pitches, 12-bit export) + #479 (a file
# descriptor that CUDA has taken is not closed a second time when its import fails); master
# commit of 2026-10-11, reviewed
PKG_VERSION="443050726fdb30888a2ced1cea1c5d036ea3b15c"
PKG_SHA256="eb19284e5e8005efdb52341c4f5e55173423bdb095b90285392cc35aa724094e"
PKG_LICENSE="MIT"
PKG_SITE="https://github.com/elFarto/nvidia-vaapi-driver"
PKG_URL="https://github.com/elFarto/nvidia-vaapi-driver/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain libva nv-codec-headers gst-plugins-bad"
PKG_LONGDESC="A VA-API implementation using NVIDIA's NVDEC"
