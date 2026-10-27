"""Native HDMI mode aliases must not hide the advertised CTA timing."""
from pathlib import Path
import os,subprocess,tempfile,unittest
from test_native_video_source import TREE,body


class NativeModeAliasTests(unittest.TestCase):
    def test_dv_alias_is_transaction_local_and_native_catalog_is_unchanged(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DRMUtils.cpp').read_text()
        helpers=''
        for signature in ('bool IsCTATiming(', 'bool SameTimingExceptSync('):
            if signature in source:
                declaration=source[source.index(signature):source.index('{',source.index(signature))]
                helpers+=declaration+body(source,signature)+'\n'
        method=body(source,'std::vector<RESOLUTION_INFO> CDRMUtils::GetModes()')
        alias=body(source,'const drmModeModeInfo* CDRMUtils::GetDVTransportMode() const') if 'CDRMUtils::GetDVTransportMode()' in source else '{return m_mode;}'
        atomic=(TREE/'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        commit=body(atomic,'bool CDRMAtomic::DrmAtomicCommit(')
        selection=commit[commit.index('  const bool dvTransport ='):commit.index('  if (flags & DRM_MODE_ATOMIC_ALLOW_MODESET)')] if '  const bool dvTransport =' in commit else 'const auto* mode=m_mode;'
        committed=body(atomic,'bool CDRMAtomic::IsSelectedModeCommitted() const')
        flip=body(atomic,'bool CDRMAtomic::FlipPageTransactional(')
        flags=flip[flip.index('  const int flags ='):flip.index('  const bool accepted =')]
        program=r'''
#include <xf86drmMode.h>
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <optional>
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
 uint64_t dv=0;std::optional<uint64_t> GetPropertyValue(const char*)const{return dv;}
 int GetModesCount()const{return modes.size();}
 drmModeModeInfo* GetModeForIndex(int i){return &modes.at(i);}
 std::string GetType()const{return type;}
};
struct CDRMUtils {
 Connector connector;Connector* m_connector=&connector;
 const drmModeModeInfo* m_mode=nullptr;
 RESOLUTION_INFO GetResolutionInfo(const drmModeModeInfo*){return {};}
 std::vector<RESOLUTION_INFO> GetModes() METHOD
 const drmModeModeInfo* GetDVTransportMode() const ALIAS
};
struct Atomic:CDRMUtils {
 struct Request{std::optional<uint64_t> requestedDV;}request;
 Request* m_req=&request;bool m_dvRestoring=false;drmModeModeInfo m_committedMode{};
 bool IsSelectedModeCommitted() const COMMITTED
 const drmModeModeInfo* Select(bool strict,int&flags){SELECTION return mode;}
 int Flags(bool m_need_modeset,bool m_dvActivating,bool restore,bool asynchronous){FLAGS return flags;}
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
  auto r=d.GetModes();assert(r.size()==2 && "Vanilla catalog and RGB Auto range contract must remain unchanged");
  assert(r[0].strId=="0" && r[1].strId=="1");
  d.m_mode=&d.connector.modes[reversed?1:0];
  assert(d.GetDVTransportMode()==&d.connector.modes[reversed?0:1]);
  assert(d.m_mode==&d.connector.modes[reversed?1:0]);
  d.m_mode=&d.connector.modes[reversed?0:1];assert(d.GetDVTransportMode()==d.m_mode);
 }
 d.connector.modes={mode(false)};assert(d.GetModes().size()==1 && d.GetModes()[0].strId=="0");
 d.connector.type="DisplayPort";d.connector.modes={mode(false),mode(true)};assert(d.GetModes().size()==2);
 d.m_mode=&d.connector.modes[0];assert(d.GetDVTransportMode()==d.m_mode);
 d.connector.type="HDMI-A";
 auto shifted=mode(true);shifted.hsync_start++;d.connector.modes={mode(false),shifted};assert(d.GetModes().size()==2);
 d.m_mode=&d.connector.modes[0];assert(d.GetDVTransportMode()==d.m_mode);
 auto rate=mode(true,148352);d.connector.modes={mode(false),rate};assert(d.GetModes().size()==2);
 d.m_mode=&d.connector.modes[0];assert(d.GetDVTransportMode()==d.m_mode);
 auto stereo=mode(true);stereo.flags|=DRM_MODE_FLAG_3D_TOP_AND_BOTTOM;
 d.connector.modes={mode(false),stereo};assert(d.GetModes().size()==2);
 auto small=mode(false);small.clock=74250;small.hdisplay=1280;small.hsync_start=1390;small.hsync_end=1430;small.htotal=1650;
 small.vdisplay=720;small.vsync_start=725;small.vsync_end=730;small.vtotal=750;
 auto smallCTA=small;smallCTA.flags=DRM_MODE_FLAG_PHSYNC|DRM_MODE_FLAG_PVSYNC;
 d.connector.modes={small,smallCTA};auto r=d.GetModes();assert(r.size()==2);
 d.m_mode=&d.connector.modes[0];assert(d.GetDVTransportMode()==&d.connector.modes[1]);
 d.m_mode=nullptr;assert(!d.GetDVTransportMode());
 Atomic a;a.connector.modes={mode(false),mode(true)};
 a.m_mode=&a.connector.modes[0];a.m_committedMode=*a.m_mode;
 int flags=0;assert(a.Select(false,flags)==a.m_mode && flags==0);
 assert(a.IsSelectedModeCommitted());
 a.request.requestedDV=1;flags=a.Flags(false,true,false,false);
 const auto* dv=a.Select(true,flags);assert(dv==&a.connector.modes[1]);
 assert(flags & DRM_MODE_ATOMIC_ALLOW_MODESET);
 // Preparation/rejection may not publish a different native timing or receipt.
 assert(a.m_mode==&a.connector.modes[0] && a.m_committedMode.flags==a.m_mode->flags);
 a.m_committedMode=*dv;a.connector.dv=1;a.request.requestedDV.reset();
 assert(a.IsSelectedModeCommitted());flags=a.Flags(false,false,false,false);
 assert(flags==0);assert(a.Select(true,flags)==a.m_mode);
 auto wrong=*dv;wrong.hsync_start++;a.m_committedMode=wrong;
 assert(!a.IsSelectedModeCommitted());a.m_committedMode=*dv;
 a.m_dvRestoring=true;a.request.requestedDV=0;flags=a.Flags(false,false,true,false);
 assert(a.Select(true,flags)==a.m_mode && (flags & DRM_MODE_ATOMIC_ALLOW_MODESET));
 assert(a.m_committedMode.flags==dv->flags);
 a.m_committedMode=*a.m_mode;a.connector.dv=0;a.request.requestedDV.reset();
 a.m_dvRestoring=false;assert(a.IsSelectedModeCommitted());
 flags=0;assert(a.Select(false,flags)==a.m_mode && flags==0);
}
'''.replace('HELPERS',helpers).replace('METHOD',method).replace('ALIAS',alias).replace('COMMITTED',committed).replace('SELECTION',selection).replace('FLAGS',flags)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I/usr/include/libdrm',str(root/'test.cpp'),
                '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            environment=os.environ.copy();environment.pop('KODI_3D_PREFER',None)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True,env=environment)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
