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
kodi_version=$(pin PKG_VERSION packages/mediacenter/kodi/package.mk)
ffmpeg_version=$(pin PKG_VERSION packages/multimedia/ffmpeg/package.mk)
placebo_recipe=packages/addons/addon-depends/multimedia-tools-depends/libplacebo/package.mk
placebo_version=$(pin PKG_VERSION "$placebo_recipe")
test -n "$kodi_version" && test -n "$ffmpeg_version" && test -n "$placebo_version"
download "https://github.com/xbmc/xbmc/archive/$kodi_version.tar.gz" \
  "$test_root/kodi.tar.gz" "$(pin PKG_SHA256 packages/mediacenter/kodi/package.mk)"
download "https://ffmpeg.org/releases/ffmpeg-$ffmpeg_version.tar.xz" \
  "$test_root/ffmpeg.tar.xz" "$(pin PKG_SHA256 packages/multimedia/ffmpeg/package.mk)"
download "https://github.com/haasn/libplacebo/archive/$placebo_version.tar.gz" \
  "$test_root/libplacebo.tar.gz" "$(pin PKG_SHA256 "$placebo_recipe")"

python3 scripts/cb1-stage.py
mkdir "$test_root/kodi" "$test_root/ffmpeg" "$test_root/libplacebo"
tar -xf "$test_root/kodi.tar.gz" -C "$test_root/kodi" --strip-components=1
tar -xf "$test_root/ffmpeg.tar.xz" -C "$test_root/ffmpeg" --strip-components=1
tar -xf "$test_root/libplacebo.tar.gz" -C "$test_root/libplacebo" --strip-components=1
for patch_file in packages/mediacenter/kodi/patches/*.patch projects/Generic/patches/kodi/*.patch \
                  projects/Generic/patches/kodi/x86/*.patch; do
  patch --batch --forward --fuzz=0 -p1 -d "$test_root/kodi" < "$patch_file"
done
for patch_file in packages/multimedia/ffmpeg/patches/postproc/*.patch \
                  packages/multimedia/ffmpeg/patches/libreelec/*.patch \
                  projects/Generic/patches/ffmpeg/*.patch; do
  patch --batch --forward --fuzz=0 -p1 -d "$test_root/ffmpeg" < "$patch_file"
done
for patch_file in CB1/patches/libplacebo/*.patch; do
  patch --batch --forward --fuzz=0 -p1 -d "$test_root/libplacebo" < "$patch_file"
done
python3 CB1/tools/verify.py --ffmpeg-source "$test_root/ffmpeg" \
  --libplacebo-source "$test_root/libplacebo"
(
  cd "$test_root/ffmpeg"
  ./configure --prefix="$test_root/prefix" --disable-everything --disable-programs \
    --disable-doc --disable-network --disable-autodetect --disable-x86asm \
    --enable-gpl --enable-version3 --enable-shared --disable-static \
    --enable-filter=buffer,buffersink,hstack,settb \
    --enable-demuxer=mov,mpegts,matroska --enable-parser=hevc --enable-protocol=file \
    --enable-bsf=hevc_mp4toannexb
  make -j2
  make install
)
printf '%s\n' \
  "KODI_NATIVE_SOURCE_TREE=$test_root/kodi" \
  "CB1_DRM_STATE_SOURCE=$test_root/kodi" \
  "FFMPEG_TEST_PREFIX=$test_root/prefix" \
  "FFMPEG_MATCHED_SOURCE=$test_root/ffmpeg" \
  "FFMPEG_SOURCE_ARCHIVE=$test_root/ffmpeg.tar.xz" \
  "LD_LIBRARY_PATH=$test_root/prefix/lib" >> "${GITHUB_ENV:?}"
