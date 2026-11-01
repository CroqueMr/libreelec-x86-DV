"""Execute native HDMV/BD-J callbacks, crop/copy, and player group flattening."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class BlurayMenuSource(unittest.TestCase):
    def test_menu_identity_survives_callbacks_crop_and_player_flattening(self):
        include = os.environ.get('LIBBLURAY_TEST_INCLUDE')
        if not include:
            self.skipTest('Set LIBBLURAY_TEST_INCLUDE to matched libbluray include root')
        bluray = (TREE / 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        video = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        methods = {
            'void OverlayClose()': 'void CDVDInputStreamBluray::OverlayClose()',
            'void OverlayInit(SPlane& plane, int w, int h)': 'void CDVDInputStreamBluray::OverlayInit(',
            'void OverlayClear(SPlane& plane, int x, int y, int w, int h)': 'void CDVDInputStreamBluray::OverlayClear(',
            'void OverlayFlush(SPlane& updated, int64_t pts)': 'void CDVDInputStreamBluray::OverlayFlush(',
            'void OverlayCallback(const BD_OVERLAY* const ov)': 'void CDVDInputStreamBluray::OverlayCallback(',
            'void OverlayCallbackARGB(const BD_ARGB_OVERLAY* const ov)': 'void CDVDInputStreamBluray::OverlayCallbackARGB(',
            'bool IsInMenu()': 'bool CDVDInputStreamBluray::IsInMenu()',
        }
        program = r'''
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <list>
#include <mutex>
#include "utils/Geometry.h"
#include "cores/VideoPlayer/DVDCodecs/Overlay/DVDOverlayImage.h"
#include <libbluray/decoders/overlay.h>
#define PIXEL_ASHIFT 24
#define PIXEL_RSHIFT 16
#define PIXEL_GSHIFT 8
#define PIXEL_BSHIFT 0
#define LOGWARNING 1
#define BD_EVENT_MENU_OVERLAY 1
struct CLog { template<class... T> static void Log(T...) {} };
uint8_t clamp(double v) CLAMP
uint32_t build_rgba(const BD_PG_PALETTE_ENTRY& e) RGBA
struct Player {
  std::shared_ptr<CDVDOverlayGroup> group;
  void OnDiscNavResult(void* pointer, int) {
    group = *static_cast<std::shared_ptr<CDVDOverlayGroup>*>(pointer);
  }
};
struct Input {
  using SOverlay = std::shared_ptr<CDVDOverlayImage>;
  using SOverlays = std::list<SOverlay>;
  struct SPlane { int w{}, h{}; SOverlays o, committed; };
  std::array<SPlane, 2> m_planes;
  Player player;
  Player* m_player = &player;
  bool m_hasOverlay{};
  bool m_menu{};
  void* m_bd = this;
  bool m_navmode = true;
  METHODS
};
struct VideoPicture {};
struct IDVDStreamPlayer { enum {SYNC_INSYNC}; };
struct Container : std::mutex {
  VecOverlays items;
  void CleanUp(double) {}
  VecOverlays* GetOverlays() {return &items;}
};
struct Video {
  int m_syncState = IDVDStreamPlayer::SYNC_INSYNC;
  double m_iSubtitleDelay{};
  bool m_bRenderSubs = false;
  Container container;
  Container* m_pOverlayContainer = &container;
  struct RenderManager {
    VecOverlays items;
    void AddOverlay(std::shared_ptr<CDVDOverlay> overlay, double) {items.push_back(overlay);}
  } m_renderManager;
  void ProcessOverlays(const VideoPicture* pSource, double pts) FLATTEN
};
void check(Input& input) {
  input.OverlayFlush(input.m_planes[0], 0);
  assert(input.player.group && input.player.group->GetSource() == DVDOverlaySource::MENU);
  assert(!input.player.group->IsOverlayContainerFlushable());
  assert(input.player.group->m_overlays.size() == 1);
  Video player;
  player.container.items.push_back(input.player.group);
  player.ProcessOverlays(nullptr, 1);
  assert(player.m_renderManager.items.size() == 1 && "forced menus render with subtitles off");
  auto child = player.m_renderManager.items.front();
  assert(child->GetSource() == DVDOverlaySource::MENU && "flattened menu is not a subtitle");
  assert(child->Clone()->GetSource() == DVDOverlaySource::MENU);
  // Exercise actual partial wipe/crop and the native image copy constructor.
  input.OverlayClear(input.m_planes[0], 0, 0, 1, 1);
  assert(!input.m_planes[0].o.empty());
  for (const auto& cropped : input.m_planes[0].o)
    assert(cropped->GetSource() == DVDOverlaySource::MENU);
  input.OverlayClose();
  assert(input.player.group->m_overlays.empty());
  assert(input.player.group->GetSource() == DVDOverlaySource::MENU);
}
void check_visibility(Input& input) {
  input.OverlayFlush(input.m_planes[0], 0);
  assert(input.IsInMenu());
  input.OverlayClear(input.m_planes[0], 0, 0, 1920, 1080);
  // libbluray stages a wipe after presentation; only FLUSH commits it.
  assert(input.IsInMenu());
  input.OverlayFlush(input.m_planes[0], 90000);
  assert(input.player.group->m_overlays.empty());
  assert(!input.IsInMenu() && "empty committed overlays must release menu keys");
  input.m_menu = true;
  assert(input.IsInMenu() && "disc navigation remains authoritative");
  input.m_menu = false;
}
int main() {
  CDVDOverlayImage subtitle;
  assert(subtitle.GetSource() == DVDOverlaySource::SUBTITLE);
  Input hdmv;
  BD_OVERLAY pg{};
  pg.cmd = BD_OVERLAY_INIT; pg.w = 1920; pg.h = 1080;
  hdmv.OverlayCallback(&pg);
  BD_PG_RLE_ELEM run{4, 1};
  std::array<BD_PG_PALETTE_ENTRY, 256> palette{};
  palette[1] = {235, 128, 128, 255};
  pg.cmd = BD_OVERLAY_DRAW; pg.w = 2; pg.h = 2; pg.img = &run; pg.palette = palette.data();
  hdmv.OverlayCallback(&pg);
  check_visibility(hdmv);
  hdmv.OverlayCallback(&pg);
  check(hdmv);
  pg.cmd = BD_OVERLAY_DRAW;
  hdmv.OverlayCallback(&pg);
  pg.plane = 1;
  hdmv.OverlayCallback(&pg);
  hdmv.OverlayFlush(hdmv.m_planes[0], 90000);
  hdmv.OverlayFlush(hdmv.m_planes[1], 90000);
  assert(hdmv.player.group->m_overlays.size() == 2);
  pg.cmd = BD_OVERLAY_CLOSE; pg.pts = -1;
  hdmv.OverlayCallback(&pg);
  assert(hdmv.player.group->m_overlays.size() == 1 && "closing IG must preserve PG");
  assert(hdmv.player.group->iPTSStartTime == 0 && hdmv.IsInMenu());
  pg.plane = 2;
  hdmv.OverlayCallback(&pg);
  assert(hdmv.player.group->m_overlays.size() == 1 && "unsupported close is not global");
  pg.plane = 0;
  hdmv.OverlayCallback(&pg);
  assert(hdmv.player.group->m_overlays.empty() && !hdmv.IsInMenu());
  Input staged;
  pg.plane=0; pg.cmd=BD_OVERLAY_INIT; pg.w=1920; pg.h=1080;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_DRAW; pg.w=2; pg.h=2;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_FLUSH;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_WIPE;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_HIDE;
  staged.OverlayCallback(&pg);
  assert(staged.player.group->m_overlays.size()==1);
  pg.plane=1; pg.cmd=BD_OVERLAY_INIT;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_DRAW;
  staged.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_FLUSH;
  staged.OverlayCallback(&pg);
  assert(staged.player.group->m_overlays.size()==2 && "IG flush must not commit the staged PG wipe");
  pg.cmd=BD_OVERLAY_CLOSE;
  staged.OverlayCallback(&pg);
  assert(staged.player.group->m_overlays.size()==1 && "IG close must preserve displayed PG");
  pg.plane=0; pg.cmd=BD_OVERLAY_FLUSH;
  staged.OverlayCallback(&pg);
  assert(staged.player.group->m_overlays.empty() && !staged.IsInMenu());
  Input pending;
  pg.plane=0; pg.cmd=BD_OVERLAY_INIT;
  pending.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_DRAW;
  pending.OverlayCallback(&pg);
  pg.cmd=BD_OVERLAY_FLUSH;
  pending.OverlayCallback(&pg);
  pg.plane=1; pg.cmd=BD_OVERLAY_DRAW;
  pending.OverlayCallback(&pg);
  pg.plane=0; pg.cmd=BD_OVERLAY_CLOSE;
  pending.OverlayCallback(&pg);
  assert(pending.player.group->m_overlays.empty() && "PG close must not reveal pending IG");
  pg.plane=1; pg.cmd=BD_OVERLAY_FLUSH;
  pending.OverlayCallback(&pg);
  assert(pending.player.group->m_overlays.size()==1);
  Input bdj;
  BD_ARGB_OVERLAY argb{};
  argb.cmd = BD_ARGB_OVERLAY_INIT; argb.w = 1920; argb.h = 1080;
  bdj.OverlayCallbackARGB(&argb);
  std::array<uint32_t, 4> pixels{0xffffffff, 0xff123456, 0x80808080, 0};
  argb.cmd = BD_ARGB_OVERLAY_DRAW; argb.w = 2; argb.h = 2; argb.stride = 2; argb.argb = pixels.data();
  bdj.OverlayCallbackARGB(&argb);
  check_visibility(bdj);
  bdj.OverlayCallbackARGB(&argb);
  check(bdj);
  bdj.OverlayCallbackARGB(&argb);
  argb.plane = 1;
  bdj.OverlayCallbackARGB(&argb);
  argb.cmd = BD_ARGB_OVERLAY_FLUSH;
  bdj.OverlayCallbackARGB(&argb);
  argb.plane = 0; argb.cmd = BD_ARGB_OVERLAY_CLOSE; argb.pts = -1;
  bdj.OverlayCallbackARGB(&argb);
  assert(bdj.player.group->m_overlays.size() == 1 && "closing PG must preserve IG");
  assert(bdj.m_planes[1].o.size() == 1 && bdj.IsInMenu());
  bdj.OverlayCallbackARGB(nullptr);
  assert(bdj.player.group->m_overlays.empty() && !bdj.IsInMenu());
  assert(bdj.m_planes[0].committed.empty() && bdj.m_planes[1].committed.empty());
}
'''
        program = program.replace('CLAMP', body(bluray, 'static uint8_t  clamp('))
        program = program.replace('RGBA', body(bluray, 'static uint32_t build_rgba('))
        program = program.replace('METHODS', '\n'.join(
            declaration + body(bluray, signature) for declaration, signature in methods.items()))
        program = program.replace('FLATTEN', body(video, 'void CVideoPlayerVideo::ProcessOverlays('))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # DVDOverlayImage's platform header is not used by these methods.
            (root / 'PlatformDefs.h').write_text('')
            (root / 'probe.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    '-I' + str(root), '-I' + str(TREE / 'xbmc'), '-I' + include,
                                    str(root / 'probe.cpp'), '-o', str(root / 'probe')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
