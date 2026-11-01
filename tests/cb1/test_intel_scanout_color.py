"""The DV scanout guard reads the color enables actually used by each generation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelScanoutColor(unittest.TestCase):
    def test_native_generation_and_primary_pipeline_admission(self):
        source=(Path(os.environ['CB1_KERNEL_SOURCE'])/
                'drivers/gpu/drm/i915/display/intel_display.c').read_text()
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define EINVAL 22
#define DRM_FORMAT_XRGB8888 1
#define DRM_MODE_ROTATE_0 1
#define ICL_CSC_ENABLE (1U<<31)
#define ICL_OUTPUT_CSC_ENABLE (1U<<30)
#define PRE_CSC_GAMMA_ENABLE (1U<<31)
#define POST_CSC_GAMMA_ENABLE (1U<<30)
struct intel_display{int version;};static struct intel_display display_fixture={12};
#define to_intel_display(p) ((void)(p),&display_fixture)
#define DISPLAY_VER(p) ((p)->version)
struct drm_crtc{struct drm_plane*primary;};
struct drm_framebuffer{struct{int format;}*format;unsigned width,height;};
struct drm_plane_state{struct drm_framebuffer*fb;struct drm_crtc*crtc;bool visible;
 unsigned src_x,src_y,src_w,src_h,crtc_x,crtc_y,crtc_w,crtc_h,rotation,alpha;void*color_pipeline;};
struct intel_plane_state{struct drm_plane_state uapi;
 struct{void*ctm,*degamma_lut,*gamma_lut,*lut_3d;}hw;int scaler_id;bool force_black;void*planar_linked_plane;};
struct drm_plane{struct drm_plane_state*state;};
struct intel_crtc{struct drm_crtc base;};
struct intel_crtc_state{struct{bool active;struct{unsigned hdisplay,vdisplay;}adjusted_mode;
 void*ctm,*degamma_lut,*gamma_lut;}hw;void*pre_csc_lut,*post_csc_lut;
 bool gamma_enable,csc_enable,dither,dv;unsigned gamma_mode,csc_mode;
 struct{bool enable;}vrr;struct{bool compression_enable;}dsc;struct{int scaler_users;}scaler_state;
 struct{unsigned plane_mask;}uapi;};
struct intel_atomic_state{int base;struct intel_crtc_state*s;};
#define to_intel_plane_state(p) ((struct intel_plane_state*)(p))
static const struct intel_crtc_state*intel_atomic_get_new_crtc_state(struct intel_atomic_state*a,struct intel_crtc*c)
{(void)c;return a->s;}
static unsigned drm_plane_mask(struct drm_plane*p){(void)p;return 1;}
static struct drm_plane_state*drm_atomic_get_new_plane_state(int*s,struct drm_plane*p)
{(void)s;return p->state;}
static bool intel_dv_lab_active(const struct intel_crtc_state*s){return s->dv;}
static int intel_dv_lab_scanout_reject(struct intel_crtc*c,const char*stage,unsigned r)
{(void)c;(void)stage;(void)r;return -EINVAL;}
@@OWNER@@
int main(void){
 struct{int format;}format={DRM_FORMAT_XRGB8888};
 struct drm_framebuffer fb={.format=(void*)&format,.width=3840,.height=2160};
 struct intel_plane_state p={.uapi={.fb=&fb,.visible=true,.src_w=3840U<<16,
  .src_h=2160U<<16,.crtc_w=3840,.crtc_h=2160,.rotation=DRM_MODE_ROTATE_0,.alpha=0xffff},.scaler_id=-1};
 struct drm_plane plane={&p.uapi};struct intel_crtc crtc={{&plane}};p.uapi.crtc=&crtc.base;
 struct intel_crtc_state s={.hw={.active=true,.adjusted_mode={3840,2160}},.dv=true,.uapi={1}};
 struct intel_atomic_state a={.s=&s};
 for(int gen=10;gen<=12;gen+=2)for(int scenario=0;scenario<10;scenario++){
  struct intel_crtc_state before=s;display_fixture.version=gen;p.uapi.color_pipeline=NULL;
  int want=0;
  if(scenario==1){s.csc_mode=ICL_CSC_ENABLE;want=gen>=11?-EINVAL:0;}
  if(scenario==2){s.csc_mode=ICL_OUTPUT_CSC_ENABLE;want=gen>=11?-EINVAL:0;}
  if(scenario==3){s.gamma_mode=PRE_CSC_GAMMA_ENABLE;want=gen>=11?-EINVAL:0;}
  if(scenario==4){s.gamma_mode=POST_CSC_GAMMA_ENABLE;want=gen>=11?-EINVAL:0;}
  if(scenario==5){s.gamma_mode=1;}
  if(scenario==6){p.uapi.color_pipeline=&p;want=-EINVAL;}
  if(scenario==7){s.csc_enable=true;want=gen<11?-EINVAL:0;}
  if(scenario==8){s.gamma_enable=true;want=gen<11?-EINVAL:0;}
  if(scenario==9){s.dv=false;p.uapi.color_pipeline=&p;s.csc_mode=ICL_CSC_ENABLE;}
  assert(intel_dv_lab_scanout_check(&a,&crtc)==want);s=before;
 }
}
'''.replace('@@OWNER@@',function(source,'intel_dv_lab_scanout_check'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
