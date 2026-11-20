# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2009-2016 Stephan Raue (stephan@openelec.tv)
# Copyright (C) 2018-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="libbluray"
# also bump packages/addons/tools/jre.zulu/package.mk
PKG_VERSION="1.5.0"
PKG_SHA256="f676408e91a5d321abf8b8d4dfdae36205c297dab5c54c3ec519639025f474a2"
PKG_LICENSE="LGPL-2.1-or-later"
PKG_SITE="https://www.videolan.org/developers/libbluray.html"
PKG_URL="http://download.videolan.org/pub/videolan/libbluray/${PKG_VERSION}/${PKG_NAME}-${PKG_VERSION}.tar.xz"
PKG_DEPENDS_TARGET="toolchain fontconfig freetype libxml2 libudfread"
PKG_LONGDESC="libbluray is an open-source library designed for Blu-Ray Discs playback for media players."

if [ "${BLURAY_AACS_SUPPORT}" = "yes" ]; then
  PKG_DEPENDS_TARGET+=" libaacs"
fi

if [ "${BLURAY_BDPLUS_SUPPORT}" = "yes" ]; then
  PKG_DEPENDS_TARGET+=" libbdplus"
fi

PKG_MESON_OPTS_TARGET="-Ddefault_library=shared \
                       -Denable_docs=false \
                       -Denable_tools=false \
                       -Denable_devtools=false \
                       -Denable_examples=false \
                       -Dbdj_jar=disabled \
                       -Dembed_udfread=true \
                       -Dfontconfig=enabled \
                       -Dfreetype=enabled \
                       -Dlibxml2=enabled"

CB1_BLURAY_SOURCE_REPOSITORY="https://github.com/CroqueMr/libbluray-cb1"
CB1_BLURAY_SOURCE_COMMIT="93addf91e6b9447bf523f3cb383fb36d25b53087"
CB1_BLURAY_SOURCE_SHA256="19850f976567a51a275d231ae15b5814878782ef79e644157e9bdb3d107a06f0"

if [ "${PROJECT}" = "Generic" ] && [ "${TARGET_ARCH}" = "x86_64" ]; then
  PKG_VERSION="1.5.1"
  PKG_URL="${CB1_BLURAY_SOURCE_REPOSITORY}/archive/${CB1_BLURAY_SOURCE_COMMIT}.tar.gz"
  PKG_SOURCE_NAME="${PKG_NAME}-${CB1_BLURAY_SOURCE_COMMIT}.tar.gz"
  PKG_SOURCE_DIR="libbluray-cb1-${CB1_BLURAY_SOURCE_COMMIT}"
  PKG_SHA256="${CB1_BLURAY_SOURCE_SHA256}"
  PKG_SKIP_PATCHES="yes"
  PKG_DEPENDS_UNPACK+=" jdk-${MACHINE_HARDWARE_NAME}-zulu cb1-udfread-source"
fi

post_unpack() {
  if [ "${PROJECT}" = "Generic" ] && [ "${TARGET_ARCH}" = "x86_64" ]; then
    # Source archives do not include Git submodules. Keep the original vendored revision.
    cp -a "$(get_build_dir cb1-udfread-source)/." "${PKG_BUILD}/contrib/libudfread/"
  fi
}

configure_package() {
  if [ "${PROJECT}" = "Generic" ] && [ "${TARGET_ARCH}" = "x86_64" ]; then
    PKG_DEPENDS_TARGET+=" apache-ant:host"
    PKG_MESON_OPTS_TARGET="${PKG_MESON_OPTS_TARGET/bdj_jar=disabled/bdj_jar=enabled}"
  fi
}

pre_configure_target() {
  if [ "${PROJECT}" = "Generic" ] && [ "${TARGET_ARCH}" = "x86_64" ]; then
    export JAVA_HOME="$(get_build_dir jdk-${MACHINE_HARDWARE_NAME}-zulu)"
    export PATH+=":${JAVA_HOME}/bin"
    PKG_MESON_OPTS_TARGET+=" -Djdk_home=${JAVA_HOME}"
  fi
}

post_makeinstall_target() {
  if [ "${PROJECT}" = "Generic" ] && [ "${TARGET_ARCH}" = "x86_64" ]; then
    test -s "${INSTALL}/usr/share/java/libbluray-j2se-${PKG_VERSION}.jar"
    test -s "${INSTALL}/usr/share/java/libbluray-awt-j2se-${PKG_VERSION}.jar"
  fi
}
