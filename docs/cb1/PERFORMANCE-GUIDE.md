# Image quality and performance

## Reference vs Master Reference

Both TV-led paths reconstruct applicable FEL and forward display-management metadata. Master Reference uses exact source-domain integer arithmetic and dedicated FEL filters for its admitted source formats. Reference uses a lighter reconstruction recipe. [Master Reference contract](../../CB1/docs/MASTER-REFERENCE.md) · [Reference algorithm](../../CB1/docs/ALGORITHMS.md#dolby-vision-reference)

On the Ryzen 5 7430U with **Beta5 Debug**, the circuit then named **Standard** reduced graphics-engine busy time by **34% on Avatar** and **50% on 1917**. Both matched measurement windows reported zero missed presentations. These figures describe the two measured excerpts at 23.976 fps on the historical build. The report includes unamplified crops, amplified difference maps, per-component errors and raw measurements. [Matched comparison](../reports/master-reference-vs-standard-2026-10-21.md)

## Video upscalers

Kodi keeps its existing scaler by default. The video scaler has independent settings for 1080p and above and below 1080p. Both offer the same filters across SDR, HDR and Dolby Vision. The selected video upscaler runs when the picture needs enlargement. Player Information shows it when active.

| Filter | What it does | Median GPU time, film / animation |
| --- | --- | --- |
| Kodi Default | Keeps the normal Kodi selection. Bilinear was effective on this test setup. | 0.83 / 0.85 ms |
| Lanczos | Uses a windowed sinc filter for sharper detail. | 7.22 / 7.23 ms |
| FSR 1 EASU | Enlarges the image with edge-adaptive spatial sampling. | 5.07 / 5.07 ms |
| FSR 1 EASU + RCAS | Adds contrast-adaptive sharpening after the EASU pass. | 6.80 / 6.85 ms |
| FSRCNNX x2 | Uses a convolutional shader for 2× enlargement. | 24.51 / 24.70 ms |
| Anime4K Fast | Uses a lightweight CNN upscaler aimed at animated edges and detail. | 28.91 / 30.38 ms |

The **Ryzen 5 7430U SDR scaling comparison** uses matching 1080p-to-4K crops from *Tears of Steel* and *Sintel*. These are GPU render timings for the scaling comparison. Decode, subtitles and display are outside the timings. The PDF includes P95 and the exact crop coordinates. Blender Foundation film stills are credited in the report under CC BY 3.0. [PDF with same-position crops and timings](../reports/upscaler-comparison-amd.pdf)

The **FEL upscaler** is a separate stage. It resamples the enhancement layer before reconstruction. Master Reference retains its dedicated FEL reconstruction filters when the final picture is enlarged with a video upscaler. [FEL visual comparison](FEL-UPSCALING.md)

## Hardware reference points

The Ryzen 5 7430U is the reference system for the AMD playback and upscaling measurements. Use the following integrated graphics as reference points for the tier with more headroom for conversions.

| Processor | Integrated graphics |
| --- | --- |
| AMD Ryzen 3 7330U | Radeon Vega 6, six graphics cores at up to 1.8 GHz |
| Intel Core i3-1315U | Intel UHD Graphics, 64 execution units |
| AMD Ryzen 5 7430U | Radeon Vega 7, seven graphics cores at up to 1.8 GHz |

[AMD Ryzen 3 7330U specifications](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-3-7330u.html) · [Intel Core i3-1315U specifications](https://www.intel.com/content/www/us/en/products/sku/232136/intel-core-i31315u-processor-10m-cache-up-to-4-50-ghz/specifications.html) · [AMD Ryzen 5 7430U specifications](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-5-7430u.html)

In PassMark G3D, the 7330U scored **1,693** against **2,270** for the 7430U, about **25% lower** in that dataset. Playback performance varies with the system, memory configuration, native HDMI path, source and selected circuit. [7330U graphics results](https://www.videocardbenchmark.net/gpu.php?gpu=Ryzen+3+7330U+with+Radeon+Graphics&id=4875) · [7430U graphics results](https://www.videocardbenchmark.net/gpu.php?gpu=Ryzen+5+7430U+with+Radeon+Graphics&id=5948)
