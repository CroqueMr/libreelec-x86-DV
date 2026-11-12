# SPDX-License-Identifier: MIT
"""Build the FEL offscreen benchmark against matching production sources."""
import argparse
from pathlib import Path
import shutil
import subprocess


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libplacebo-source", required=True, type=Path)
    parser.add_argument("--core-build", required=True, type=Path)
    parser.add_argument("--ffmpeg-prefix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    tool = Path(__file__).resolve().parent
    cb1 = tool.parents[1]
    out = args.output.resolve()
    placebo = out / "libplacebo"
    placebo_build = out / "placebo-build"
    ffmpeg = args.ffmpeg_prefix.resolve()
    archive = out / "libdvbridge_core.a"
    core_build = args.core_build.resolve() / "src"
    original_archive = core_build / "libdvbridge_core.a"
    if not original_archive.is_file():
        parser.error(f"Core archive missing: {original_archive}")

    out.mkdir(parents=True)
    shutil.copytree(args.libplacebo_source, placebo, ignore=shutil.ignore_patterns(".git"))
    if "PL_HAVE_CB1_LLDV_HOST" not in (placebo / "src/include/libplacebo/renderer.h").read_text():
        parser.error("libplacebo source must contain the CB1 player-led host patch")
    run("meson", "setup", placebo_build, placebo, "--buildtype=debugoptimized",
        "-Ddemos=false", "-Dtests=false", "-Dvulkan=disabled", "-Dopengl=enabled",
        "-Dlibdovi=disabled", "-Dglslang=disabled", "-Dshaderc=disabled", "-Dlcms=disabled")
    run("meson", "compile", "-C", placebo_build)

    include = ["-I", cb1 / "src", "-I", core_build, "-I", placebo / "src/include",
               "-I", placebo_build / "src/include", "-I", ffmpeg / "include"]
    drm = subprocess.check_output(["pkg-config", "--cflags", "libdrm"], text=True).split()
    shutil.copyfile(original_archive, archive)
    run("gcc", "-O2", "-UNDEBUG", "-pthread", *include, "-I", cb1 / "tests",
        tool / "benchmark.c", archive, "-L", placebo_build / "src",
        "-L", ffmpeg / "lib", "-lplacebo", "-lavformat", "-lavcodec", "-lavutil",
        "-lGLESv2", "-lEGL", "-lva", "-ldrm", "-lgbm", "-lm", "-ldl",
        "-o", out / "fel-offscreen")
    run("gcc", "-O2", tool / "compare_carrier.c", "-lm", "-o", out / "compare-carrier")


if __name__ == "__main__":
    main()
