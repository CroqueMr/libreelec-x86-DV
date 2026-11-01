"""Exercise Kodi's real native view geometry, mode menu and RPC registration."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AutoViewModeTests(unittest.TestCase):
    def test_near_size_is_centred_but_hd_and_manual_zoom_still_scale(self):
        renderer = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/BaseRenderer.cpp').read_text()
        header = (TREE/'xbmc/cores/VideoSettings.h').read_text()
        modes = re.search(r'enum ViewMode\s*\{.*?\};', header, re.S).group()
        program = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
@ENUM@
struct CRect {
 float x1=0,y1=0,x2=0,y2=0;
 float Width()const{return x2-x1;}float Height()const{return y2-y1;}
 void SetRect(float a,float b,float c,float d){x1=a;y1=b;x2=c;y2=d;}
};
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
struct Window {struct Context{const Resolution& GetResInfo(){return resolution;}}context;
 Context& GetGfxContext(){return context;}};
struct CServiceBroker {
 static Window* GetWinSystem(){static Window w;return &w;}
 struct Component{Settings s;Settings* GetSettings(){return &s;}};
 static Component* GetSettingsComponent(){static Component c;return &c;}
};
namespace MathUtils {int round_int(double v){return std::lround(v);}}
struct CDisplaySettings {
 float zoom=1,ratio=1,shift=0;bool stretch=false;
 static CDisplaySettings& GetInstance(){static CDisplaySettings s;return s;}
 void SetZoomAmount(float v){zoom=v;}float GetZoomAmount(){return zoom;}
 void SetPixelRatio(float v){ratio=v;}float GetPixelRatio(){return ratio;}
 void SetVerticalShift(float v){shift=v;}float GetVerticalShift(){return shift;}
 void SetNonLinearStretched(bool v){stretch=v;}bool IsNonLinearStretched(){return stretch;}
};
struct CBaseRenderer {
 struct {int m_ViewMode=0;float m_CustomZoomAmount=1,m_CustomPixelRatio=1,m_CustomVerticalShift=0;
 bool m_CustomNonLinStretch=false;}m_videoSettings;
 int m_sourceWidth=3832,m_sourceHeight=1600,m_renderOrientation=0;
 CRect m_sourceRect;
 float GetAspectRatio(){return float(m_sourceWidth)/m_sourceHeight;}
 void SetViewMode(int viewMode) @SET@
 void CalcDestRect(float offsetX,float offsetY,float width,float height,float inputFrameRatio,
   float zoomAmount,float verticalShift,CRect& destRect,bool useVideoSettings=true) @RECT@
 CRect draw(){
  auto& settings=CDisplaySettings::GetInstance();CRect rect;
  CalcDestRect(0,0,resolution.iScreenWidth,resolution.iScreenHeight,
    GetAspectRatio()*settings.GetPixelRatio(),settings.GetZoomAmount(),settings.GetVerticalShift(),rect);
  return rect;
 }
 CRect output(int mode){SetViewMode(mode);return draw();}
};
int main(){
 CBaseRenderer r;
 struct Sample{int width,height,outWidth,outHeight,wantWidth,wantHeight;};
 const Sample samples[]{
  {3832,1600,3840,2160,3832,1600},{3808,1600,3840,2160,3808,1600},
  {3802,1600,3840,2160,3802,1600},{3801,1600,3840,2160,3840,1616},
  {3800,1600,3840,2160,3840,1617},{3840,1600,3840,2160,3840,1600},
  {1920,1080,3840,2160,3840,2160},{1912,1080,3840,2160,3824,2160},
  {2560,1440,3840,2160,3840,2160},{7680,4320,3840,2160,3840,2160},
  {1912,800,1920,1080,1912,800},{1920,1080,1920,1080,1920,1080},
  {3832,1600,1920,1080,1920,802}
 };
 for(const auto& s:samples){
  r.m_sourceWidth=s.width;r.m_sourceHeight=s.height;
  resolution.iWidth=resolution.iScreenWidth=resolution.Overscan.right=s.outWidth;
  resolution.iHeight=resolution.iScreenHeight=resolution.Overscan.bottom=s.outHeight;
  const auto rect=r.output(10);
  std::printf("%dx%d -> %dx%d: %.0fx%.0f\n",s.width,s.height,s.outWidth,s.outHeight,rect.Width(),rect.Height());
  std::fflush(stdout);
  assert(rect.Width()==s.wantWidth && rect.Height()==s.wantHeight);
  assert(rect.x1==std::lround((s.outWidth-s.wantWidth)/2.0));
  assert(rect.y1==std::lround((s.outHeight-s.wantHeight)/2.0));
 }
 r.m_sourceWidth=3832;r.m_sourceHeight=1600;
 resolution.iWidth=resolution.iScreenWidth=resolution.Overscan.right=3840;
 resolution.iHeight=resolution.iScreenHeight=resolution.Overscan.bottom=2160;
 assert(r.output(ViewModeNormal).Width()==3840);
 assert(r.output(ViewModeOriginal).Width()==3832);
 r.output(10);r.m_videoSettings.m_CustomZoomAmount=1.1f;
 assert(r.output(ViewModeCustom).Width()==4224);
 assert(r.output(10).Width()==3832);
 // Native display changes do not necessarily call SetViewMode again.
 resolution.iWidth=resolution.iScreenWidth=resolution.Overscan.right=1920;
 resolution.iHeight=resolution.iScreenHeight=resolution.Overscan.bottom=1080;
 assert(r.draw().Width()==1920 && r.draw().Height()==802);
 r.output(10);
 resolution.iWidth=resolution.iScreenWidth=resolution.Overscan.right=3840;
 resolution.iHeight=resolution.iScreenHeight=resolution.Overscan.bottom=2160;
 assert(r.draw().Width()==3832 && r.draw().Height()==1600);
 r.m_renderOrientation=90;
 assert(r.output(10).Width()==902 && r.draw().Height()==2160);
 r.m_renderOrientation=0;
 // Logical GUI dimensions must not be mistaken for physical HDMI dimensions.
 resolution.iWidth=1920;resolution.iHeight=1080;r.output(10);
 CRect logical;
 r.CalcDestRect(0,0,1920,1080,r.GetAspectRatio(),1,0,logical);
 assert(logical.Width()==1916 && logical.Height()==800);
 // The hardware-plane caller already supplies physical dimensions.
 CRect physical;
 r.CalcDestRect(0,0,3840,2160,r.GetAspectRatio(),1,0,physical,false);
 assert(physical.Width()==3832 && physical.Height()==1600);
}
'''.replace('@ENUM@', modes).replace('@SET@', body(renderer, 'void CBaseRenderer::SetViewMode(')).replace(
            '@RECT@', body(renderer, 'void CBaseRenderer::CalcDestRect('))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

    def test_auto_is_a_native_selectable_mode_and_rpc_value(self):
        schema=json.loads((TREE/'xbmc/interfaces/json-rpc/schema/types.json').read_text())
        self.assertIn('auto',schema['Player.ViewMode']['enum'])
        menu=(TREE/'xbmc/video/ViewModeSettings.cpp').read_text()
        # Compile the real native menu functions, not a second mode list.
        part=menu[menu.index('struct ViewModeProperties'):menu.index('void CViewModeSettings::ViewModesFiller')]
        header=(TREE/'xbmc/cores/VideoSettings.h').read_text()
        enum=re.search(r'enum ViewMode\s*\{.*?\};',header,re.S).group()
        program='#include <cassert>\n#include <cstddef>\n'+enum+r'''
struct CViewModeSettings{static int GetNextQuickCycleViewMode(int);static int GetViewModeStringIndex(int);};
'''+part+r'''
int main(){assert(CViewModeSettings::GetViewModeStringIndex(10)==16316);
 bool found=false;for(const auto& mode:viewModes)if(mode.viewMode==10&&!mode.hideFromList)found=true;
 assert(found);assert(CViewModeSettings::GetViewModeStringIndex(0)==630);}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True,capture_output=True)


if __name__=='__main__':unittest.main()
