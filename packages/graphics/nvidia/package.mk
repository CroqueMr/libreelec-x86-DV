# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2021-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="nvidia"
PKG_VERSION="615.78.08"
PKG_SHA256="e9d5167f4ca67f58b2b3447584b1e4273218d5088aba210d3aef2a407e522892"
PKG_ARCH="x86_64"
PKG_LICENSE="LicenseRef-nonfree"
PKG_SITE="https://www.nvidia.com/en-us/drivers/unix/"
PKG_DEPENDS_TARGET="toolchain util-macros libglvnd nvidia-open-kernel-modules nvidia-pascal"
PKG_LONGDESC="NVIDIA R615 and R580 GBM drivers, selected coherently at early boot."
PKG_URL="https://download.nvidia.com/XFree86/Linux-x86_64/${PKG_VERSION}/NVIDIA-Linux-x86_64-${PKG_VERSION}-no-compat32.run"
PKG_TOOLCHAIN="manual"
PKG_BUILD_FLAGS="-strip"
PKG_IS_KERNEL_PKG="yes"
NVIDIA_BRANCH="r615"
if [ "${VULKAN_SUPPORT}" = yes ]; then
  PKG_DEPENDS_TARGET+=" ${VULKAN} vulkan-tools"
fi

source "${PKG_DIR}/common.mk"

post_makeinstall_target() {
  mkdir -p "${INSTALL}/usr/lib/nvidia-drivers/r615"
  cp "${PKG_DIR}/files/select-driver" "${INSTALL}/usr/lib/nvidia-drivers/"
  cp "${PKG_DIR}/files/hdr-depth.conf" "${INSTALL}/usr/lib/nvidia-drivers/r615/"
  python3 "${PKG_DIR}/generate-pci-map.py" \
    "${PKG_BUILD}/supported-gpus/supported-gpus.json" \
    "$(get_build_dir nvidia-pascal)/supported-gpus/supported-gpus.json" \
    "${INSTALL}/usr/lib/nvidia-drivers/pci-branches"
}
