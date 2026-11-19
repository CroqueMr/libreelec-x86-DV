# SPDX-License-Identifier: MIT
PKG_NAME="lightgbm"
PKG_VERSION="4.7.0"
PKG_SHA256="f8e20f682c9aabd000bcf4a7ed8aa6f473c1adfecccae34ec24e823d156f4af0"
PKG_LICENSE="MIT"
PKG_SITE="https://github.com/lightgbm-org/LightGBM"
PKG_URL="https://files.pythonhosted.org/packages/63/8e/4db5e29290d7e619c307fdb8dab0a0514090af2ce3ec483050e024ec6126/lightgbm-${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain"
PKG_LONGDESC="Native CPU inference for the CB1 HDR10 metadata estimator."
PKG_TOOLCHAIN="cmake"

PKG_CMAKE_OPTS_TARGET="-DBUILD_CLI=OFF
                       -DUSE_OPENMP=OFF
                       -DUSE_GPU=OFF
                       -DUSE_CUDA=OFF
                       -DUSE_MPI=OFF
                       -DINSTALL_HEADERS=ON"
