# SPDX-License-Identifier: GPL-2.0-only
PKG_NAME="nvidia-pascal-modeset"
PKG_VERSION="580.196.07"
PKG_COMMIT="02e64bf229e77873c9df22ebcfed6a3e0b813206"
PKG_SHA256="5e9e92f1c70d1487a365179704ae14bab3eedfd60b5e005c214bba40a926db45"
PKG_ARCH="x86_64"
PKG_LICENSE="MIT AND GPL-2.0-only"
PKG_SITE="https://github.com/NVIDIA/open-gpu-kernel-modules"
PKG_URL="${PKG_SITE}/archive/${PKG_COMMIT}.tar.gz"
PKG_DEPENDS_TARGET="toolchain"
PKG_LONGDESC="Source-built R580 modeset core and DRM transport for the proprietary Pascal RM."
PKG_TOOLCHAIN="manual"
PKG_BUILD_FLAGS="-strip"

make_target() {
  unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
  make -C src/nvidia-modeset TARGET_ARCH=x86_64 \
    CC="${CC}" CXX="${CXX}" LD="${LD}" AR="${AR}" OBJCOPY="${OBJCOPY}"
}

makeinstall_target() {
  # The matching proprietary driver recipe consumes these build artifacts directly.
  :
}
