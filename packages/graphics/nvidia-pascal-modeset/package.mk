# SPDX-License-Identifier: GPL-2.0-only
PKG_NAME="nvidia-pascal-modeset"
PKG_VERSION="580.178.04"
PKG_COMMIT="c8e699821c23e4335bf23330a54a23d15cfb95e9"
PKG_SHA256="6aef3721780e35ddfe222f11eef854baf5c706544f5d9d14c6dc5a5be73401b9"
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
