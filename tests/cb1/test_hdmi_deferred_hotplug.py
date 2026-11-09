"""Exercise the actual Intel detection, lock-backoff and HPD work owners.

Only DRM/I2C/workqueue ABI adapters are deterministic. No device is accessed;
the source owners choose every guard, notification, retry and CONFIG reset.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import body

def run_owner_proof(kernel):
 kernel = Path(kernel)
 display = kernel / 'drivers/gpu/drm/i915/display'
 ddi = (display / 'intel_ddi.c').read_text(encoding='utf-8')
 hotplug = (display / 'intel_hotplug.c').read_text(encoding='utf-8')
 locks = (display / 'intel_modeset_lock.c').read_text(encoding='utf-8')
 lock_header = (display / 'intel_modeset_lock.h').read_text(encoding='utf-8')
 types = (display / 'intel_display_types.h').read_text(encoding='utf-8')
 enum = types[types.index('enum intel_hotplug_state {'):].split('};', 1)[0] + '};'
 lock_macro = lock_header[lock_header.index('#define intel_modeset_lock_ctx_retry'):].split('\n\n', 1)[0]

 # Reuse only the already reviewed external DRM/I2C ABI adapters. All control
 # flow, detection, retry accounting and lock-backoff owners below are extracted.
 program = r'''
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
 static int intel_hdmi_reset_link('''
 prefix = program.split('static int intel_hdmi_reset_link(')[0]
 prefix = prefix.replace('#include <iostream>', '#include <iostream>\n#include <functional>\n#include <cstdint>')
 prefix = prefix.replace('struct drm_modeset_acquire_ctx{};', r'''
 using u32=unsigned;using u64=unsigned long long;
 enum drm_connector_status{connector_disconnected=2};
 constexpr int DRM_MODE_CONNECTOR_HDMIA=11,HPD_NONE=0;
 struct intel_display;struct intel_connector;struct intel_encoder;
 struct work_struct{intel_display*owner;};
 struct delayed_work{work_struct work;};
 struct drm_connector_list_iter{struct drm_device*dev;};
 struct drm_modeset_acquire_ctx{};
 struct intel_atomic_state{struct{drm_modeset_acquire_ctx*acquire_ctx;}base;};
 enum hpd_pin{HPD_A=1,HPD_B=2};
 ''' + enum)
 prefix = prefix.replace('struct drm_device{struct{int connection_mutex=1;}mode_config;};', r'''
 struct drm_device{struct{int connection_mutex=1,mutex=3;}mode_config;std::vector<intel_connector*>connectors;};''')
 prefix = prefix.replace('struct intel_display{drm_device*drm;int resets=0,result=0;};', r'''
 struct intel_hotplug{u32 event_bits=0,retry_bits=0;bool ignore_long_hpd=false;delayed_work hotplug_work;};
 struct intel_display{drm_device*drm;int resets=0,result=0;struct{int lock=4;}irq;intel_hotplug hotplug;};''')
 prefix = prefix.replace('struct drm_connector{int status=connector_status_connected;', 'struct drm_connector{int status=connector_status_connected;u64 epoch_counter=0;bool force=false;int connector_type=DRM_MODE_CONNECTOR_HDMIA;drm_device*dev;')
 prefix = prefix.replace('struct intel_connector{drm_connector base;};', 'struct intel_connector{drm_connector base;int hotplug_retries=0;intel_encoder*encoder;hpd_pin pin=HPD_A;};')
 prefix = prefix.replace('struct intel_encoder{intel_display*display;intel_hdmi*hdmi;};', r'''
 struct intel_dp{bool is_mst=false;intel_connector*attached_connector;};
 struct intel_digital_port{intel_dp dp;bool tc=false,tc_reset=false,phy_test=false;};
 struct intel_encoder{intel_display*display;intel_hdmi*hdmi;intel_digital_port*port;struct{drm_device*dev;}base;
  intel_hotplug_state(*hotplug)(intel_encoder*,intel_connector*);};''')
 prefix = prefix.replace('int lock_error=0;', 'int lock_error=0,lock_failures=0,backoffs=0,acquire_init=0,acquire_fini=0;')
 prefix = prefix.replace('return *lock==lock_error?-EDEADLK:0;', 'if(*lock==lock_error&&lock_failures>0){--lock_failures;return -EDEADLK;}return 0;')
 prefix = prefix.replace('#define drm_WARN_ON(device,condition) ((void)(condition))', 'int warns=0;\n#define drm_WARN_ON(device,condition) do{warns+=!!(condition);}while(0)')
 prefix += re.search(r'^#define HPD_RETRY_DELAY[^\n]+',hotplug,re.M).group(0)+'\n'

 adapters = r'''
 void drm_modeset_acquire_init(drm_modeset_acquire_ctx*,unsigned){++acquire_init;}
 int drm_modeset_backoff(drm_modeset_acquire_ctx*){++backoffs;return 0;}
 void drm_modeset_drop_locks(drm_modeset_acquire_ctx*){}
 void drm_modeset_acquire_fini(drm_modeset_acquire_ctx*){++acquire_fini;}
 template<class T>void drm_atomic_commit_clear(T*){}
 intel_digital_port*enc_to_dig_port(intel_encoder*e){return e->port;}
 bool intel_encoder_is_tc(intel_encoder*e){return e->port->tc;}
 bool intel_dp_test_phy(intel_dp*){return false;}
 bool intel_tc_port_link_reset(intel_digital_port*p){return p->tc_reset;}
 int dp_checks=0;
 void intel_dp_check_link_state(intel_dp*){++dp_checks;}
 bool mutex_is_locked(int*){return true;}
 void mutex_lock(int*){}void mutex_unlock(int*){}
 void spin_lock_irq(int*){}void spin_unlock_irq(int*){}
 bool probe_connected=true,probe_epoch=false;
 int drm_helper_probe_detect(drm_connector*c,void*,bool){const int next=probe_connected?1:2;
  if(c->status!=next||probe_epoch){++c->epoch_counter;probe_epoch=false;}return next;}
 const char*drm_get_connector_status_name(int){return "external-probe";}
 void drm_connector_list_iter_begin(drm_device*d,drm_connector_list_iter*i){i->dev=d;}
 void drm_connector_list_iter_end(drm_connector_list_iter*){}
 #define for_each_intel_connector_iter(connector,iter) for(auto*item:(iter)->dev->connectors) if(((connector)=item))
 hpd_pin intel_connector_hpd_pin(intel_connector*c){return c->pin;}
 intel_encoder*intel_attached_encoder(intel_connector*c){return c->encoder;}
 u32 get_blocked_hpd_pin_mask(intel_display*){return 0;}
 void intel_hpd_irq_storm_switch_to_polling(intel_display*){}
 int refs=0,notifications=0,single_notifications=0,global_notifications=0,queues=0,delay_ms=0,worker_runs=0;
 bool queued=false;
 void drm_connector_get(drm_connector*){++refs;}
 void drm_connector_put(drm_connector*){--refs;}
 void drm_kms_helper_connector_hotplug_event(drm_connector*){++notifications;++single_notifications;}
 void drm_kms_helper_hotplug_event(drm_device*){++notifications;++global_notifications;}
 int msecs_to_jiffies(int ms){return ms;}
 bool mod_delayed_detection_work(intel_display*,delayed_work*,int delay){queued=true;++queues;delay_ms=delay;return true;}
 #define container_of(pointer,type,member) ((pointer)->owner)
 #define fallthrough [[fallthrough]]
 '''

 owners = [
  ('void _intel_modeset_lock_begin(drm_modeset_acquire_ctx*ctx,intel_atomic_state*state,unsigned flags,int*ret)', locks, 'void _intel_modeset_lock_begin('),
  ('bool _intel_modeset_lock_loop(int*ret)', locks, 'bool _intel_modeset_lock_loop('),
  ('void _intel_modeset_lock_end(drm_modeset_acquire_ctx*ctx,intel_atomic_state*state,int*ret)', locks, 'void _intel_modeset_lock_end('),
  (ddi[ddi.index('static int intel_hdmi_reset_link('):ddi.index('{',ddi.index('static int intel_hdmi_reset_link('))], ddi, 'static int intel_hdmi_reset_link('),
  ('static intel_hotplug_state intel_hotplug_detect_connector(intel_connector*connector)', hotplug, 'intel_hotplug_detect_connector('),
  ('intel_hotplug_state intel_encoder_hotplug(intel_encoder*encoder,intel_connector*connector)', hotplug, 'intel_encoder_hotplug('),
  ('static intel_hotplug_state intel_ddi_hotplug(intel_encoder*encoder,intel_connector*connector)', ddi, 'intel_ddi_hotplug('),
  ('static void i915_hotplug_work_func(work_struct*work)', hotplug, 'static void i915_hotplug_work_func('),
 ]
 functions = '\n'.join(signature + body(source, marker) for signature, source, marker in owners)
 # C permits implicit int/enum assignment; the C++ external ABI uses int status.
 functions = functions.replace('enum drm_connector_status old_status;', 'int old_status;')
 main = r'''
 struct Fixture{
  drm_device device;intel_display display{&device};i2c_adapter bus;intel_crtc_state state;
  intel_crtc crtc{{2,&state}};::commit commit;drm_connector_state conn{&crtc.base,&commit};
  intel_connector connector;intel_hdmi hdmi{&connector};intel_digital_port port;
  intel_encoder encoder{&display,&hdmi,&port,{&device},intel_ddi_hotplug};
  Fixture(){connector.base.dev=&device;connector.base.state=&conn;connector.base.ddc=&bus;
  connector.base.status=2;connector.encoder=&encoder;port.dp.attached_connector=&connector;
  display.hotplug.hotplug_work.work.owner=&display;device.connectors.push_back(&connector);
  queued=false;queues=0;notifications=single_notifications=global_notifications=0;refs=0;worker_runs=0;probe_connected=true;
  probe_epoch=false;lock_error=0;lock_failures=0;backoffs=0;acquire_init=acquire_fini=0;dp_checks=0;warns=0;messages.clear();kms=true;}
  void add(Fixture&other,hpd_pin pin){other.encoder.display=&display;other.encoder.base.dev=&device;
  other.connector.base.dev=&device;other.connector.pin=pin;device.connectors.push_back(&other.connector);}
  void irq(){display.hotplug.event_bits|=BIT(HPD_A);run();}
  void run(){++worker_runs;i915_hotplug_work_func(&display.hotplug.hotplug_work.work);}
  int drain(){int n=0;while(queued&&n<8){queued=false;++n;run();}return n;}
  int configs(){int count=0;for(int r:bus.reads)count+=r==SCDC_TMDS_CONFIG;return count;}
 };
 int main(){int failed=0,checks=0;auto check=[&](bool ok,const char*name){++checks;if(!ok){++failed;std::cout<<"FAIL "<<name<<'\n';}};
  for(bool deadlock:{false,true}){
   Fixture f;f.commit.hw_done=false;f.bus.config=0;
   if(deadlock){lock_error=2;lock_failures=1;}
   f.irq();
   check(notifications==1,"CHANGED pending preserves immediate notification");
   check(f.configs()==0&&f.display.resets==0,"pending never touches SCDC or resets");
   check(backoffs==(deadlock?1:0)&&acquire_init==acquire_fini,"real EDEADLK backoff finishes acquisition");
   check(!warns,"pending is expected scheduling state not false hardware warning");
   check(queued&&delay_ms==1000,"CHANGED pending schedules existing delayed worker");
   f.commit.hw_done=true;const int runs=f.drain();
   check(runs==1&&f.configs()==1&&f.display.resets==1,"completion reruns existing CONFIG/reset owner exactly once");
   check(notifications==1&&refs==0&&!queued,"rerun retains notification ownership and terminates");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();probe_connected=false;f.commit.hw_done=true;f.drain();
   check(notifications==2,"unplug at deferred check notifies independently");
   check(f.configs()==0&&f.display.resets==0,"unplug cancels SCDC/reset through fresh guards");
   check(!queued,"unplug leaves no deferred work loop");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();const int runs=f.drain();
   check(runs==1&&worker_runs==2,"permanently pending gets one native bounded retry");
   check(!queued&&f.configs()==0&&f.display.resets==0,"permanently pending terminates with no reset loop");
  }
  {
   Fixture f;f.bus.config=0;f.irq();
   check(f.configs()==1&&f.display.resets==1&&notifications==1&&!queued,"completed CHANGED original reset/notification unchanged");
  }
  {
   Fixture f;f.connector.base.status=1;f.irq();const int runs=f.drain();
   check(runs==1&&f.configs()==2&&!notifications&&!queued,"ordinary UNCHANGED retains its single retry");
  }
  {
   Fixture f;f.connector.base.status=1;f.port.dp.is_mst=true;f.irq();
   check(!queued&&f.configs()==1&&!notifications,"MST unchanged exclusion preserved");
  }
  {
   Fixture f;f.state.hdmi_scrambling=f.state.hdmi_high_tmds_clock_ratio=false;f.irq();
   check(!queued&&!f.configs()&&!f.display.resets&&notifications==1,"low rate no scrambling path unchanged");
  }
  {
   Fixture f;f.bus.config_error=-EIO;f.irq();
   check(f.configs()==1&&!f.display.resets&&notifications==1&&!queued,"typed CONFIG error is not treated as deferred commit");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();f.connector.base.state->crtc=nullptr;f.drain();
   check(!f.configs()&&!f.display.resets&&!queued,"CRTC removed before rerun uses fresh ownership");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();f.commit.hw_done=true;f.bus.config=3;f.drain();
   check(f.configs()==1&&!f.display.resets,"completion checks CONFIG but matching configuration never forces reset");
  }
  {
   Fixture f;f.port.tc=true;f.commit.hw_done=false;f.irq();const int runs=f.drain();
   check(runs==1&&!queued&&!f.configs(),"TC pending still gets only one deferred followup");
  }
  {
   Fixture f;f.port.tc=true;f.connector.base.status=1;f.irq();const int runs=f.drain();
   check(runs==5&&!queued&&f.configs()==6,"ordinary TC UNCHANGED keeps five native retries");
  }
  {
   Fixture f;f.connector.base.connector_type=10;f.irq();
   check(dp_checks==1&&!f.configs()&&!queued&&notifications==1,"DP CHANGED check/notification unchanged");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();
   intel_crtc_state new_state;new_state.hdmi_scrambling=new_state.hdmi_high_tmds_clock_ratio=false;
   intel_crtc new_crtc{{2,&new_state}};::commit new_commit;drm_connector_state new_conn{&new_crtc.base,&new_commit};
   f.connector.base.state=&new_conn;f.drain();
   check(!f.configs()&&!f.display.resets&&!queued,"new low-rate target invalidates deferred scrambling expectation");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();
   intel_crtc_state new_state;intel_crtc new_crtc{{2,&new_state}};::commit new_commit;
   drm_connector_state new_conn{&new_crtc.base,&new_commit};f.connector.base.state=&new_conn;f.bus.config=0;f.drain();
   check(f.configs()==1&&f.display.resets==1&&!f.commit.hw_done,"rerun resolves new complete target not retained old pending commit");
  }
  {
   Fixture f,g;f.add(g,HPD_A);g.connector.base.status=1;f.irq();
   check(!queued&&notifications==1&&f.configs()==1&&g.configs()==1,"ordinary shared-pin CHANGED still cancels obsolete retry");
  }
  {
   Fixture f,g;f.add(g,HPD_A);f.commit.hw_done=false;f.irq();
   check(queued&&notifications==1,"explicit deferred shared-pin check survives connection change");
   f.commit.hw_done=true;f.drain();
   check(f.configs()==1&&g.configs()==2&&!queued&&notifications==1,"shared-pin followup rereads both current owners once");
  }
  {
   Fixture f,g;f.add(g,HPD_B);f.commit.hw_done=false;f.display.hotplug.event_bits|=BIT(HPD_B);f.irq();
   check(queued&&f.display.hotplug.retry_bits==BIT(HPD_A),"unrelated CHANGED pin never acquires deferred retry");
   f.commit.hw_done=true;f.drain();
   check(f.configs()==1&&g.configs()==1&&!queued,"multiport followup visits only deferred pin");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();f.state.hw.active=false;f.drain();
   check(!f.configs()&&!f.display.resets&&!queued,"inactive current target safely ends deferred check");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();f.commit.hw_done=true;f.bus.config=0;
   f.display.result=-EIO;f.drain();
   check(f.configs()==1&&f.display.resets==1&&!queued&&warns==1,"real reset error stays diagnosed and never requeues as pending");
  }
  {
   Fixture f;f.commit.hw_done=false;f.irq();f.commit.hw_done=true;lock_error=1;lock_failures=1;f.drain();
   check(backoffs==1&&f.configs()==1&&!queued&&!warns&&acquire_init==acquire_fini,"deferred callback reacquires locks with real EDEADLK backoff");
  }
  {
   Fixture f,g;f.add(g,HPD_A);f.connector.base.status=1;f.commit.hw_done=false;f.irq();
   check(single_notifications==1&&global_notifications==0&&notifications==1,"only newly changed sibling is notified, never unchanged pending owner");
   check(queued&&f.display.hotplug.retry_bits==BIT(HPD_A),"UNCHANGED pending survives sibling CHANGED on same pin");
   f.commit.hw_done=true;f.drain();
   check(f.configs()==1&&g.configs()==2&&!queued,"UNCHANGED pending followup reads CONFIG after sibling notification");
  }
  std::cout<<checks-failed<<'/'<<checks<<" actual-owner invariants pass\n";return failed?1:0;
 }
 '''
 code = prefix + adapters + lock_macro + '\n' + functions + main
 with tempfile.TemporaryDirectory() as temporary:
  code_path=Path(temporary)/'check.cpp';binary=Path(temporary)/'check'
  code_path.write_text(code,encoding='utf-8')
  built=subprocess.run(['c++','-std=gnu++20','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-missing-field-initializers',str(code_path),'-o',str(binary)],text=True,capture_output=True)
  ran=subprocess.run([str(binary)],text=True,capture_output=True) if built.returncode==0 else None
  return built,ran

class HDMIDeferredHotplug(unittest.TestCase):
 def test_pending_commit_preserves_change_and_gets_one_native_followup(self):
  kernel=Path(os.environ.get('CB1_KERNEL_SOURCE','/nonexistent'))
  if not kernel.is_dir():
   self.skipTest('Set CB1_KERNEL_SOURCE to the full patched kernel')
  built,ran=run_owner_proof(kernel)
  self.assertEqual(built.returncode,0,built.stdout+built.stderr)
  self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
