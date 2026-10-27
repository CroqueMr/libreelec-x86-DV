"""Native HDMI mode aliases must not hide the advertised CTA timing."""
from pathlib import Path
import os,subprocess,tempfile,unittest
from test_native_video_source import TREE,body


class NativeModeAliasTests(unittest.TestCase):
    def test_native_catalog_prefers_cta_only_for_polarity_aliases(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DRMUtils.cpp').read_text()
        helpers=''
        for signature in ('bool IsCTATiming(', 'bool SameTimingExceptSync('):
            if signature in source:
                declaration=source[source.index(signature):source.index('{',source.index(signature))]
                helpers+=declaration+body(source,signature)+'\n'
        method=body(source,'std::vector<RESOLUTION_INFO> CDRMUtils::GetModes()')
        program=r'''
#include <xf86drmMode.h>
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <string>
#include <tuple>
#include <vector>
// Independent CTA fixtures isolate catalog selection from the external table.
enum {DI_CTA_VIC_VIDEO_FORMAT_SYNC_NEGATIVE,DI_CTA_VIC_VIDEO_FORMAT_SYNC_POSITIVE};
struct di_cta_vic {uint8_t code;};
struct di_cta_vic_video_format {
 int h_active,v_active,h_front,v_front,h_sync,v_sync,h_back,v_back;
 int h_sync_polarity,v_sync_polarity;int64_t pixel_clock_hz;bool interlaced;
};
const di_cta_vic_video_format* di_cta_vic_video_format_from_vic(di_cta_vic vic){
 static const di_cta_vic_video_format hd={1920,1080,88,4,44,5,148,36,1,1,148500000,false};
 static const di_cta_vic_video_format sd={1280,720,110,5,40,5,220,20,1,1,74250000,false};
 return vic.code==16?&hd:vic.code==4?&sd:nullptr;
}
HELPERS
struct RESOLUTION_INFO {std::string strId;};
struct Connector {
 std::vector<drmModeModeInfo> modes;std::string type="HDMI-A";
 int GetModesCount()const{return modes.size();}
 drmModeModeInfo* GetModeForIndex(int i){return &modes.at(i);}
 std::string GetType()const{return type;}
};
struct CDRMUtils {
 Connector connector;Connector* m_connector=&connector;
 RESOLUTION_INFO GetResolutionInfo(const drmModeModeInfo*){return {};}
 std::vector<RESOLUTION_INFO> GetModes() METHOD
};
drmModeModeInfo mode(bool cta,int clock=148500){
 drmModeModeInfo m{};m.clock=clock;m.hdisplay=1920;m.hsync_start=2008;m.hsync_end=2052;m.htotal=2200;
 m.vdisplay=1080;m.vsync_start=1084;m.vsync_end=1089;m.vtotal=1125;m.vrefresh=60;m.type=DRM_MODE_TYPE_DRIVER;
 m.flags=cta?DRM_MODE_FLAG_PHSYNC|DRM_MODE_FLAG_PVSYNC:DRM_MODE_FLAG_NHSYNC|DRM_MODE_FLAG_NVSYNC;
 return m;
}
int main(){
 CDRMUtils d;
 for(bool reversed:{false,true})for(int clock:{148500,148352}){
  d.connector.modes={mode(reversed,clock),mode(!reversed,clock)};
  auto r=d.GetModes();assert(r.size()==1 && "Native timing aliases must resolve to one advertised CTA mode");
  assert(r[0].strId==(reversed?"0":"1"));
 }
 d.connector.modes={mode(false)};assert(d.GetModes().size()==1 && d.GetModes()[0].strId=="0");
 d.connector.type="DisplayPort";d.connector.modes={mode(false),mode(true)};assert(d.GetModes().size()==2);
 d.connector.type="HDMI-A";
 auto shifted=mode(true);shifted.hsync_start++;d.connector.modes={mode(false),shifted};assert(d.GetModes().size()==2);
 auto rate=mode(true,148352);d.connector.modes={mode(false),rate};assert(d.GetModes().size()==2);
 auto stereo=mode(true);stereo.flags|=DRM_MODE_FLAG_3D_TOP_AND_BOTTOM;
 d.connector.modes={mode(false),stereo};assert(d.GetModes().size()==2);
 auto small=mode(false);small.clock=74250;small.hdisplay=1280;small.hsync_start=1390;small.hsync_end=1430;small.htotal=1650;
 small.vdisplay=720;small.vsync_start=725;small.vsync_end=730;small.vtotal=750;
 auto smallCTA=small;smallCTA.flags=DRM_MODE_FLAG_PHSYNC|DRM_MODE_FLAG_PVSYNC;
 d.connector.modes={small,smallCTA};auto r=d.GetModes();assert(r.size()==1 && r[0].strId=="1");
}
'''.replace('HELPERS',helpers).replace('METHOD',method)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I/usr/include/libdrm',str(root/'test.cpp'),
                '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            environment=os.environ.copy();environment.pop('KODI_3D_PREFER',None)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True,env=environment)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
