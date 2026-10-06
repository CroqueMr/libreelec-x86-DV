# Hardware support

Performance may vary by hardware. Report incompatibility or playback problems
in a GitHub issue with:

- Exact CPU and GPU model.
- Display model.
- Connection chain, including any receiver or adapter.
- Build version and `kodi.log`.

## Intel

| CPU generation / series with integrated graphics | Driver support |
| --- | --- |
| Core 8th gen and newer | Dolby Vision output |
| Core Ultra Series 1 / 2, including 200V | Dolby Vision output |
| N-series, including N100 / N150 | Dolby Vision output |

Newly enabled Intel families require hardware testing.

## AMD

Experimental amdgpu support:

| Ryzen generation / APU series | Display family |
| --- | --- |
| Ryzen 2000G / 3000G and corresponding mobile APUs | DCN 1 |
| Ryzen 4000 / 5000 APUs and 7030U, including 5800H / 7430U | DCN 2 |
| Ryzen 6000 and 7035 | DCN 3 |
| Ryzen 7040 / 8040 and 8000G | DCN 3 |
| Ryzen AI 300 | DCN 3 |

These AMD families are experimental and require hardware qualification.

## Other hardware

DV processing can output HDR10 when GPU processing is available. Custom Dolby
Vision HDMI output is unavailable; native Kodi playback remains available.

Processor-family references: [Intel Coffee Lake](https://www.intel.com/content/www/us/en/ark/products/codename/97787/products-formerly-coffee-lake.html),
[Intel N-series](https://www.intel.com/content/www/us/en/ark/products/series/231819/intel-processor-n-series.html)
and [AMD Ryzen processor guide](https://www.amd.com/content/dam/amd/en/documents/partner-hub/ryzen/ryzen-consumer-master-quick-reference-competitive.pdf).

## Known issues

- Some frame drops with Profile 7 FEL on a small number of files on N100/N150.
