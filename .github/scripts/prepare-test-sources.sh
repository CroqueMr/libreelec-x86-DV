#!/bin/bash
# SPDX-License-Identifier: MIT
# Prepare the actual patched sources, not concatenated diff fragments.
set -euo pipefail
shopt -s nullglob
export LC_ALL=C

pin() {
  awk -F '"' -v key="$1" '$1 == key "=" {print $2; exit}' "$2"
}

download() {
  curl --fail --silent --show-error --location --retry 3 "$1" --output "$2"
  printf '%s  %s\n' "$3" "$2" | sha256sum --check
}

test_root=$(mktemp -d "${RUNNER_TEMP:?}/cb1-tests.XXXXXX")
kodi_recipe=packages/mediacenter/kodi/package.mk
kodi_version=$(pin PKG_VERSION "$kodi_recipe")
kodi_fork=$(pin CB1_KODI_SOURCE_REPOSITORY "$kodi_recipe")
kodi_revision=$(pin CB1_KODI_SOURCE_COMMIT "$kodi_recipe")
ffmpeg_recipe=packages/multimedia/ffmpeg/package.mk
ffmpeg_version=$(pin PKG_VERSION "$ffmpeg_recipe")
ffmpeg_fork=$(pin CB1_FFMPEG_SOURCE_REPOSITORY "$ffmpeg_recipe")
ffmpeg_revision=$(pin CB1_FFMPEG_SOURCE_COMMIT "$ffmpeg_recipe")
placebo_recipe=packages/addons/addon-depends/multimedia-tools-depends/libplacebo/package.mk
placebo_fork=$(pin CB1_PLACEBO_SOURCE_REPOSITORY "$placebo_recipe")
placebo_revision=$(pin CB1_PLACEBO_SOURCE_COMMIT "$placebo_recipe")
engine_recipe=packages/multimedia/cb1-engine/package.mk
engine_fork=$(pin PKG_SITE "$engine_recipe")
engine_revision=$(pin PKG_VERSION "$engine_recipe")
bluray_recipe=packages/multimedia/libbluray/package.mk
bluray_fork=$(pin CB1_BLURAY_SOURCE_REPOSITORY "$bluray_recipe")
bluray_revision=$(pin CB1_BLURAY_SOURCE_COMMIT "$bluray_recipe")
# Generic kernel fixtures use the same pinned source as the Generic image.
PROJECT=Generic DEVICE=Generic ARCH=x86_64 bash tools/pkginfo linux PKG_SHA256 > "$test_root/linux-recipe"
linux_url=$(pin PKG_URL "$test_root/linux-recipe")
linux_sha=$(pin PKG_SHA256 "$test_root/linux-recipe")
test -n "$linux_url" && test -n "$linux_sha"

test -n "$kodi_version" && test -n "$ffmpeg_version" && test -n "$placebo_revision" && test -n "$bluray_revision"
download "https://github.com/xbmc/xbmc/archive/$kodi_version.tar.gz" \
  "$test_root/kodi.tar.gz" "$(pin PKG_SHA256 "$kodi_recipe")"
download "$kodi_fork/archive/$kodi_revision.tar.gz" \
  "$test_root/kodi-cb1.tar.gz" "$(pin CB1_KODI_SOURCE_SHA256 "$kodi_recipe")"
# Retain the original archive as input to tests that inspect historical patches.
download "https://ffmpeg.org/releases/ffmpeg-$ffmpeg_version.tar.xz" \
  "$test_root/ffmpeg.tar.xz" "$(pin PKG_SHA256 "$ffmpeg_recipe")"
download "$ffmpeg_fork/archive/$ffmpeg_revision.tar.gz" \
  "$test_root/ffmpeg-cb1.tar.gz" "$(pin CB1_FFMPEG_SOURCE_SHA256 "$ffmpeg_recipe")"
download "$placebo_fork/archive/$placebo_revision.tar.gz" \
  "$test_root/libplacebo.tar.gz" "$(pin CB1_PLACEBO_SOURCE_SHA256 "$placebo_recipe")"
