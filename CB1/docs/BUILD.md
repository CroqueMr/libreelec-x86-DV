# Build

Use Linux and CMake 3.22 or later. Apply the patches in `patches/` to the exact
FFmpeg/libplacebo sources recorded in `config/dependencies.json`.

Required dependencies: FFmpeg, libplacebo, GLESv2, EGL and libdrm. Headers and
libraries must come from the same modified build.

```sh
python3 tools/verify.py
cmake -S . -B build -DCMAKE_PREFIX_PATH="$PREFIX"
cmake --build build -j2
```

Output: the `dvbridge_core` static library. The player links it and supplies its
graphics context and video resources.

## Tests

Tests require the matching dependency sources and retained reference fixtures:

```sh
cmake -S . -B build-tests -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DCB1_BUILD_TESTS=ON -DCB1_ENABLE_SANITIZERS=ON \
  -DCB1_FFMPEG_SOURCE="$FFMPEG" -DCB1_FFMPEG_STOCK_SOURCE="$STOCK_FFMPEG" \
  -DCB1_CUMULATIVE_SOURCE="$KODI" -DCB1_REFERENCE="$REFERENCE" \
  -DCB1_SOURCE_COMMIT="$CB1_COMMIT"
cmake --build build-tests -j2
ctest --test-dir build-tests --output-on-failure
```

These tests do not replace physical GPU/HDMI qualification. Retain and report
failing numerical controls.

## Optional AI conversion

`CB1_ENABLE_HDR10_AI=ON` uses the included `models/l1l3/` bundle and its native
contract. Install the pinned LightGBM C API and library recorded in
`config/hdr10-ai-dependencies.json`.

```sh
cmake -S . -B build-ai -DCMAKE_PREFIX_PATH="$PREFIX" -DCB1_ENABLE_HDR10_AI=ON
cmake --build build-ai -j2
```

The player loads `models/l1l3/data/` at runtime. LibreELEC installs it under
`/usr/share/cb1/l1l3/`. No Python runtime is used during playback.
Training and evaluation datasets are excluded.
