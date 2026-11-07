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
        if 'CDVDInputStreamBluray::PlaneShows(' in bluray:
            methods['static bool PlaneShows(const SPlane& plane)'] = 'bool CDVDInputStreamBluray::PlaneShows('
        program = r'''
#include <array>
#include <atomic>
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
#define LOGDEBUG 2
#define BD_EVENT_MENU_OVERLAY 1
#define BD_EVENT_MENU 2
struct CLog { template<class... T> static void Log(T...) {} };
struct Title { bool bdj; };
struct DiscInfo { const Title* top_menu{}; };
using BLURAY_DISC_INFO = DiscInfo;
static DiscInfo disc_info;
static const DiscInfo* bd_get_disc_info(void*) {return &disc_info;}
uint8_t clamp(double v) CLAMP
uint32_t build_rgba(const BD_PG_PALETTE_ENTRY& e) RGBA
struct Player {
  std::shared_ptr<CDVDOverlayGroup> group;
  unsigned menu_event = 99;
  void OnDiscNavResult(void* pointer, int event) {
    if(event==BD_EVENT_MENU){menu_event=*static_cast<unsigned*>(pointer);return;}
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
  std::atomic_bool m_menuShows{};
  std::atomic_bool m_menu{};
  bool m_isInMainMenu{};
  using Title = ::Title;
  const Title* m_title{};
  struct {unsigned param;} m_event;
  void* m_bd = this;
  bool m_navmode = true;
  METHODS
  void MenuEvent(unsigned value) {m_event.param=value;switch(0){case 0:MENUEVENT}}
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
  assert(!input.player.group->m_overlays.empty() && !input.IsInMenu() && "PG subtitles are not a navigation menu");
  input.OverlayClear(input.m_planes[0], 0, 0, 1920, 1080);
  // libbluray stages a wipe after presentation; only FLUSH commits it.
  assert(!input.IsInMenu());
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
  assert(hdmv.player.group->iPTSStartTime == 0 && !hdmv.IsInMenu());
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
  assert(pending.player.group->m_overlays.size()==1 && pending.IsInMenu());
  pending.OverlayClear(pending.m_planes[1],0,0,1920,1080);
  assert(pending.IsInMenu() && "a staged IG wipe must retain the displayed menu keys");
  pending.OverlayFlush(pending.m_planes[1],90000);
  assert(!pending.IsInMenu());
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
  Input dirty;
  argb.plane=1;argb.cmd=BD_ARGB_OVERLAY_INIT;argb.w=3;argb.h=2;
  dirty.OverlayCallbackARGB(&argb);
  // libbluray points at the top-left dirty pixel, not the full framebuffer.
  std::array<uint32_t,6> framebuffer{0,0x00123456,0xffffffff,0,0,0x01123456};
  argb.cmd=BD_ARGB_OVERLAY_DRAW;argb.x=1;argb.y=0;argb.w=2;
  argb.stride=3;argb.argb=framebuffer.data()+1;
  dirty.OverlayCallbackARGB(&argb);
  const std::array<uint32_t,4> expected{0x00123456,0xffffffff,0,0x01123456};
  auto image=dirty.m_planes[1].o.front();
  assert(image->linesize==8 && image->pixels.size()==16);
  assert(!memcmp(image->pixels.data(),expected.data(),16));
  Input transparent;
  argb.x=argb.y=0;
  argb.plane=1;argb.cmd=BD_ARGB_OVERLAY_INIT;argb.w=2;argb.h=2;
  transparent.OverlayCallbackARGB(&argb);
  // Padding is opaque, visible RGB is nonzero but its alpha is zero.
  std::array<uint32_t,6> padded{0x00123456,0,0xffffffff,0,0,0xffffffff};
  argb.cmd=BD_ARGB_OVERLAY_DRAW;argb.stride=3;argb.argb=padded.data();
  transparent.OverlayCallbackARGB(&argb);
  argb.cmd=BD_ARGB_OVERLAY_FLUSH;
  transparent.OverlayCallbackARGB(&argb);
  assert(!transparent.player.group->m_overlays.empty() && !transparent.IsInMenu() && "transparent IG and stride padding must release player keys");
  padded[4]=0x01123456;argb.cmd=BD_ARGB_OVERLAY_DRAW;
  transparent.OverlayCallbackARGB(&argb);
  assert(!transparent.IsInMenu() && "an uncommitted DRAW is not yet the displayed menu");
  argb.cmd=BD_ARGB_OVERLAY_FLUSH;transparent.OverlayCallbackARGB(&argb);
  assert(transparent.IsInMenu() && "even one nonzero alpha pixel is a visible menu");
  transparent.OverlayClear(transparent.m_planes[1],0,0,1,1);
  transparent.OverlayFlush(transparent.m_planes[1],90000);
  assert(transparent.IsInMenu() && "partial wipe must preserve another visible pixel");
  transparent.OverlayClear(transparent.m_planes[1],1,1,1,1);
  assert(transparent.IsInMenu());
  transparent.OverlayFlush(transparent.m_planes[1],180000);
  assert(!transparent.IsInMenu());
  transparent.m_menu=true;assert(transparent.IsInMenu());
  transparent.m_navmode=false;assert(!transparent.IsInMenu());
  transparent.m_navmode=true;transparent.m_bd=nullptr;assert(!transparent.IsInMenu());
  Input java;
  Input::Title java_title{true};java.m_title=&java_title;
  argb.plane=1;argb.x=argb.y=0;argb.w=argb.h=2;argb.stride=2;
  argb.cmd=BD_ARGB_OVERLAY_INIT;java.OverlayCallbackARGB(&argb);
  java.MenuEvent(1); // Native BD-J plane INIT queues MENU=1 even if transparent.
  std::array<uint32_t,4> empty{};argb.argb=empty.data();
  argb.cmd=BD_ARGB_OVERLAY_DRAW;java.OverlayCallbackARGB(&argb);
  argb.cmd=BD_ARGB_OVERLAY_FLUSH;java.OverlayCallbackARGB(&argb);
  assert(!java.IsInMenu() && "synthetic BD-J MENU=1 must not pin invisible menu keys");
  empty[3]=0x01000000;argb.cmd=BD_ARGB_OVERLAY_DRAW;java.OverlayCallbackARGB(&argb);
  argb.cmd=BD_ARGB_OVERLAY_FLUSH;java.OverlayCallbackARGB(&argb);
  assert(java.IsInMenu());
  java.OverlayClose();disc_info.top_menu=&java_title;java.m_isInMainMenu=true;java.MenuEvent(1);
  assert(java.IsInMenu() && "TOP_MENU remains authoritative even for BD-J");
  java.MenuEvent(0);assert(!java.IsInMenu()&&!java.m_isInMainMenu&&java.player.menu_event==0);
  java.MenuEvent(1);assert(java.IsInMenu() && java.m_isInMainMenu && "same TOP_MENU title must reopen after close without another TITLE event");
  java.MenuEvent(0);disc_info.top_menu=nullptr;java.MenuEvent(1);
  assert(!java.IsInMenu() && "ordinary BD-J plane init remains synthetic");
  Input::Title hdmv_title{false};java.m_title=&hdmv_title;java.MenuEvent(1);
  assert(java.IsInMenu() && "genuine HDMV MENU remains authoritative");
  java.MenuEvent(0);java.m_title=nullptr;java.MenuEvent(1);
  assert(java.IsInMenu() && "unknown title retains explicit navigation events");
}
'''
        program = program.replace('CLAMP', body(bluray, 'static uint8_t  clamp('))
        program = program.replace('RGBA', body(bluray, 'static uint32_t build_rgba('))
        program = program.replace('METHODS', '\n'.join(
            declaration + body(bluray, signature) for declaration, signature in methods.items()))
        program = program.replace('FLATTEN', body(video, 'void CVideoPlayerVideo::ProcessOverlays('))
        program = program.replace('MENUEVENT', bluray.split('case BD_EVENT_MENU:',1)[1].split('case BD_EVENT_IDLE:',1)[0])
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
