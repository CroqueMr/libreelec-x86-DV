"""Exercise real framebuffer import and isolated half-float TEST_ONLY admission."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code


class NvidiaFramebuffer(unittest.TestCase):
    def source(self,path):
        root=os.environ.get('CB1_DRM_STATE_SOURCE')
        return (Path(root)/path).read_text() if root else shipped_code(path)

    def execute(self,program):
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp';code.write_text(program)
            binary=Path(directory)/'check'
            built=subprocess.run(['c++','-std=c++20',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_bgr_and_opaque_float_final_images_are_not_rejected(self):
        method=re.search(r'uint32_t CDRMUtils::DrmOpaqueFbGetFromBo.*?^}',self.source('xbmc/windowing/gbm/drm/DRMUtils.cpp'),re.S|re.M).group()
        self.execute(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cerrno>
constexpr unsigned DRM_FORMAT_XRGB8888=1,DRM_FORMAT_XRGB2101010=2,DRM_FORMAT_ARGB8888=3,
 DRM_FORMAT_ARGB2101010=4,DRM_FORMAT_XBGR2101010=5,DRM_FORMAT_ABGR2101010=6,DRM_FORMAT_ABGR16161616F=7;
constexpr uint64_t DRM_FORMAT_MOD_LINEAR=0,DRM_FORMAT_MOD_INVALID=~0ull;
constexpr int DRM_MODE_FB_MODIFIERS=1,LOGERROR=1;
struct CLog {template<class... T>static void LogF(T...) {}};
struct Handle {unsigned u32=1;};
struct gbm_bo {};
Handle gbm_bo_get_handle(gbm_bo*) {return {};}
unsigned gbm_bo_get_stride(gbm_bo*) {return 32;}
unsigned gbm_bo_get_width(gbm_bo*) {return 4;}
unsigned gbm_bo_get_height(gbm_bo*) {return 4;}
unsigned alias=0;
int drmModeAddFB2WithModifiers(int,unsigned,unsigned,unsigned format,uint32_t*,uint32_t*,uint32_t*,uint64_t*,uint32_t* id,unsigned){alias=format;*id=23;return 0;}
struct FB {unsigned format=0,fb_id=12,opaque_fb_id=0;};
struct CDRMUtils {int m_fd=0;FB fb; FB* DrmFbGetFromBo(gbm_bo*){return &fb;}
 uint32_t DrmOpaqueFbGetFromBo(gbm_bo*);};
METHOD
int main(){CDRMUtils drm;gbm_bo bo;
 drm.fb.format=DRM_FORMAT_XBGR2101010;assert(drm.DrmOpaqueFbGetFromBo(&bo)==12);
 drm.fb.format=DRM_FORMAT_ABGR2101010;assert(drm.DrmOpaqueFbGetFromBo(&bo)==23 && alias==DRM_FORMAT_XBGR2101010);
 drm.fb.format=DRM_FORMAT_ABGR16161616F;assert(drm.DrmOpaqueFbGetFromBo(&bo)==12);
 drm.fb.format=99;assert(drm.DrmOpaqueFbGetFromBo(&bo)==0);
}
'''.replace('METHOD',method))

    def test_float_probe_is_test_only_and_does_not_commit_real_state(self):
        source=self.source('xbmc/windowing/gbm/drm/DRMAtomic.cpp')
        found=re.search(r'bool CDRMAtomic::TestFramebuffer.*?^}',source,re.S|re.M)
        self.assertIsNotNone(found,'half-float framebuffer admission probe is missing')
        self.execute(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cerrno>
constexpr int LOGWARNING=1,DRM_MODE_ATOMIC_TEST_ONLY=1,DRM_MODE_ATOMIC_ALLOW_MODESET=2;
struct CLog {template<class... T>static void LogF(T...) {}};
struct CDRMPlane {int GetId(){return 1;}};struct Crtc {int GetCrtcId(){return 2;}};
struct gbm_bo{};struct drm_fb{int fb_id=3,format=4;};struct Mode{unsigned hdisplay=3840,vdisplay=2160;};
struct DRMHELPERS {static int FourCCToString(int v){return v;}};
struct CDRMAtomicRequest {bool AddProperty(void*,const char*,uint64_t){return true;}void* Get(){return this;}};
int result=0,calls=0;
int drmModeAtomicCommit(int,void*,int flags,void*){assert(flags==3);++calls;return result;}
struct CDRMAtomic {CDRMPlane plane,*m_gui_plane=&plane,*m_video_plane=nullptr; Crtc crtc,*m_crtc=&crtc;
 Mode mode,*m_mode=&mode;int m_fd=1;unsigned m_width=3840,m_height=2160;drm_fb fb;
 drm_fb* DrmFbGetFromBo(gbm_bo*){return &fb;}bool TestFramebuffer(gbm_bo*);
};
METHOD
int main(){CDRMAtomic drm;gbm_bo bo;assert(drm.TestFramebuffer(&bo)&&calls==1);
 result=-1;assert(!drm.TestFramebuffer(&bo)&&calls==2);
 assert(!drm.TestFramebuffer(nullptr)&&calls==2);
}
'''.replace('METHOD',found.group()))
