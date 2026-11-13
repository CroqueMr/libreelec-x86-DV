"""Exercise Kodi's real render-area code with Dolby Vision L5 active areas."""
from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body

RENDERERS = TREE/'xbmc/cores/VideoPlayer/VideoRenderers'


class DVActiveAreaViewTests(unittest.TestCase):
    def test_active_area_mode_fits_each_picture_l5(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to the sanitizer-built FFmpeg prefix')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        base = (RENDERERS/'BaseRenderer.cpp').read_text()
        gles = (RENDERERS/'LinuxRendererGLES.cpp').read_text()
        header = (TREE/'xbmc/cores/VideoSettings.h').read_text()
        modes = re.search(r'enum ViewMode\s*\{.*?\};', header, re.S).group()
        program = r'''
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
extern "C" {
#include <libavutil/dovi_meta.h>
}
#include "utils/Geometry.h"
#include "rendering/RenderSystemTypes.h"
#include "cores/VideoPlayer/VideoRenderers/RenderFlags.h"
@ENUM@
struct Resolution {
 int iWidth=3840,iHeight=2160,iScreenWidth=3840,iScreenHeight=2160;
 float fPixelRatio=1;struct{int left=0,top=0,right=3840,bottom=2160;}Overscan;
} resolution;
using RESOLUTION_INFO=Resolution;
struct Settings {
 static constexpr int SETTING_VIDEOPLAYER_STRETCH43=0,SETTING_VIDEOPLAYER_ERRORINASPECT=1;
 int GetInt(int)const{return 0;}
};
using CSettings=Settings;
struct Window {struct Context{
 const Resolution& GetResInfo(){return resolution;}
 CRect GetViewWindow(){return CRect(0,0,resolution.iWidth,resolution.iHeight);}
 RenderStereoView GetStereoView(){return RenderStereoView::OFF;}
 bool IsFullScreenVideo(){return true;}bool IsCalibrating(){return false;}
}context;Context& GetGfxContext(){return context;}};
struct CServiceBroker {
 static Window* GetWinSystem(){static Window w;return &w;}
 struct Component{Settings s;Settings* GetSettings(){return &s;}};
 static Component* GetSettingsComponent(){static Component c;return &c;}
};
namespace MathUtils {int round_int(double v){return std::lround(v);}}
enum {LOGDEBUG};
struct CLog {template<class... T> static void Log(T&&...){}};
struct CDisplaySettings {
 float zoom=1,ratio=1,shift=0;bool stretch=false;
 static CDisplaySettings& GetInstance(){static CDisplaySettings s;return s;}
 void SetZoomAmount(float v){zoom=v;}float GetZoomAmount(){return zoom;}
 void SetPixelRatio(float v){ratio=v;}float GetPixelRatio(){return ratio;}
 void SetVerticalShift(float v){shift=v;}float GetVerticalShift(){return shift;}
 void SetNonLinearStretched(bool v){stretch=v;}bool IsNonLinearStretched(){return stretch;}
};
// One owned L5-capable metadata block, laid out as libavutil describes it.
struct Metadata {
 AVDOVIMetadata header{};AVDOVIDmData ext[2]{};
 explicit Metadata(int blocks){header.ext_block_offset=offsetof(Metadata,ext);
  header.ext_block_size=sizeof(AVDOVIDmData);header.num_ext_blocks=blocks;}
};
struct Buffer {const uint8_t* metadata=nullptr;
 struct {const Buffer* owner;const uint8_t* Data()const{return owner->metadata;}}doviMetadata{this};};
struct CLinuxRendererGLES {
 struct {int m_ViewMode=0;float m_CustomZoomAmount=1,m_CustomPixelRatio=1,m_CustomVerticalShift=0;
 bool m_CustomNonLinStretch=false;}m_videoSettings;
 unsigned m_sourceWidth=3840,m_sourceHeight=2160,m_renderOrientation=0,m_iFlags=0;
 bool m_alwaysClip=false;
 CRect m_sourceRect,m_destRect,m_viewRect,m_activeArea;
 Buffer m_buffers[1];
 float GetAspectRatio()const{return float(m_sourceWidth)/m_sourceHeight;}
 float GetPerEyeAspectRatio()const{return GetAspectRatio();}
 void ReorderDrawPoints(){}
 void SetActiveArea(const CRect& area){m_activeArea=area;}
 void SetViewMode(int viewMode) @SET@
 void CalcDestRect(float offsetX,float offsetY,float width,float height,float inputFrameRatio,
   float zoomAmount,float verticalShift,CRect& destRect,bool useVideoSettings=true) @RECT@
 void CalcNormalRenderRect(float offsetX,float offsetY,float width,float height,
   float inputFrameRatio,float zoomAmount,float verticalShift) @NORMAL@
 void ManageRenderArea() @MANAGE@
 void FitActiveArea(float& aspectRatio) @FIT@
 void UpdateActiveArea(int index) @UPDATE@
 // RenderUpdate order: this picture's L5, then its render area.
 void Render(const Metadata* metadata){
  m_buffers[0].metadata=reinterpret_cast<const uint8_t*>(metadata);
  UpdateActiveArea(0);ManageRenderArea();
 }
};
static Metadata l5(int left,int right,int top,int bottom){
 Metadata m(2);m.ext[0].level=1;m.ext[1].level=5;
 m.ext[1].l5.left_offset=left;m.ext[1].l5.right_offset=right;
 m.ext[1].l5.top_offset=top;m.ext[1].l5.bottom_offset=bottom;return m;
}
static void expect(const CLinuxRendererGLES& r,CRect source,CRect dest){
 std::printf("source %.0f,%.0f-%.0f,%.0f dest %.0f,%.0f-%.0f,%.0f\n",r.m_sourceRect.x1,r.m_sourceRect.y1,
  r.m_sourceRect.x2,r.m_sourceRect.y2,r.m_destRect.x1,r.m_destRect.y1,r.m_destRect.x2,r.m_destRect.y2);
 std::fflush(stdout);assert(r.m_sourceRect==source && r.m_destRect==dest);
}
int main(){
 CLinuxRendererGLES r;r.SetViewMode(ViewModeActiveArea);
 const CRect frame(0,0,3840,2160);
 // Project Hail Mary 1.43 IMAX: 2.39 scenes are windowboxed inside the IMAX width.
 const Metadata scope=l5(376,376,433,433),imax=l5(376,376,0,0),none(0);
 r.Render(&scope);expect(r,CRect(376,433,3464,1727),CRect(0,275,3840,1884));
 // A picture that already fits its area keeps the whole uncropped frame.
 r.Render(&imax);expect(r,frame,frame);
 r.Render(&scope);expect(r,CRect(376,433,3464,1727),CRect(0,275,3840,1884));
 r.Render(&none);expect(r,frame,frame);
 r.Render(nullptr);expect(r,frame,frame);
 const Metadata invalid=l5(1920,1920,0,0);
 r.Render(&invalid);expect(r,frame,frame);
 // A 1080p view scales the same choice.
 resolution.iWidth=1920;resolution.iHeight=1080;
 r.Render(&scope);expect(r,CRect(376,433,3464,1727),CRect(0,138,1920,943));
 resolution.iWidth=3840;resolution.iHeight=2160;
 // Other modes keep encoded bars.
 r.SetViewMode(ViewModeNormal);r.Render(&scope);expect(r,frame,frame);
 r.SetViewMode(ViewModeAuto);r.Render(&scope);expect(r,frame,frame);
 // Packed stereo is out of scope.
 r.SetViewMode(ViewModeActiveArea);r.m_iFlags=CONF_FLAGS_STEREO_MODE_SBS;
 r.Render(&scope);expect(r,frame,frame);
}
'''
        for key, text, signature in [
                ('@SET@', base, 'void CBaseRenderer::SetViewMode('),
                ('@RECT@', base, 'void CBaseRenderer::CalcDestRect('),
                ('@NORMAL@', base, 'void CBaseRenderer::CalcNormalRenderRect('),
                ('@MANAGE@', base, 'void CBaseRenderer::ManageRenderArea('),
                ('@FIT@', base, 'void CBaseRenderer::FitActiveArea('),
                ('@UPDATE@', gles, 'void CLinuxRendererGLES::UpdateActiveArea(')]:
            program = program.replace(key, body(text, signature))
        program = program.replace('@ENUM@', modes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I'+str(TREE/'xbmc'), '-I'+str(prefix/'include'),
                                    str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-3000:])
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout+ran.stderr)

    def test_active_area_is_a_selectable_mode_and_rpc_value(self):
        schema = json.loads((TREE/'xbmc/interfaces/json-rpc/schema/types.json').read_text())
        self.assertIn('activearea', schema['Player.ViewMode']['enum'])
        self.assertIn('{"activearea", ViewModeActiveArea}',
                      (TREE/'xbmc/interfaces/json-rpc/PlayerOperations.cpp').read_text())
        strings = (TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        self.assertIn('msgctxt "#41225"\nmsgid "Dolby Vision active area"\n', strings)
        menu = (TREE/'xbmc/video/ViewModeSettings.cpp').read_text()
        part = menu[menu.index('struct ViewModeProperties'):menu.index('void CViewModeSettings::ViewModesFiller')]
        header = (TREE/'xbmc/cores/VideoSettings.h').read_text()
        enum = re.search(r'enum ViewMode\s*\{.*?\};', header, re.S).group()
        program = '#include <cassert>\n#include <cstddef>\n'+enum+r'''
struct CViewModeSettings{static int GetNextQuickCycleViewMode(int);static int GetViewModeStringIndex(int);};
'''+part+r'''
int main(){assert(CViewModeSettings::GetViewModeStringIndex(ViewModeActiveArea)==41225);
 bool listed=false;for(const auto& mode:viewModes)if(mode.viewMode==ViewModeActiveArea&&!mode.hideFromList)listed=true;
 assert(listed);assert(CViewModeSettings::GetNextQuickCycleViewMode(ViewModeAuto)==ViewModeActiveArea);}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/'test.cpp').write_text(program)
            subprocess.run(['c++', '-std=c++20', str(root/'test.cpp'), '-o', str(root/'test')],
                           check=True, capture_output=True)
            subprocess.run([str(root/'test')], check=True, capture_output=True)


if __name__ == '__main__': unittest.main()
