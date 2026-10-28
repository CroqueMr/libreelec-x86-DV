# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026-present Hades

PKG_NAME="nvidia-open-kernel-modules"
PKG_VERSION="615.78.08"
PKG_COMMIT="1a82fbfda8f321b056eb3568850f9316c5e465c5"
PKG_SHA256="590ee6a5a780f946322edd17f9d235c6664eb7e6839073ac0d68c0f263e7184f"
PKG_ARCH="x86_64"
PKG_LICENSE="MIT OR GPL-2.0-only"
PKG_SITE="https://github.com/NVIDIA/open-gpu-kernel-modules"
PKG_URL="${PKG_SITE}/archive/${PKG_COMMIT}.tar.gz"
PKG_DEPENDS_TARGET="toolchain linux"
PKG_LONGDESC="NVIDIA open GPU kernel modules (Turing and later), built entirely from source."
PKG_TOOLCHAIN="manual"

PKG_IS_KERNEL_PKG="yes"

make_target() {
  # The OS-agnostic parts (src/nvidia, src/nvidia-modeset) are compiled from source instead of
  # using the prebuilt nv-*-kernel.o_binary objects of the driver .run. Build with the same
  # compiler as the kernel and without the target's user-space flags.
  unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS

  # Keep the in-kernel client and independently source-built NVKMS layout matched.
  cp src/nvidia-modeset/kapi/interface/nvkms-kapi.h kernel-open/common/inc/
  cp src/common/inc/nvkms-cb1-hdr.h kernel-open/common/inc/

  make modules \
    TARGET_ARCH=x86_64 \
    ARCH=x86_64 \
    CC=${CC} \
    LD=${LD} \
    AR=${AR} \
    CXX=${CXX} \
    OBJCOPY=${OBJCOPY} \
    SYSSRC=$(kernel_path) \
    SYSOUT=$(kernel_path)

  ${STRIP} --strip-debug kernel-open/nvidia.ko \
                         kernel-open/nvidia-modeset.ko \
                         kernel-open/nvidia-drm.ko \
                         kernel-open/nvidia-uvm.ko
}

makeinstall_target() {
  mkdir -p ${INSTALL}/$(get_full_module_dir)/nvidia
    cp -P kernel-open/nvidia.ko         ${INSTALL}/$(get_full_module_dir)/nvidia
    cp -P kernel-open/nvidia-drm.ko     ${INSTALL}/$(get_full_module_dir)/nvidia
    cp -P kernel-open/nvidia-uvm.ko     ${INSTALL}/$(get_full_module_dir)/nvidia
    cp -P kernel-open/nvidia-modeset.ko ${INSTALL}/$(get_full_module_dir)/nvidia
}
