# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2023-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="libplacebo"
PKG_VERSION="e2972fdd09adacd383656738d7d280f0cd84a761"
PKG_SHA256="2dc029b7686455054fb5e76dd8c084cbf4fa4159f33364c5b7f9afc8b3611811"
PKG_LICENSE="LGPL-2.1-or-later"
PKG_SITE="https://code.videolan.org/videolan/libplacebo"
PKG_URL="https://github.com/haasn/libplacebo/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain glad:host Jinja2:host"
PKG_DEPENDS_UNPACK="vulkan-headers"
PKG_LONGDESC="Reusable library for GPU-accelerated image/video processing primitives and shaders"
PKG_BUILD_FLAGS=""

PKG_MESON_OPTS_TARGET="-Ddefault_library=shared \
                       -Dprefer_static=true \
                       -Dvulkan=disabled \
                       -Dvk-proc-addr=disabled \
                       -Dd3d11=disabled \
                       -Dglslang=disabled \
                       -Dshaderc=disabled \
                       -Dlcms=disabled \
                       -Ddovi=enabled \
                       -Dlibdovi=disabled \
                       -Ddemos=false"

if [ "${OPENGLES_SUPPORT}" = "yes" ]; then
  PKG_DEPENDS_TARGET+=" ${OPENGLES}"
  PKG_MESON_OPTS_TARGET+=" -Dopengl=enabled -Dgl-proc-addr=enabled"
else
  PKG_MESON_OPTS_TARGET+=" -Dopengl=disabled -Dgl-proc-addr=disabled"
fi

pre_configure_target() {
  # Normalize __FILE__ and debug paths; do not change rendering or optimization flags.
  export TARGET_CFLAGS+=" -I$(get_build_dir vulkan-headers)/include -ffile-prefix-map=${ROOT}=/usr/src/libreelec"
  export TARGET_CXXFLAGS+=" -ffile-prefix-map=${ROOT}=/usr/src/libreelec"
}

post_makeinstall_target() {
  sed 's/^Libs:.*-lplacebo/& -lstdc++/' -i ${INSTALL}/usr/lib/pkgconfig/libplacebo.pc
}
