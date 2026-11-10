# DVD cadence corpus

Synthetic DVD-style MPEG-2 program streams with known cadences, and a harness that
measures cadence reconstruction methods against the progressive frames each sample
was made from. Requires `ffmpeg` and `ffprobe` on the host.

```sh
python3 tools/dvd-cadence/corpus.py /tmp/dvd-cadence [--containers]
python3 tools/dvd-cadence/measure.py /tmp/dvd-cadence --json /tmp/dvd-cadence/results.json
```

| Sample | Content | Coding |
| --- | --- | --- |
| `ntsc_soft32` | 23.976p film | progressive frames, 3:2 `repeat_first_field` flags, stream rate 29.97, 3:2 timestamps |
| `ntsc_hard32` | 23.976p film | 3:2 pulldown in the fields, 29.97i |
| `ntsc_video` | 59.94p video | every field a different instant, 29.97i |
| `ntsc_mixed` | hard-telecined film, then video | 29.97i, no single reference (cadence detection only) |
| `pal_22` | 25p film | 2:2, flagged interlaced, 25i |
| `pal_22_progressive` | 25p film | flagged progressive |
| `pal_video` | 50p video | every field a different instant, 25i |

With `--containers` (requires `mkvpropedit`, `dvdauthor` and `xorriso`), the
soft-telecine sample is also written in other containers:

| File | Container |
| --- | --- |
| `ntsc_soft32.mkv` | Matroska remux with the 3:2 timestamps; states 23.976, their average rate |
| `ntsc_soft32_dvd/VIDEO_TS` | DVD-Video folder, title 1 |
| `ntsc_soft32.iso` | ISO image of that folder |

The pattern is rendered at twice the size and filtered down. Unfiltered one-pixel edges
look like combing to field detectors.

## Methods

| Method | Graph | Kodi equivalent |
| --- | --- | --- |
| `weave` | none | coded frames unchanged |
| `bwdif` | `bwdif=mode=send_field` | FFmpeg software deinterlace; VAAPI methods are similar field-rate deinterlacers |
| `fieldmatch` | `fieldmatch,bwdif=deint=interlaced` | rebuild frames from matching fields, interpolate orphans |
| `ivtc` | `fieldmatch,bwdif=deint=interlaced,decimate` | inverse telecine |

`fps` is the output frames per second of the sample. PSNR (dB) compares with the
progressive source. An output with the source frame count is compared frame by frame;
any other output is resampled to the source rate by timestamp first.

## Baseline (FFmpeg 8.1.3 host, 8 s samples)

| Sample | weave | bwdif | fieldmatch | ivtc |
| --- | --- | --- | --- | --- |
| `ntsc_soft32` | 24.0 fps, 50.94 | 48.0 fps, 38.56 | 24.0 fps, 50.94 | 19.25 fps, 22.54 |
| `ntsc_hard32` | 30.0 fps, 32.64 | 60.0 fps, 39.31 | 30.0 fps, 50.85 | **24.0 fps, 50.85** |
| `ntsc_video` | 30.0 fps, 30.09 | **60.0 fps, 37.40** | 30.0 fps, 29.86 | 24.0 fps, 27.04 |
| `pal_22` | 25.0 fps, 51.40 | 50.0 fps, 39.21 | **25.0 fps, 51.40** | 20.0 fps, 28.94 |
| `pal_22_progressive` | **25.0 fps, 51.30** | 50.0 fps, 39.22 | 25.0 fps, 51.30 | 20.0 fps, 28.94 |
| `pal_video` | 25.0 fps, 29.07 | **50.0 fps, 37.67** | 25.0 fps, 29.02 | 20.0 fps, 26.90 |

Findings:

- Hard telecine: field-rate deinterlacing loses about 11.5 dB against inverse telecine
  and shows the film at 59.94 with 3:2 judder. Inverse telecine restores the 192 film
  frames exactly (MPEG-2 coding loss only).
- PAL 2:2 flagged interlaced: deinterlacing loses about 12 dB; field matching
  restores the frames.
- True video: field-rate deinterlacing is best; inverse telecine and field matching
  are wrong. One fixed method cannot serve every disc, so the method must follow the
  detected cadence.
- Soft telecine: the decoder already outputs the 192 film frames (`weave`). Only the
  presentation timing is wrong: the stream states 29.97, so Kodi keeps that rate and
  the 3:2 field repeats.
