# Build

Use a Linux filesystem and the normal LibreELEC build dependencies. This
repository includes CB1 and the matching LightGBM model in `CB1/`.

CB1 is linked into Kodi as a static library. Its sources and FFmpeg/libplacebo
patches are staged into ignored native package paths, not maintained here twice.

```sh
python3 CB1/tools/verify.py
python3 scripts/cb1-stage.py --check
python3 scripts/cb1-stage.py
CB1_HDR10_AI=yes PROJECT=Generic ARCH=x86_64 OFFICIAL=no make image
```

The stager checks the exact source snapshot and refuses conflicting destination
files. It does not fetch, build, install or publish anything. Rebuild affected
packages with LibreELEC's native clean/build commands after changing sources.

Output: installation `.img.gz` and native-update `.tar` under `target/`.
The default build version is `R1.0.0-Beta1`, displayed as R1.0.0 Beta1 in the
release description. `CUSTOM_VERSION` can override the build identifier.
The AI model is included. No media or training dataset is included.

## Optional AI conversion

HDR10-to-Dolby Vision AI conversion is enabled by default. The source stager
copies CB1's included `models/l1l3/` bundle to
`packages/mediacenter/kodi/cb1-model/`. The native Kodi recipe installs its data
under `/usr/share/cb1/l1l3/`. LightGBM is compiled through its native package recipe.
Set `CB1_HDR10_AI=no` to build without AI conversion.

## Source checks

```sh
python3 -m unittest discover -s tests/cb1 -p 'test_*.py'
git diff --check
```
