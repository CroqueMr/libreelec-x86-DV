# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2021-present Team LibreELEC (https://libreelec.tv)
# Shared native NVIDIA payload extraction and installation.
unpack() {
  # Extract the self-extracting .run without executing it. Its makeself header checks the
  # payload with cksum and md5sum over "tail -n +4" and extracts it with
  # "tail -n +${skip} | zstd -d | tar x"; do the same, and stop on any mismatch.
  local run="${SOURCES}/${PKG_NAME}/${PKG_SOURCE_NAME}"
  local skip crc md5
  skip=$(head -n 20 "${run}" | sed -n 's/^skip=\([0-9]\+\)$/\1/p')
  crc=$(head -n 20 "${run}" | sed -n 's/^CRCsum=\([0-9]\+\)$/\1/p')
  md5=$(head -n 20 "${run}" | sed -n 's/^MD5=\([0-9a-f]\{32\}\)$/\1/p')
  [ -n "${skip}" -a -n "${crc}" -a -n "${md5}" ] || die "nvidia: unexpected .run header"
  [ "$(tail -n +4 "${run}" | cksum | cut -d' ' -f1)" = "${crc}" ] || die "nvidia: .run CRC mismatch"
  [ "$(tail -n +4 "${run}" | md5sum | cut -b-32)" = "${md5}" ] || die "nvidia: .run MD5 mismatch"

  [ -d ${PKG_BUILD} ] && rm -rf ${PKG_BUILD}
  mkdir -p ${PKG_BUILD}
  tail -n +${skip} "${run}" | zstd -dq | tar -xf - -C ${PKG_BUILD} --no-same-owner
}

make_target() {
  if [ "${NVIDIA_BRANCH}" = r580 ]; then
    local public="$(get_build_dir nvidia-pascal-modeset)"
    # Keep RM proprietary; build the modified modeset core and DRM adapter from source.
    cp "${public}/src/nvidia-modeset/_out/Linux_x86_64/nv-modeset-kernel.o" \
       "${PKG_BUILD}/kernel/nvidia-modeset/nv-modeset-kernel.o_binary"
    cp "${public}/src/nvidia-modeset/kapi/interface/nvkms-kapi.h" \
       "${public}/src/common/inc/nvkms-cb1-vsif.h" \
       "${public}/src/common/inc/nvkms-cb1-hdr10plus.h" "${PKG_BUILD}/kernel/common/inc/"
    local name
    for name in nvidia-drm-connector.c nvidia-drm-connector.h nvidia-drm-drv.c nvidia-drm-priv.h nvidia-drm-modeset.c; do
      cp "${public}/kernel-open/nvidia-drm/${name}" "${PKG_BUILD}/kernel/nvidia-drm/${name}"
    done
    make -C "${PKG_BUILD}/kernel" modules \
      NV_KERNEL_MODULES="nvidia nvidia-modeset nvidia-drm nvidia-uvm" \
      CC="${CC}" LD="${LD}" SYSSRC="$(kernel_path)" SYSOUT="$(kernel_path)"
  fi
}

