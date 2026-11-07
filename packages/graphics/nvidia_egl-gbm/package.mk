# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="nvidia_egl-gbm"
PKG_VERSION="1.1.4"
PKG_SHA256="9738d7961550a67f2fcca5923374d1869ac214e00e96da6393b7206e3ef293e0"
PKG_LICENSE="MIT GPL-2.0-or-later"
PKG_SITE="https://github.com/NVIDIA/egl-gbm"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain libdrm eglexternalplatform mesa"
PKG_LONGDESC="NVIDIA GBM EGL external platform library (libnvidia-egl-gbm)"
PKG_TOOLCHAIN="meson"
# Upstream tag1.1.4 still builds the ABI filename1.1.3. Keep one source owner.
PKG_EGL_GBM_LIBVERSION="1.1.3"

pre_configure_target() {
  grep -q "^        version : '${PKG_EGL_GBM_LIBVERSION}',$" ${PKG_BUILD}/meson.build ||
    die "nvidia_egl-gbm: unexpected upstream library version"
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/share/egl/egl_external_platform.d
    cp -p ${PKG_BUILD}/src/15_nvidia_gbm.json                                   ${INSTALL}/usr/share/egl/egl_external_platform.d

  mkdir -p ${INSTALL}/usr/lib
    cp -p ${PKG_BUILD}/.${TARGET_NAME}/src/libnvidia-egl-gbm.so.${PKG_EGL_GBM_LIBVERSION}  ${INSTALL}/usr/lib
    ln -sf libnvidia-egl-gbm.so.${PKG_EGL_GBM_LIBVERSION}                                  ${INSTALL}/usr/lib/libnvidia-egl-gbm.so.1
    ln -sf libnvidia-egl-gbm.so.1                                               ${INSTALL}/usr/lib/libnvidia-egl-gbm.so
}
