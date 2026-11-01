"""Gen9 GMP changes must not use the unsynchronised static HDR fastset writer."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelGmpModeset(unittest.TestCase):
    def test_native_fastset_changed_unchanged_and_route_exclusions(self):
        root=Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/i915/display'
        hdmi=(root/'intel_hdmi.c').read_text();source=(root/'intel_display.c').read_text()
        helpers='\n'.join(function(hdmi,n) for n in ('intel_hdmi_has_gmp_hdr','intel_hdmi_uses_gmp_hdr')
                          if n+'(' in hdmi)
        macro=re.search(r'^#define PIPE_CONF_CHECK_X_WITH_MASK.*?^\} while \(0\)',source,re.M|re.S).group()
        comparison=re.search(r'PIPE_CONF_CHECK_X_WITH_MASK\(infoframes.enable, ~exclude_infoframes\);',source).group()
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
enum{TRANSCODER_EDP=3};
struct intel_display{int version;struct{bool skylake,kabylake;}platform;};
static struct intel_display display_fixture={9,{false,true}};
struct intel_crtc{struct{struct{int id;}base;const char*name;}base;};
static struct intel_crtc crtc_fixture;
#define to_intel_display(p) ((void)(p),&display_fixture)
#define to_intel_crtc(p) ((void)(p),&crtc_fixture)
#define DISPLAY_VER(p) ((p)->version)
#define drm_dbg_kms(...) ((void)0)
struct intel_crtc_state{struct{void*crtc;bool mode_changed;}uapi;
 bool has_hdmi_sink,dv,update_lrr,update_m_n,update_pipe,forced;int cpu_transcoder,dp_m_n;
 struct{bool in_range;}vrr;struct{unsigned enable,drm[8];}infoframes;};
static bool intel_dv_lab_active(const struct intel_crtc_state*s){return s->dv;}
static void intel_crtc_flag_modeset(struct intel_crtc_state*s){s->forced=true;}
#define BUILD_BUG_ON_MSG(c,m) ((void)0)
#define __same_type(a,b) __builtin_types_compatible_p(__typeof__(a),b)
#define __stringify(a) #a
#define pipe_config_mismatch(...) ((void)0)
@@MACRO@@
static bool intel_pipe_config_compare(const struct intel_crtc_state*current_config,
 const struct intel_crtc_state*pipe_config,bool fastset){
 bool ret=true;unsigned exclude_infoframes=0;
 @@COMPARISON@@
 return ret;
}
static bool allow_vblank_delay_fastset(const struct intel_crtc_state*s){(void)s;return false;}
static bool intel_compare_link_m_n(const int*a,const int*b){(void)a;(void)b;return false;}
static bool lrr_params_changed(const struct intel_crtc_state*a,const struct intel_crtc_state*b)
{(void)a;(void)b;return false;}
static bool intel_crtc_needs_modeset(const struct intel_crtc_state*s){return s->uapi.mode_changed;}
@@HELPERS@@
@@OWNER@@
int main(void){
 for(int scenario=0;scenario<8;scenario++){
  display_fixture.version=9;display_fixture.platform.kabylake=true;
  struct intel_crtc_state old={.has_hdmi_sink=true},next=old;
  next.uapi.mode_changed=true;next.update_lrr=next.update_m_n=true;
  next.infoframes.drm[0]=0x1a0187;
  bool want=scenario==0||scenario==6||scenario==7;
  if(scenario==1)next.infoframes.drm[0]=0;
  if(scenario==2)old.has_hdmi_sink=next.has_hdmi_sink=false;
  if(scenario==3)display_fixture.version=12;
  if(scenario==4)display_fixture.platform.kabylake=false;
  if(scenario==5)old.cpu_transcoder=next.cpu_transcoder=TRANSCODER_EDP;
  if(scenario==6){next.dv=true;display_fixture.version=12;}
  if(scenario==7){old.infoframes.enable=2;next.infoframes.drm[0]=0;}
  intel_crtc_check_fastset(&old,&next);
  assert(next.forced==want && next.uapi.mode_changed==want);
  if(scenario==0||scenario==6)assert(!next.update_lrr&&!next.update_m_n);
 }
}
'''.replace('@@HELPERS@@',helpers).replace('@@OWNER@@',function(source,'intel_crtc_check_fastset'))
        code=code.replace('@@MACRO@@',macro).replace('@@COMPARISON@@',comparison)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-variable','-Wno-unused-function','-Wno-unused-parameter',
                str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