makeinstall_target() {
  if [ "${NVIDIA_BRANCH}" = r580 ]; then
    mkdir -p "${INSTALL}/$(get_full_module_dir nvidia-${NVIDIA_BRANCH})/nvidia"
    local module
    for module in nvidia nvidia-modeset nvidia-drm nvidia-uvm; do
      cp -p "kernel/${module}.ko" "${INSTALL}/$(get_full_module_dir nvidia-${NVIDIA_BRANCH})/nvidia/"
    done
  fi
  local image_install="${INSTALL}"
  local payload="/usr/lib/nvidia-drivers/${NVIDIA_BRANCH}"
  # Hades: the agreement that NVIDIA's files come under goes wherever they go. The copy in
  # licenses/, which the release .tar and the boot partition of the image carry, has to be the one
  # of this driver.
  cmp -s LICENSE ${ROOT}/licenses/LicenseRef-NVIDIA-Driver-License-Agreement.txt || \
    die "nvidia: licenses/LicenseRef-NVIDIA-Driver-License-Agreement.txt is not the LICENSE of this driver"
  mkdir -p "${INSTALL}${payload}/usr/share/licenses/nvidia"
  cp -p LICENSE "${INSTALL}${payload}/usr/share/licenses/nvidia"
  printf "%s\n" "${PKG_VERSION}" >"${INSTALL}${payload}/driver-version"

  # GSP firmware and the ucode images the open kernel modules also request
  mkdir -p ${INSTALL}/$(get_full_firmware_dir nvidia-${NVIDIA_BRANCH})/nvidia/${PKG_VERSION}
    cp firmware/gsp*.bin           ${INSTALL}/$(get_full_firmware_dir nvidia-${NVIDIA_BRANCH})/nvidia/${PKG_VERSION}
    if [ "${NVIDIA_BRANCH}" != r580 ]; then
      cp firmware/ucodes*.bin      ${INSTALL}/$(get_full_firmware_dir nvidia-${NVIDIA_BRANCH})/nvidia/${PKG_VERSION}
    fi

  # All vendor userspace lives in one branch-local root.
  INSTALL="${image_install}${payload}"

  # GBM
  mkdir -p ${INSTALL}/usr/lib/gbm
    cp -p libnvidia-allocator.so.${PKG_VERSION}     ${INSTALL}/usr/lib
    ln -sf libnvidia-allocator.so.${PKG_VERSION}    ${INSTALL}/usr/lib/liballocator.so.0
    ln -sf ../libnvidia-allocator.so.${PKG_VERSION} ${INSTALL}/usr/lib/gbm/nvidia-drm_gbm.so

  # GLVND
  mkdir -p ${INSTALL}/usr/share/glvnd/egl_vendor.d
    cp -p 10_nvidia.json ${INSTALL}/usr/share/glvnd/egl_vendor.d

  # Wayland
  mkdir -p ${INSTALL}/usr/lib
    cp -p libnvidia-egl-wayland.so.1.1.20  ${INSTALL}/usr/lib/
    ln -sf libnvidia-egl-wayland.so.1.1.20 ${INSTALL}/usr/lib/libnvidia-egl-wayland.so.1
    ln -sf libnvidia-egl-wayland.so.1     ${INSTALL}/usr/lib/libnvidia-egl-wayland.so

  mkdir -p ${INSTALL}/usr/share/egl/egl_external_platform.d
    cp -p 10_nvidia_wayland.json ${INSTALL}/usr/share/egl/egl_external_platform.d

  # EGL-GBM
  mkdir -p ${INSTALL}/usr/lib
    cp -p libnvidia-egl-gbm.so.1.1.3 ${INSTALL}/usr/lib/
    ln -sf libnvidia-egl-gbm.so.1.1.3 ${INSTALL}/usr/lib/libnvidia-egl-gbm.so.1
    ln -sf libnvidia-egl-gbm.so.1 ${INSTALL}/usr/lib/libnvidia-egl-gbm.so

  mkdir -p ${INSTALL}/usr/share/egl/egl_external_platform.d
    cp -p 15_nvidia_gbm.json ${INSTALL}/usr/share/egl/egl_external_platform.d

  # OpenGL / EGL
  mkdir -p ${INSTALL}/usr/lib
    cp -p libEGL_nvidia.so.${PKG_VERSION}  ${INSTALL}/usr/lib/
    ln -sf libEGL_nvidia.so.${PKG_VERSION} ${INSTALL}/usr/lib/libEGL_nvidia.so.0
    ln -sf libEGL_nvidia.so.0              ${INSTALL}/usr/lib/libEGL_nvidia.so

  # OpenGL core
  mkdir -p ${INSTALL}/usr/lib
    cp -p libnvidia-eglcore.so.${PKG_VERSION}  ${INSTALL}/usr/lib/
    ln -sf libnvidia-eglcore.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvidia-eglcore.so
    cp -p libnvidia-glsi.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libnvidia-glsi.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvidia-glsi.so

  # OpenGL ES
  mkdir -p ${INSTALL}/usr/lib
    cp -p libGLESv2_nvidia.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libGLESv2_nvidia.so.${PKG_VERSION} ${INSTALL}/usr/lib/libGLESv2_nvidia.so.2
    ln -sf libGLESv2_nvidia.so.2              ${INSTALL}/usr/lib/libGLESv2_nvidia.so

  # Vulkan
  if [ "${VULKAN_SUPPORT}" = "yes" ]; then
    mkdir -p ${INSTALL}/usr/lib
      cp -P libnvidia-glvkspirv.so.${PKG_VERSION}  ${INSTALL}/usr/lib
      ln -sf libnvidia-glvkspirv.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvidia-glvkspirv.so

    mkdir -p ${INSTALL}/usr/share/vulkan/implicit_layer.d
      sed "s#libGLX_nvidia.so.0#libEGL_nvidia.so.0#" nvidia_layers.json >${INSTALL}/usr/share/vulkan/implicit_layer.d/nvidia_layers.json
    mkdir -p ${INSTALL}/usr/share/vulkan/icd.d
      sed "s#libGLX_nvidia.so.0#libEGL_nvidia.so.0#" nvidia_icd.json >${INSTALL}/usr/share/vulkan/icd.d/nvidia_icd.json
  fi

  # CUDA
  mkdir -p ${INSTALL}/usr/lib
    cp -p libcuda.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libcuda.so.${PKG_VERSION} ${INSTALL}/usr/lib/libcuda.so.1
    ln -sf libcuda.so.1              ${INSTALL}/usr/lib/libcuda.so

  # NVDEC
  mkdir -p ${INSTALL}/usr/lib
    cp -p libnvcuvid.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libnvcuvid.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvcuvid.so.1
    ln -sf libnvcuvid.so.1              ${INSTALL}/usr/lib/libnvcuvid.so

  # nvidia-gpucomp
  mkdir -p ${INSTALL}/usr/lib
    cp -P libnvidia-gpucomp.so.${PKG_VERSION} ${INSTALL}/usr/lib

  # nvidia-tls
  mkdir -p ${INSTALL}/usr/lib
    cp -P libnvidia-tls.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libnvidia-tls.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvidia-tls.so

  # NVIDIA Management Library (NVML) / System Management Interface
  mkdir -p ${INSTALL}/usr/bin
    cp -P nvidia-smi ${INSTALL}/usr/bin
    # fake nvidia-modprobe
    ln -s /usr/bin/false ${INSTALL}/usr/bin/nvidia-modprobe

  mkdir -p ${INSTALL}/usr/lib
    cp -P libnvidia-ml.so.${PKG_VERSION}  ${INSTALL}/usr/lib
    ln -sf libnvidia-ml.so.${PKG_VERSION} ${INSTALL}/usr/lib/libnvidia-ml.so.1
    ln -sf libnvidia-ml.so.1              ${INSTALL}/usr/lib/libnvidia-ml.so

  # App profiles
  mkdir -p ${INSTALL}/usr/share/nvidia
    cp -P nvidia-application-profiles-${PKG_VERSION}-rc ${INSTALL}/usr/share/nvidia

  INSTALL="${image_install}"
  # Global entry points dispatch through a single early-boot selection.
  local file relative
  while IFS= read -r file; do
    relative="${file#${INSTALL}${payload}/}"
    mkdir -p "${INSTALL}/$(dirname "${relative}")"
    ln -sf "/run/nvidia-driver/${relative}" "${INSTALL}/${relative}"
  done < <(find "${INSTALL}${payload}/usr" \
    \( -type f -o -type l \) ! -path "*/share/licenses/*" | sort)
  find "${INSTALL}${payload}/usr" \( -type f -o -type l \) \
    | sed "s|^${INSTALL}${payload}/||" | sort >"${INSTALL}${payload}/required-userspace"
  local firmware="${INSTALL}/$(get_full_firmware_dir nvidia-${NVIDIA_BRANCH})"
  find "${firmware}/nvidia/${PKG_VERSION}" -type f \
    | sed "s|^${firmware}/||" | sort >"${INSTALL}${payload}/required-firmware"
}

