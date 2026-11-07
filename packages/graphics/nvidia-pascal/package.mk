# SPDX-License-Identifier: GPL-2.0-only
PKG_NAME="nvidia-pascal"
PKG_VERSION="580.196.07"
PKG_SHA256="2189c47fa87ae45b7a166b58c3742dd1629035069cb0fb4103ed375229c55867"
PKG_ARCH="x86_64"
PKG_LICENSE="LicenseRef-nonfree"
PKG_SITE="https://www.nvidia.com/en-us/drivers/unix/"
PKG_URL="https://download.nvidia.com/XFree86/Linux-x86_64/${PKG_VERSION}/NVIDIA-Linux-x86_64-${PKG_VERSION}-no-compat32.run"
PKG_DEPENDS_TARGET="toolchain util-macros libglvnd nvidia_egl-gbm linux nvidia-pascal-modeset"
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
