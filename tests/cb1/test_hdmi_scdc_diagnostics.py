"""Compile the real Intel reset-link owner; diagnostics must not change recovery."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_native_video_source import body

KERNEL=Path(os.environ.get('CB1_KERNEL_SOURCE','/nonexistent'))

class SCDCDiagnostics(unittest.TestCase):
 def test_typed_scdc_observation_preserves_every_guard_return_and_reset(self):
  source=(KERNEL/'drivers/gpu/drm/i915/display/intel_ddi.c').read_text(encoding='utf-8')
  owner=body(source,'static int intel_hdmi_reset_link(')
  program=r'''
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <string>
#include <vector>
#include <iostream>
using u8=unsigned char;
#define SCDC_TMDS_CONFIG 0x20
#define SCDC_SCRAMBLER_STATUS 0x21
#define SCDC_TMDS_BIT_CLOCK_RATIO_BY_40 2
#define SCDC_SCRAMBLING_ENABLE 1
constexpr int connector_status_connected=1,DRM_UT_KMS=4,INTEL_OUTPUT_HDMI=1;
bool kms=false;
std::vector<std::string>messages;
void log(const char*format,...){char text[768];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);messages.emplace_back(text);}
#define drm_dbg_kms(device,format,...) do{if(kms)log(format,##__VA_ARGS__);}while(0)
#define drm_err(device,format,...) log(format,##__VA_ARGS__)
#define drm_WARN_ON(device,condition) ((void)(condition))
#define BIT(n) (1U<<(n))
bool drm_debug_enabled(int category){return kms&&category==DRM_UT_KMS;}
struct drm_modeset_acquire_ctx{};
struct i2c_adapter{u8 config=3,status=0;int config_error=0,status_error=0;std::vector<int>reads;};
int drm_scdc_readb(i2c_adapter*bus,u8 offset,u8*value){bus->reads.push_back(offset);const int error=offset==SCDC_TMDS_CONFIG?bus->config_error:bus->status_error;if(error)return error;*value=offset==SCDC_TMDS_CONFIG?bus->config:bus->status;return 0;}
struct drm_device{struct{int connection_mutex=1;}mode_config;};
struct intel_display{drm_device*drm;int resets=0,result=0;};
struct drm_crtc_state{virtual ~drm_crtc_state()=default;};
struct intel_crtc_state:drm_crtc_state{struct{bool active=true;}hw;bool hdmi_high_tmds_clock_ratio=true,hdmi_scrambling=true;};
struct drm_crtc{int mutex=2;drm_crtc_state*state;};
struct intel_crtc{drm_crtc base;int pipe=0;};
struct commit{bool hw_done=true;};
struct drm_connector_state{drm_crtc*crtc;::commit*commit;};
struct drm_connector{int status=connector_status_connected;struct{unsigned id=391;}base;const char*name="HDMI-A-1";drm_connector_state*state;i2c_adapter*ddc;};
struct intel_connector{drm_connector base;};
struct intel_hdmi{intel_connector*attached_connector;};
struct intel_encoder{intel_display*display;intel_hdmi*hdmi;};
intel_display*to_intel_display(intel_encoder*e){return e->display;}
intel_hdmi*enc_to_intel_hdmi(intel_encoder*e){return e->hdmi;}
intel_crtc*to_intel_crtc(drm_crtc*c){return reinterpret_cast<intel_crtc*>(c);}
intel_crtc_state*to_intel_crtc_state(drm_crtc_state*s){return static_cast<intel_crtc_state*>(s);}
bool intel_crtc_has_type(intel_crtc_state*,int){return true;}
bool try_wait_for_completion(bool*done){return *done;}
int lock_error=0;
int drm_modeset_lock(int*lock,drm_modeset_acquire_ctx*){return *lock==lock_error?-EDEADLK:0;}
int intel_modeset_commit_pipes(intel_display*d,unsigned,drm_modeset_acquire_ctx*){++d->resets;return d->result;}
// HPD lifecycle/registration is exercised with its real owners by the separate
// native completion fixture; this test isolates diagnostic return/I2C behavior.
void intel_hpd_hdmi_cancel(intel_encoder*){}
bool intel_hpd_hdmi_wait_for_commit(intel_encoder*,int,commit*c){return c&&!try_wait_for_completion(&c->hw_done);}
static int intel_hdmi_reset_link(intel_encoder*encoder,drm_modeset_acquire_ctx*ctx,bool*retry) OWNER
struct Fixture{
 drm_device device;intel_display display{&device};i2c_adapter bus;intel_crtc_state state;
 intel_crtc crtc{{2,&state}};::commit commit;drm_connector_state conn{&crtc.base,&commit};
 intel_connector connector{{connector_status_connected,{391},"HDMI-A-1",&conn,&bus}};
 intel_hdmi hdmi{&connector};intel_encoder encoder{&display,&hdmi};
};
int main(){int failures=0,cases=0;auto check=[&](bool good,const std::string&name){++cases;failures+=!good;if(!good)std::cout<<"FAIL "<<name<<'\n';};
 auto has=[](const char*text){for(const auto&m:messages)if(m.find(text)!=std::string::npos)return true;return false;};
 for(bool debug:{false,true})for(int scenario=0;scenario<17;++scenario){
  Fixture f;messages.clear();lock_error=0;kms=debug;
  int expected_return=0,expected_resets=0,expected_config_reads=1;const char*reason=nullptr;
  switch(scenario){
   case 0:reason="config-match";break;
   case 1:f.bus.status=1;reason="config-match";break;
   case 2:f.bus.status_error=-EIO;reason="config-match";break;
   case 3:f.bus.config_error=-EIO;reason="config-read-error";break;
   case 4:f.bus.config=0;expected_resets=1;reason="config-mismatch";break;
   case 5:f.bus.config=0;f.display.result=-EDEADLK;expected_return=-EDEADLK;expected_resets=1;reason="config-mismatch";break;
   case 6:f.connector.base.status=2;expected_config_reads=0;reason="not-connected";break;
   case 7:f.conn.crtc=nullptr;expected_config_reads=0;reason="no-crtc";break;
   case 8:f.state.hw.active=false;expected_config_reads=0;reason="inactive";break;
   case 9:f.state.hdmi_scrambling=f.state.hdmi_high_tmds_clock_ratio=false;expected_config_reads=0;reason="not-scrambled";break;
   case 10:f.commit.hw_done=false;expected_config_reads=0;reason="check-deferred";break;
   case 11:lock_error=1;expected_config_reads=0;expected_return=-EDEADLK;reason="connection-lock";break;
   case 12:lock_error=2;expected_config_reads=0;expected_return=-EDEADLK;reason="crtc-lock";break;
   case 13:f.conn.commit=nullptr;reason="config-match";break;
   case 14:f.state.hdmi_high_tmds_clock_ratio=false;f.bus.config=1;reason="config-match";break;
   case 15:f.bus.config=0xa3;f.bus.status=0x43;reason="config-match";break;
   case 16:f.bus.config=0;f.bus.status_error=-EREMOTEIO;expected_resets=1;reason="config-mismatch";break;
  }
  drm_modeset_acquire_ctx ctx;bool retry=true;const auto result=intel_hdmi_reset_link(&f.encoder,&ctx,&retry);
  int config_reads=0,status_reads=0;for(int offset:f.bus.reads){config_reads+=offset==0x20;status_reads+=offset==0x21;}
  const std::string label="debug="+std::to_string(debug)+" case="+std::to_string(scenario);
  check(result==expected_return&&f.display.resets==expected_resets,label+" unchanged return/reset");
  check(retry==(scenario==10),label+" only pending commit requests deferred check");
  check(config_reads==expected_config_reads,label+" unchanged CONFIG I/O");
  check(status_reads==(debug&&expected_config_reads&&!f.bus.config_error?1:0),label+" STATUS is diagnostic-only and guarded");
  if(debug){check(has(reason),label+" guard/decision reason");
   if(expected_config_reads&&!f.bus.config_error){check(has("expected_scrambling="),label+" expected CRTC facts");check(has("hw_done="),label+" completion fact");
    if(f.bus.status_error)check(has((std::string("status_ret=")+std::to_string(f.bus.status_error)).c_str())&&has("status=unavailable"),label+" typed STATUS failure");
    else check(has(scenario==15?"status=0x43":scenario==1?"status=0x01":"status=0x00"),label+" raw STATUS value");
   }
  }
 }
 std::cout<<cases-failures<<'/'<<cases<<" invariants pass\n";return failures?1:0;
}
'''.replace('OWNER',owner)
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);code=root/'check.cpp';binary=root/'check';code.write_text(program,encoding='utf-8')
   built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(code),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(built.returncode,0,built.stderr)
   ran=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
