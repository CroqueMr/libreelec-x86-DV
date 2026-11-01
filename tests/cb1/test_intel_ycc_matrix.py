"""Native ILK/ICL assignment must match the signalled BT.2020 NCL transport."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelYccMatrix(unittest.TestCase):
    def test_encoded_matrix_and_active_colorimetry_transitions(self):
        source=(Path(os.environ['CB1_KERNEL_SOURCE'])/
                'drivers/gpu/drm/i915/display/intel_color.c').read_text().replace(
                    '*\nintel_csc_rgb_to_ycbcr', '*intel_csc_rgb_to_ycbcr')
        matrices='\n'.join(re.findall(
            r'static const struct intel_csc_matrix ilk_csc_matrix_\w+ = \{.*?^\};',
            source,re.M|re.S))
        helpers=(function(source,'intel_csc_rgb_to_ycbcr')
                 if 'intel_csc_rgb_to_ycbcr(' in source else '')
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
struct intel_csc_matrix {uint16_t preoff[3],coeff[9],postoff[3];};
#define ILK_CSC_COEFF_1_0 0x7800
#define ILK_CSC_COEFF_LIMITED_RANGE ((235-16)<<(12-8))
#define ILK_CSC_POSTOFF_LIMITED_RANGE (16<<(12-8))
enum {INTEL_OUTPUT_FORMAT_RGB,INTEL_OUTPUT_FORMAT_YCBCR444,INTEL_OUTPUT_FORMAT_YCBCR420};
enum {HDMI_INFOFRAME_TYPE_AVI=0x82,DP_SDP_VSC=7,HDMI_COLORSPACE_RGB=0,
 HDMI_COLORSPACE_YUV422=1,HDMI_COLORSPACE_YUV444=2,HDMI_COLORSPACE_YUV420=3,
 HDMI_COLORIMETRY_EXTENDED=3,HDMI_EXTENDED_COLORIMETRY_BT2020=6,
 HDMI_EXTENDED_COLORIMETRY_BT2020_CONST_LUM=5,DP_PIXELFORMAT_RGB=0,
 DP_PIXELFORMAT_YUV444=1,DP_PIXELFORMAT_YUV422=2,DP_PIXELFORMAT_YUV420=3,
 DP_COLORIMETRY_BT2020_RGB=6,DP_COLORIMETRY_BT2020_CYCC=6,DP_COLORIMETRY_BT2020_YCC=7};
#define ICL_CSC_ENABLE (1U<<31)
#define ICL_OUTPUT_CSC_ENABLE (1U<<30)
static unsigned intel_hdmi_infoframe_enable(unsigned t){return t==HDMI_INFOFRAME_TYPE_AVI?1:2;}
struct intel_display {void *drm;struct{bool geminilake;}platform;};
struct hdmi_avi_infoframe {int colorspace,colorimetry,extended_colorimetry;};
struct drm_dp_vsc_sdp {int pixelformat,colorimetry;};
struct intel_crtc_state {struct{void*ctm;}hw;bool csc_enable,limited_color_range;
 unsigned csc_mode;int output_format;struct intel_csc_matrix csc,output_csc;
 struct{unsigned enable;struct{struct hdmi_avi_infoframe avi;}avi;
 struct drm_dp_vsc_sdp vsc;}infoframes;};
static struct intel_display display_fixture;
#define to_intel_display(p) ((void)(p),&display_fixture)
#define drm_WARN_ON(...) ((void)0)
static bool ilk_csc_limited_range(const struct intel_crtc_state*s){return s->limited_color_range;}
static void ilk_csc_convert_ctm(struct intel_crtc_state*s,struct intel_csc_matrix*c,bool b)
{(void)s;(void)b;memset(c,0x5a,sizeof(*c));}
static void ilk_csc_copy(struct intel_display*d,struct intel_csc_matrix*a,const struct intel_csc_matrix*b)
{(void)d;*a=*b;}
@@MATRICES@@
@@HELPERS@@
@@OWNERS@@
static double coefficient(unsigned x){
 static const double divisor[8]={1,2,4,8,0,0,.25,.5};
 return (x&0x8000?-1.0:1.0)*(x&0xff8)/4096.0/divisor[(x>>12)&7];
}
static void check2020(const struct intel_csc_matrix*m){
 /* Independent NCL equations, Khronos DataFormat1.4 §15.1.3 and limited codes. */
 for(unsigned mask=0;mask<8;mask++){
  double r=mask&1?4080:0,g=mask&2?4080:0,b=mask&4?4080:0;
  double y=.2627*r+.6780*g+.0593*b;
  double expected[]={2048+(r-y)/(2*(1-.2627))*224/255,
    256+y*219/255,2048+(b-y)/(2*(1-.0593))*224/255};
  for(unsigned row=0;row<3;row++){
   double actual=m->postoff[row]+coefficient(m->coeff[row*3])*r+
    coefficient(m->coeff[row*3+1])*g+coefficient(m->coeff[row*3+2])*b;
   if(fabs(actual-expected[row])>=3.0)
    fprintf(stderr,"mask=%u row=%u actual=%f expected=%f coeff=%x,%x,%x\n",mask,row,
     actual,expected[row],m->coeff[row*3],m->coeff[row*3+1],m->coeff[row*3+2]);
   assert(fabs(actual-expected[row])<3.0);
  }
 }
}
int main(void){
 struct intel_crtc_state s={.output_format=INTEL_OUTPUT_FORMAT_YCBCR444,
  .csc_enable=true,.csc_mode=ICL_OUTPUT_CSC_ENABLE};
 for(int generation=0;generation<2;generation++)for(int scenario=0;scenario<12;scenario++){
  memset(&s.infoframes,0,sizeof(s.infoframes));s.output_format=INTEL_OUTPUT_FORMAT_YCBCR444;
  s.infoframes.avi.avi.colorspace=HDMI_COLORSPACE_YUV444;
  s.infoframes.avi.avi.colorimetry=HDMI_COLORIMETRY_EXTENDED;
  s.infoframes.avi.avi.extended_colorimetry=HDMI_EXTENDED_COLORIMETRY_BT2020;
  s.infoframes.vsc.pixelformat=DP_PIXELFORMAT_YUV444;
  s.infoframes.vsc.colorimetry=DP_COLORIMETRY_BT2020_YCC;
  s.infoframes.enable=scenario<6?1:2;
  bool want=scenario==0||scenario==5||scenario==6||scenario==11;
  if(scenario==1||scenario==7)s.infoframes.enable=0;
  if(scenario==2)s.infoframes.avi.avi.extended_colorimetry=HDMI_EXTENDED_COLORIMETRY_BT2020_CONST_LUM;
  if(scenario==3)s.infoframes.avi.avi.colorimetry=0;
  if(scenario==4)s.infoframes.avi.avi.colorspace=HDMI_COLORSPACE_RGB;
  if(scenario==8)s.infoframes.vsc.colorimetry=DP_COLORIMETRY_BT2020_CYCC;
  if(scenario==9)s.infoframes.vsc.pixelformat=DP_PIXELFORMAT_RGB;
  if(scenario==10)s.infoframes.vsc.colorimetry=1;
  if(scenario==5||scenario==11)s.output_format=INTEL_OUTPUT_FORMAT_YCBCR420;
  if(generation)icl_assign_csc(&s);else ilk_assign_csc(&s);
  const struct intel_csc_matrix*m=generation?&s.output_csc:&s.csc;
  if(want)check2020(m);else assert(!memcmp(m,&ilk_csc_matrix_rgb_to_ycbcr,sizeof(*m)));
 }
 s.output_format=INTEL_OUTPUT_FORMAT_RGB;s.limited_color_range=false;s.csc_enable=false;s.csc_mode=0;
 ilk_assign_csc(&s);assert(!memcmp(&s.csc,&(struct intel_csc_matrix){0},sizeof(s.csc)));
 icl_assign_csc(&s);assert(!memcmp(&s.output_csc,&(struct intel_csc_matrix){0},sizeof(s.csc)));
 s.hw.ctm=&s;ilk_assign_csc(&s);assert(s.csc.coeff[0]==0x5a5a);
}
'''
        code=code.replace('@@MATRICES@@',matrices).replace('@@HELPERS@@',helpers)
        code=code.replace('@@OWNERS@@','\n'.join(function(source,n) for n in (
            'intel_csc_clear','ilk_assign_csc','icl_assign_csc')))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-function',str(path),'-lm','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
