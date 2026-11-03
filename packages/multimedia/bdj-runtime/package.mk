# SPDX-License-Identifier: GPL-2.0-or-later

PKG_NAME="bdj-runtime"
PKG_VERSION="1.0"
PKG_ARCH="x86_64"
PKG_LICENSE="GPL-2.0-only WITH Classpath-exception-2.0"
PKG_DEPENDS_TARGET="toolchain libbluray libXi libXrender libXext chrome-libXtst jre-libXinerama"
PKG_DEPENDS_UNPACK="jdk-${TARGET_ARCH}-zulu"
PKG_LONGDESC="System Java runtime for native Blu-ray Java menus."
PKG_TOOLCHAIN="manual"

makeinstall_target() {
  local jre="$(get_build_dir jdk-${TARGET_ARCH}-zulu)/jre"
  test -x "${jre}/bin/java"
  test -s "${jre}/lib/amd64/server/libjvm.so"
  mkdir -p "${INSTALL}/usr/lib/jvm"
  cp -a "${jre}" "${INSTALL}/usr/lib/jvm/zulu8"
}
