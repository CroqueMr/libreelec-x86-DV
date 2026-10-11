# FEL hardware upscaling

VAAPI enlarges the half-resolution FEL enhancement layer before CB1 reconstructs the picture. The existing metadata processing, reconstruction and HDMI transport remain unchanged. This applies to FEL input in DV Native, DV Enhanced and DV-to-HDR10 modes. MEL and ordinary HDR10/SDR playback are unaffected.

The adapter uses two reusable Y416 surfaces. Exported DMA-BUF storage is imported as RGBA16 UNORM without a CPU pixel copy. The renderer retains each surface until its existing source-read fence completes. It does not queue additional prepared frames.

Hardware upscaling is selected automatically where supported. Unsupported output formats, failed imports or failed VPP operations use the complete shader FEL path. A temporarily occupied pool also uses that path for the current picture.

Hardware interpolation differs slightly from shader interpolation. This changes enhancement-layer sampling, not Dolby Vision metadata or artistic trims.

The adapter requires VAAPI VideoProc, Y416 output allocation and EGL DMA-BUF import. It probes these operations rather than matching CPU model names. No proprietary Dolby library is used.
