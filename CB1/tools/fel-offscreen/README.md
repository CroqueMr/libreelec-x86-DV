# Offscreen 4K FEL benchmark

This benchmark pairs and decodes both HEVC layers through VA-API, runs the CB1
player-led renderer for a BT.2020 target, then packs 10- or 12-bit
4:2:2 into an EGL-imported GBM buffer. A coherent GPU buffer passes the linear
image to four x86 packing workers. The workers write the final carrier directly
into mapped DMA-BUF memory.

Build on x86-64 Linux with Python, GCC, Meson, Ninja, and development libraries
for DRM, GBM, VA-API, EGL and GLES. Supply the libplacebo tree with the current
CB1 patches already applied, the current CB1 Release build directory and its
matching FFmpeg prefix. The script builds a copy of the patched libplacebo source and links the matching CB1 archive.

```sh
python3 CB1/tools/fel-offscreen/build.py \
  --libplacebo-source "$placebo" --core-build "$core_build" \
  --ffmpeg-prefix "$ffmpeg" --output "$out"

EGL_PLATFORM=surfaceless MESA_SHADER_CACHE_DISABLE=true \
LD_LIBRARY_PATH="$out/placebo-build/src:$ffmpeg/lib" CB1_TARGET_FPS=27 \
  "$out/fel-offscreen" fel "$clip" 900 120 12
```

Set the last argument to 10 or 12. The CSV times the complete chain in blocks
of 300 frames, including queue drain. The deadline count checks whether each
carrier was ready on a 27-fps timeline with 100 ms of initial headroom. The
input timestamps still drive BL/EL pairing. The benchmark needs a 3840×2160
input, AVX2 and FMA, coherent persistent GLES buffer storage, and a linearly
mapped ABGR8888 GBM buffer with a tightly packed pitch. Peak allocation for
three linear images and three carriers is about 475 MiB, plus decoded surfaces.

Set CB1_RENDER_NODE to change the VA-API and GBM node from
/dev/dri/renderD128. On a multi-GPU host, select the same EGL device via the
driver environment. CB1_CPU_THREADS accepts 1–4 workers. CB1_PEAK_NITS defaults to 1000.
CB1_XRGB=1 writes flipped XRGB8888 carrier rows for direct scanout tests.

CB1_CPU_DUMP=1 reads the last carrier back through EGL into
pipeline-cpu.rgba. The compare-carrier executable takes the reference and
candidate RGBA carriers, the reference linear RGBA float image, width, height,
and useful bit depth. It checks the alpha and bit layout, then reports any
differences against a double-precision calculation at the affected pixels.
CB1_PROBE_CARRIER=1 adds a GPU read and completion fence for every carrier
before reuse. The producer benchmark ends at the ready buffer and uses no
Kodi presentation, KMS scanout, or HDMI link.
