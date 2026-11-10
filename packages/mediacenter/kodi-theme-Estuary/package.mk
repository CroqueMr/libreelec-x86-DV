# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2009-2016 Stephan Raue (stephan@openelec.tv)
# Copyright (C) 2016-present Team LibreELEC (https://libreelec.tv)

PKG_NAME="kodi-theme-Estuary"
PKG_VERSION="1.0"
PKG_LICENSE="GPL-2.0-only AND CC-BY-SA-4.0"
PKG_SITE="http://www.kodi.tv"
PKG_URL=""
PKG_DEPENDS_TARGET="kodi"
PKG_DEPENDS_UNPACK="kodi"
# PKG_DEPENDS_UNPACK already tracks Kodi's global package directory.
PKG_NEED_UNPACK="${PROJECT_DIR}/${PROJECT}/patches/kodi ${PROJECT_DIR}/${PROJECT}/packages/kodi"
if [ -n "${DEVICE}" ]; then
  PKG_NEED_UNPACK+=" ${PROJECT_DIR}/${PROJECT}/devices/${DEVICE}/patches/kodi"
fi
PKG_LONGDESC="Kodi Mediacenter default theme."
PKG_TOOLCHAIN="manual"

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/share/kodi/addons/
    cp -a $(get_install_dir kodi)/.noinstall/skin.estuary ${INSTALL}/usr/share/kodi/addons/
}