download "$engine_fork/archive/$engine_revision.tar.gz" \
  "$test_root/engine.tar.gz" "$(pin PKG_SHA256 "$engine_recipe")"
download "$bluray_fork/archive/$bluray_revision.tar.gz" \
  "$test_root/libbluray.tar.gz" "$(pin CB1_BLURAY_SOURCE_SHA256 "$bluray_recipe")"

download "$linux_url" \
  "$test_root/linux.tar.xz" "$linux_sha"

python3 scripts/cb1-stage.py
mkdir "$test_root/engine" "$test_root/kodi" "$test_root/ffmpeg" "$test_root/libplacebo" "$test_root/libbluray" "$test_root/linux"
tar -xf "$test_root/engine.tar.gz" -C "$test_root/engine" --strip-components=1
tar -xf "$test_root/kodi-cb1.tar.gz" -C "$test_root/kodi" --strip-components=1
tar -xf "$test_root/ffmpeg-cb1.tar.gz" -C "$test_root/ffmpeg" --strip-components=1
tar -xf "$test_root/libplacebo.tar.gz" -C "$test_root/libplacebo" --strip-components=1
tar -xf "$test_root/libbluray.tar.gz" -C "$test_root/libbluray" --strip-components=1
tar -xf "$test_root/linux.tar.xz" -C "$test_root/linux" --strip-components=1

# Verify the Generic kernel stack against the same pinned source as the package build.
for patch_file in packages/linux/patches/default/*.patch projects/Generic/patches/linux/*.patch; do
  patch --batch --forward --fuzz=0 -p1 -d "$test_root/linux" < "$patch_file"
done

python3 "$test_root/engine/tools/verify.py" --ffmpeg-source "$test_root/ffmpeg" \
  --libplacebo-source "$test_root/libplacebo"
# Build the pinned OpenGL backend for CPU probes and the native EGL surface regression.
meson setup "$test_root/placebo-build" "$test_root/libplacebo" --wrap-mode=nofallback \
  --prefix="$test_root/prefix" --libdir=lib \
  -Ddemos=false -Dvulkan=disabled -Dopengl=enabled -Dd3d11=disabled \
  -Dglslang=disabled -Dshaderc=disabled -Dlcms=disabled -Dlibdovi=disabled \
  -Dunwind=disabled -Dxxhash=disabled
meson compile -C "$test_root/placebo-build" -j2
meson install -C "$test_root/placebo-build"
(
  cd "$test_root/ffmpeg"
  ./configure --prefix="$test_root/prefix" --disable-everything --disable-programs \
    --disable-doc --disable-network --disable-autodetect --disable-x86asm \
    --enable-gpl --enable-version3 --enable-shared --disable-static \
    --enable-filter=buffer,buffersink,hstack,settb --enable-decoder=hevc,pgssub,vp9 \
    --enable-demuxer=mov,mpegts,matroska --enable-parser=hevc,ac3,vp9 --enable-protocol=file \
    --enable-bsf=hevc_mp4toannexb,dovi_split,extract_extradata
  make -j2
  make install
)
printf '%s\n' \
  "CB1_TEST_ENGINE=$test_root/engine" \
  "KODI_NATIVE_SOURCE_TREE=$test_root/kodi" \
  "KODI_UPSTREAM_ARCHIVE=$test_root/kodi.tar.gz" \
  "CB1_DRM_STATE_SOURCE=$test_root/kodi" \
  "CB1_KERNEL_SOURCE=$test_root/linux" \
  "FFMPEG_TEST_PREFIX=$test_root/prefix" \
  "FFMPEG_PGS_TEST_PREFIX=$test_root/prefix" \
  "LIBBLURAY_TEST_INCLUDE=$test_root/libbluray/src" \
  "CPATH=$test_root/libplacebo/src/include:$test_root/placebo-build/src/include" \
  "CB1_FMT_INCLUDE=/usr/include" \
  "FFMPEG_MATCHED_SOURCE=$test_root/ffmpeg" \
  "FFMPEG_SOURCE_ARCHIVE=$test_root/ffmpeg.tar.xz" \
  "LD_LIBRARY_PATH=$test_root/prefix/lib" >> "${GITHUB_ENV:?}"
