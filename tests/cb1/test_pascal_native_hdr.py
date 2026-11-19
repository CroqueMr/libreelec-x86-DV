"""Keep the Pascal HDR10 fallback on the ordinary HDMI presentation path."""

import unittest

from shipped_kodi import shipped_code


class PascalNativeHDR(unittest.TestCase):
    def test_fallback_uses_the_selected_drm_gpu_and_an_hdr10_picture(self):
        source = shipped_code("xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp")
        self.assertIn("drmGetDevice2(drm.GetFileDescriptor()", source)
        self.assertIn("IsPascal(device->deviceinfo.pci->vendor_id", source)
        self.assertIn("picture->hdrType == StreamHdrType::HDR_TYPE_HDR10", source)
        self.assertIn("picture->hdrType == StreamHdrType::HDR_TYPE_HDR10PLUS", source)
        self.assertIn("m_dvSelection.route == DVBRIDGE::OutputRoute::Vanilla", source)

    def test_native_frame_is_rendered_and_submitted_from_the_rgb10_target(self):
        source = shipped_code("xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp")
        self.assertIn("BindNativePascalHDRFramebuffer()", source)
        self.assertIn("auto carrier = BlitNativePascalHDRFrame()", source)
        self.assertIn(
            "CWinSystemGbm::FlipPage(rendered, videoLayer, async, carrier)", source
        )
        gbm = shipped_code("xbmc/windowing/gbm/WinSystemGbm.cpp")
        self.assertIn("surface.AdoptTransactionalBuffer(carrier.get(), carrier)", gbm)
        self.assertIn("return atomic->LastPageAccepted()", gbm)

    def test_dynamic_metadata_is_staged_before_pascal_handoff(self):
        source = shipped_code("xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp")
        self.assertIn("if (carrier) StageNativeHDR10Plus();", source)
        self.assertIn("nativeHDR10PlusFallback = StageNativeHDR10Plus();", source)
        self.assertIn("source->Generation() == generation", source)


if __name__ == "__main__":
    unittest.main()
