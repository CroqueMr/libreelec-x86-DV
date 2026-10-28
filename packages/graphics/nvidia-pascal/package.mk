# SPDX-License-Identifier: GPL-2.0-only
PKG_NAME="nvidia-pascal"
PKG_VERSION="580.178.04"
PKG_SHA256="1833c8c5c53481dfab46df442c3de26ec5d4c35084e03d94ad93746d29899750"
PKG_ARCH="x86_64"
PKG_LICENSE="LicenseRef-nonfree"
PKG_SITE="https://www.nvidia.com/en-us/drivers/unix/"
PKG_URL="https://download.nvidia.com/XFree86/Linux-x86_64/${PKG_VERSION}/NVIDIA-Linux-x86_64-${PKG_VERSION}-no-compat32.run"
PKG_DEPENDS_TARGET="toolchain util-macros libglvnd linux nvidia-pascal-modeset"
PKG_LONGDESC="Matched R580 userspace and source-built Pascal modeset/DRM driver."
PKG_TOOLCHAIN="manual"
PKG_BUILD_FLAGS="-strip"
PKG_IS_KERNEL_PKG="yes"
PKG_NEED_UNPACK="${ROOT}/packages/graphics/nvidia/common.mk"
NVIDIA_BRANCH="r580"
if [ "${VULKAN_SUPPORT}" = yes ]; then
  PKG_DEPENDS_TARGET+=" ${VULKAN} vulkan-tools"
fi
source "${ROOT}/packages/graphics/nvidia/common.mk"
