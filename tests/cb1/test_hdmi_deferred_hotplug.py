"""Exercise native HPD, completion publication and cancellation owners.

Only external DRM/I2C/list/workqueue ABI adapters are deterministic. The real
post-hw_done integration block supplies the wakeup; no fixture-only driver hook.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_native_video_source import body

def run_owner_proof(kernel):
 display=Path(kernel)/'drivers/gpu/drm/i915/display'
 source={name:(display/name).read_text(encoding='utf-8') for name in ['intel_ddi.c','intel_hotplug.c','intel_modeset_lock.c','intel_modeset_lock.h','intel_display.c','intel_display_core.h']}
 atomic=(Path(kernel)/'drivers/gpu/drm/drm_atomic_helper.c').read_text(encoding='utf-8')
 prefix=r'''
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <string>
#include <vector>
#include <iostream>
#include <functional>
#include <cstdint>
#include <atomic>
#include <mutex>
#include <thread>
#include <future>
#include <cstring>
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
int warns=0;bool warn(bool value){warns+=value;return value;}
#define drm_WARN_ON(device,condition) warn(!!(condition))
#define BIT(n) (1U<<(n))
bool drm_debug_enabled(int category){return kms&&category==DRM_UT_KMS;}

using u32=unsigned;using u64=unsigned long long;
enum drm_connector_status{connector_disconnected=2};
constexpr int DRM_MODE_CONNECTOR_HDMIA=11,HPD_NONE=0;
struct intel_display;struct intel_connector;struct intel_encoder;
struct work_struct{intel_display*owner;};
struct delayed_work{work_struct work;};
struct drm_connector_list_iter{struct drm_device*dev;};
struct drm_modeset_acquire_ctx{};
struct intel_atomic_state;
enum hpd_pin{HPD_A=1,HPD_B=2};enum pipe{PIPE_A=0,PIPE_B=1,PIPE_C=2};constexpr int I915_MAX_PIPES=4,HPD_NUM_PINS=3,HPD_ENABLED=0,HPD_DISABLED=1,HPD_MARK_DISABLED=2;
enum intel_hotplug_state{INTEL_HOTPLUG_UNCHANGED,INTEL_HOTPLUG_CHANGED,INTEL_HOTPLUG_RETRY};
struct i2c_adapter{u8 config=3,status=0;int config_error=0,status_error=0;std::vector<int>reads;};
int drm_scdc_readb(i2c_adapter*bus,u8 offset,u8*value){bus->reads.push_back(offset);const int error=offset==SCDC_TMDS_CONFIG?bus->config_error:bus->status_error;if(error)return error;*value=offset==SCDC_TMDS_CONFIG?bus->config:bus->status;return 0;}

struct drm_device{struct{int connection_mutex=1,mutex=3;}mode_config;std::vector<intel_connector*>connectors;std::vector<intel_encoder*>encoders;};

struct intel_hotplug{u32 event_bits=0,retry_bits=0;bool ignore_long_hpd=false;delayed_work hotplug_work,reenable_work;work_struct dig_port_work,poll_init_work;int dp_wq=0;
 struct{int blocked_count=0,state=HPD_ENABLED;}stats[HPD_NUM_PINS];u32 long_hpd_pin_mask=0,short_hpd_pin_mask=0;
 bool detection_work_enabled=true;u32 hdmi_wait_encoders[I915_MAX_PIPES]{};u32 hdmi_ready_encoders=0,hdmi_running_encoders=0,hdmi_cancelled_encoders=0;};
struct intel_display{drm_device*drm;int resets=0,result=0;struct{int lock=4;}irq;intel_hotplug hotplug;struct{int unordered=0;}wq;bool present=true;};
struct drm_crtc_commit;struct drm_crtc_state{drm_crtc_commit*commit=nullptr;void*event=nullptr;virtual ~drm_crtc_state()=default;};
struct intel_crtc_state:drm_crtc_state{struct{bool active=true;}hw;bool hdmi_high_tmds_clock_ratio=true,hdmi_scrambling=true;drm_crtc_state&uapi=*this;};
struct drm_crtc{int mutex=2;drm_crtc_state*state;};
struct intel_crtc{drm_crtc base;enum pipe pipe=PIPE_A;};
struct drm_crtc_commit{std::atomic<bool>hw_done{true},flip_done{true};int refs=1;};using commit=drm_crtc_commit;
struct drm_connector_state{drm_crtc*crtc;::commit*commit;};
struct drm_connector{int status=connector_status_connected;u64 epoch_counter=0;bool force=false;int connector_type=DRM_MODE_CONNECTOR_HDMIA;drm_device*dev;struct{unsigned id=391;}base;const char*name="HDMI-A-1";drm_connector_state*state;i2c_adapter*ddc;};
struct intel_connector{drm_connector base;int hotplug_retries=0;intel_encoder*encoder;hpd_pin pin=HPD_A;};
struct intel_hdmi{intel_connector*attached_connector;};

struct intel_dp{bool is_mst=false;intel_connector*attached_connector;};
struct intel_digital_port{intel_dp dp;bool tc=false,tc_reset=false,phy_test=false;};
struct intel_encoder{intel_display*display;intel_hdmi*hdmi;intel_digital_port*port;struct{drm_device*dev;unsigned index=0;}base;enum hpd_pin hpd_pin=HPD_A;
 intel_hotplug_state(*hotplug)(intel_encoder*,intel_connector*);};
intel_display*to_intel_display(intel_encoder*e){return e->display;}
intel_hdmi*enc_to_intel_hdmi(intel_encoder*e){return e->hdmi;}
intel_crtc*to_intel_crtc(drm_crtc*c){return reinterpret_cast<intel_crtc*>(c);}
intel_crtc_state*to_intel_crtc_state(drm_crtc_state*s){return static_cast<intel_crtc_state*>(s);}
bool intel_crtc_has_type(intel_crtc_state*,int){return true;}
std::function<void(int)>completion_read;int completion_reads=0;
bool try_wait_for_completion(std::atomic<bool>*done){bool value=done->load();if(completion_read){auto hook=completion_read;hook(++completion_reads);}return value;}
int lock_error=0,lock_failures=0,backoffs=0,acquire_init=0,acquire_fini=0;
int drm_modeset_lock(int*lock,drm_modeset_acquire_ctx*){if(*lock==lock_error&&lock_failures>0){--lock_failures;return -EDEADLK;}return 0;}
int intel_modeset_commit_pipes(intel_display*d,unsigned,drm_modeset_acquire_ctx*){++d->resets;return d->result;}
#define HPD_RETRY_DELAY			1000

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
std::mutex irq_mutex;thread_local int irq_depth=0;
std::function<void()>after_irq_unlock;
void spin_lock_irq(int*){irq_mutex.lock();++irq_depth;}void spin_unlock_irq(int*){--irq_depth;irq_mutex.unlock();if(after_irq_unlock){auto hook=after_irq_unlock;after_irq_unlock=nullptr;hook();}}
bool probe_connected=true,probe_epoch=false;
int drm_helper_probe_detect(drm_connector*c,void*,bool){const int next=probe_connected?1:2;
 if(c->status!=next||probe_epoch){++c->epoch_counter;probe_epoch=false;}return next;}
const char*drm_get_connector_status_name(int){return "external-probe";}
void drm_connector_list_iter_begin(drm_device*d,drm_connector_list_iter*i){i->dev=d;}
void drm_connector_list_iter_end(drm_connector_list_iter*){}
#define for_each_intel_connector_iter(connector,iter) for(auto*item:(iter)->dev->connectors) if(((connector)=item))
hpd_pin intel_connector_hpd_pin(intel_connector*c){return c->pin;}
intel_encoder*intel_attached_encoder(intel_connector*c){return c->encoder;}

void intel_hpd_irq_storm_switch_to_polling(intel_display*){}
int refs=0,notifications=0,single_notifications=0,global_notifications=0,queues=0,delay_ms=0,worker_runs=0;
bool queued=false;unsigned now_ms=0,due_ms=0;int hpd_events=0;
void drm_connector_get(drm_connector*){++refs;}
void drm_connector_put(drm_connector*){--refs;}
void drm_kms_helper_connector_hotplug_event(drm_connector*){++notifications;++single_notifications;}
void drm_kms_helper_hotplug_event(drm_device*){++notifications;++global_notifications;}
int msecs_to_jiffies(int ms){return ms;}

bool mod_delayed_work(int,delayed_work*,int delay){queued=true;++queues;delay_ms=delay;due_ms=now_ms+delay;return true;}
bool queue_delayed_work(int,delayed_work*,int delay){if(queued)return false;return mod_delayed_work(0,nullptr,delay);}
bool queue_work(int,work_struct*){return true;}
std::function<void()>cancel_sync;
bool cancel_delayed_work_sync(delayed_work*w){if(cancel_sync){auto hook=cancel_sync;cancel_sync=nullptr;hook();}bool was=queued;queued=false;return was;}
bool cancel_work_sync(work_struct*){return false;}
void flush_work(work_struct*){}
bool hpd_pin_has_pulse(intel_display*,enum hpd_pin){return false;}

#define container_of(pointer,type,member) ((pointer)->owner)
#define fallthrough [[fallthrough]]

#define lockdep_assert_held(lock) assert(irq_depth)
#define HAS_DISPLAY(display) ((display)->present)
#define MISSING_CASE(value) assert(false)
#define for_each_hpd_pin(pin) for(pin=HPD_A;pin<HPD_NUM_PINS;pin=static_cast<hpd_pin>(pin+1))
#define for_each_intel_encoder(device,encoder) for(auto*item:(device)->encoders) if(((encoder)=item))
template<class T>u32 drm_encoder_mask(T*encoder){return BIT(encoder->index);}
struct drm_atomic_commit{drm_modeset_acquire_ctx*acquire_ctx=nullptr;drm_crtc*crtc=nullptr;drm_crtc_state*old_state=nullptr,*new_state=nullptr;drm_crtc_commit*fake_commit=nullptr;};
struct intel_atomic_state{drm_atomic_commit base;intel_crtc*crtc;intel_crtc_state*new_state;};
#define for_each_oldnew_crtc_in_state(state,crtc,old,new,i) for(i=0;i<1&&((crtc=(state)->crtc),(void)crtc,(old=(state)->old_state),(new=(state)->new_state),true);++i)
#define for_each_new_intel_crtc_in_state(_state,_crtc,_new) for(bool once=true;once&&((_crtc=(_state)->crtc),(_new=(_state)->new_state),true);once=false)
#define WARN_ON(condition) warn(!!(condition))
drm_crtc_commit*drm_crtc_commit_get(drm_crtc_commit*c){++c->refs;return c;}
void drm_crtc_commit_put(drm_crtc_commit*c){--c->refs;}
std::function<void()>published;
void complete_all(std::atomic<bool>*done){done->store(true);if(published){auto hook=published;published=nullptr;hook();}}
'''
 owners=[]
 def add(file,signature,prototype):
  owners.append((file,signature));return prototype+body(source[file],signature)+'\n'
 code=prefix+source['intel_modeset_lock.h'].split('#define intel_modeset_lock_ctx_retry',1)[1].split('\n\n',1)[0].join(['#define intel_modeset_lock_ctx_retry',''])+'\n'
 for sig,proto in [('void _intel_modeset_lock_begin(','void _intel_modeset_lock_begin(drm_modeset_acquire_ctx*ctx,intel_atomic_state*state,unsigned flags,int*ret)'),('bool _intel_modeset_lock_loop(','bool _intel_modeset_lock_loop(int*ret)'),('void _intel_modeset_lock_end(','void _intel_modeset_lock_end(drm_modeset_acquire_ctx*ctx,intel_atomic_state*state,int*ret)')]:code+=add('intel_modeset_lock.c',sig,proto)
 for name,proto in [
  ('detection_work_enabled','bool detection_work_enabled(intel_display*display)'),
  ('mod_delayed_detection_work','bool mod_delayed_detection_work(intel_display*display,delayed_work*work,int delay)'),
  ('queue_delayed_detection_work','bool queue_delayed_detection_work(intel_display*display,delayed_work*work,int delay)'),
  ('hpd_pin_is_blocked','bool hpd_pin_is_blocked(intel_display*display,enum hpd_pin pin)'),
  ('get_blocked_hpd_pin_mask','u32 get_blocked_hpd_pin_mask(intel_display*display)'),
  ('hdmi_clear_check','void hdmi_clear_check(intel_display*display,u32 encoder_mask)'),
  ('hdmi_ready_encoders','u32 hdmi_ready_encoders(intel_display*display)'),
  ('intel_hpd_hdmi_cancel','void intel_hpd_hdmi_cancel(intel_encoder*encoder)'),
  ('intel_hpd_hdmi_wait_for_commit','bool intel_hpd_hdmi_wait_for_commit(intel_encoder*encoder,enum pipe pipe,drm_crtc_commit*commit)'),
  ('intel_hpd_hdmi_commit_done','void intel_hpd_hdmi_commit_done(intel_display*display,u8 pipe_mask)')]:code+=add('intel_hotplug.c',name+'(',proto)
 code+=add('intel_ddi.c','static int intel_hdmi_reset_link(','int intel_hdmi_reset_link(intel_encoder*encoder,drm_modeset_acquire_ctx*ctx,bool*retry)')
 code+=add('intel_hotplug.c','intel_hotplug_detect_connector(','intel_hotplug_state intel_hotplug_detect_connector(intel_connector*connector)')
 code+=add('intel_hotplug.c','intel_encoder_hotplug(','intel_hotplug_state intel_encoder_hotplug(intel_encoder*encoder,intel_connector*connector)')
 code+=add('intel_ddi.c','intel_ddi_hotplug(','intel_hotplug_state intel_ddi_hotplug(intel_encoder*encoder,intel_connector*connector)')
 code+=add('intel_hotplug.c','static void i915_hotplug_work_func(','void i915_hotplug_work_func(work_struct*work)')
 for name,proto in [
  ('cancel_all_detection_work','bool cancel_all_detection_work(intel_display*display)'),
  ('intel_hpd_cancel_work','void intel_hpd_cancel_work(intel_display*display)'),
  ('queue_work_for_missed_irqs','void queue_work_for_missed_irqs(intel_display*display)'),
  ('block_hpd_pin','bool block_hpd_pin(intel_display*display,enum hpd_pin pin)'),
  ('unblock_hpd_pin','bool unblock_hpd_pin(intel_display*display,enum hpd_pin pin)'),
  ('intel_hpd_block','void intel_hpd_block(intel_encoder*encoder)'),
  ('intel_hpd_unblock','void intel_hpd_unblock(intel_encoder*encoder)'),
  ('intel_hpd_clear_and_unblock','void intel_hpd_clear_and_unblock(intel_encoder*encoder)'),
  ('intel_hpd_enable_detection_work','void intel_hpd_enable_detection_work(intel_display*display)'),
  ('intel_hpd_disable_detection_work','void intel_hpd_disable_detection_work(intel_display*display)')]:code+=add('intel_hotplug.c',('void ' if name.startswith('intel_hpd_') else '')+name+'(',proto)
 code+='void drm_atomic_helper_commit_hw_done(drm_atomic_commit*state)'+body(atomic,'void drm_atomic_helper_commit_hw_done(')+'\n'
 integration=body(source['intel_display.c'],'/* Capture pipe identities before hw_done publishes the new states. */')
 assert integration.index('new_crtc_state->uapi.commit')<integration.index('drm_atomic_helper_commit_hw_done')<integration.index('intel_hpd_hdmi_commit_done')
 assert 'new_crtc_state' not in integration[integration.index('drm_atomic_helper_commit_hw_done'):]
 code+='void native_publish(intel_display*display,intel_atomic_state*state){intel_crtc*crtc;intel_crtc_state*new_crtc_state;'+integration+'}\n'
 code=code.replace('enum drm_connector_status old_status;','int old_status;')
 main=r'''struct Fixture{
 drm_device device;intel_display display{&device};i2c_adapter bus;intel_crtc_state state;
 intel_crtc crtc{{2,&state}};::commit commit;drm_connector_state conn{&crtc.base,&commit};
 intel_connector connector;intel_hdmi hdmi{&connector};intel_digital_port port;
 intel_encoder encoder{&display,&hdmi,&port,{&device},HPD_A,intel_ddi_hotplug};
 Fixture(){state.commit=&commit;connector.base.dev=&device;connector.base.state=&conn;connector.base.ddc=&bus;
 connector.base.status=2;connector.encoder=&encoder;port.dp.attached_connector=&connector;
 display.hotplug.hotplug_work.work.owner=&display;display.hotplug.reenable_work.work.owner=&display;
 display.hotplug.dig_port_work.owner=display.hotplug.poll_init_work.owner=&display;
 device.connectors.push_back(&connector);device.encoders.push_back(&encoder);
 queued=false;now_ms=due_ms=0;hpd_events=0;queues=0;notifications=single_notifications=global_notifications=0;
 refs=0;worker_runs=0;probe_connected=true;probe_epoch=false;lock_error=0;lock_failures=0;backoffs=0;
 acquire_init=acquire_fini=0;dp_checks=0;warns=0;messages.clear();kms=true;completion_reads=0;
 completion_read=nullptr;published=nullptr;cancel_sync=nullptr;after_irq_unlock=nullptr;}
 void add(Fixture&other,enum hpd_pin pin=HPD_B){other.encoder.display=&display;other.encoder.base.dev=&device;
 other.encoder.base.index=device.encoders.size();other.encoder.hpd_pin=pin;other.connector.base.dev=&device;
 other.connector.pin=pin;device.connectors.push_back(&other.connector);device.encoders.push_back(&other.encoder);}
 void irq(){++hpd_events;display.hotplug.event_bits|=BIT(connector.pin);run();}
 void run(){++worker_runs;i915_hotplug_work_func(&display.hotplug.hotplug_work.work);}
 int drain(){int count=0;while(queued&&count<16){queued=false;++count;run();}return count;}
 int advance_to(unsigned time){now_ms=time;return queued&&due_ms<=time?drain():0;}
 void publish(){drm_crtc_state previous;intel_atomic_state update{};
 update.base.crtc=&crtc.base;update.base.old_state=&previous;update.base.new_state=&state;
 update.crtc=&crtc;update.new_state=&state;native_publish(encoder.display,&update);
 if(previous.commit)drm_crtc_commit_put(previous.commit);}
 int configs(){int count=0;for(int offset:bus.reads)count+=offset==SCDC_TMDS_CONFIG;return count;}
 u32 bit(){return drm_encoder_mask(&encoder.base);}
 bool waiting(){for(auto mask:encoder.display->hotplug.hdmi_wait_encoders)if(mask&bit())return true;return false;}
 bool ready(){return encoder.display->hotplug.hdmi_ready_encoders&bit();}
 void pending(){commit.hw_done=false;}
};
int main(){int failures=0,checks=0;auto check=[&](bool good,const char*text){++checks;if(!good){++failures;std::cout<<"FAIL "<<text<<'\n';}};
 {
  Fixture f;f.pending();f.irq();check(f.waiting()&&!queued&&notifications==1,"pending arms completion not a timer and notifies CHANGED");
  f.advance_to(1000);check(!f.configs()&&worker_runs==1,"first second does not poll pending commit");
  f.advance_to(2000);f.publish();check(queued&&due_ms==2000&&f.ready(),"real native completion integration queues immediate existing work");
  f.drain();check(f.configs()==1&&!queued&&!f.waiting()&&!f.ready(),"late completion eventually checks exactly once");
  check(hpd_events==1&&notifications==1&&f.connector.hotplug_retries==0,"completion does not manufacture IRQ notification or ordinary retry");
 }
 {
  Fixture f,g;f.add(g);g.crtc.pipe=PIPE_B;f.pending();f.irq();
  for(unsigned time:{1000u,2000u,10000u,60000u}){f.advance_to(time);g.publish();f.drain();}
  check(f.waiting()&&!queued&&!f.configs()&&worker_runs==1,"permanent pending and unrelated CRTC completions never poll");
 }
 for(bool crtc_lock:{false,true}){
  Fixture f;f.pending();lock_error=crtc_lock?2:1;lock_failures=1;f.irq();f.publish();f.drain();
  check(backoffs==1&&f.configs()==1&&!warns&&acquire_init==acquire_fini,"native EDEADLK backoff preserves completion handoff");
 }
 {
  Fixture f;f.pending();f.irq();intel_hpd_disable_detection_work(&f.display);f.publish();
  check(f.ready()&&!queued,"completion while disabled retains ready owner");
  intel_hpd_enable_detection_work(&f.display);f.drain();check(f.configs()==1&&!f.ready(),"enable runs retained completion");
 }
 {
  Fixture f;f.pending();f.irq();f.publish();intel_hpd_disable_detection_work(&f.display);
  check(f.ready()&&!queued,"disable cancels queued work without discarding ready obligation");
  intel_hpd_enable_detection_work(&f.display);f.drain();check(f.configs()==1&&!queued,"reenable resumes previously queued completion once");
 }
 {
  Fixture f;f.pending();f.irq();intel_hpd_block(&f.encoder);f.publish();
  check(f.ready()&&!queued,"blocked pin retains ready encoder without work");
  intel_hpd_unblock(&f.encoder);f.drain();check(f.configs()==1&&!queued,"native unblock resumes ready encoder");
 }
 {
  Fixture f,g;f.add(g,HPD_A);g.crtc.pipe=PIPE_B;f.pending();g.pending();f.irq();
  check(f.waiting()&&g.waiting(),"shared pin arms distinct encoder owners");
  intel_hpd_block(&f.encoder);intel_hpd_clear_and_unblock(&f.encoder);f.publish();
  check(!f.waiting()&&g.waiting()&&!queued,"cancelled encoder cannot erase or wake pending sibling");
  g.publish();f.drain();check(!f.configs()&&g.configs()==1,"shared sibling gets its own completed check");
 }
 {
  Fixture f,g;f.add(g,HPD_A);g.crtc.pipe=PIPE_B;f.pending();g.pending();f.irq();
  intel_hpd_block(&g.encoder);f.publish();intel_hpd_clear_and_unblock(&g.encoder);f.drain();
  check(f.configs()==1&&!g.configs()&&!f.ready(),"clear sibling also queues surviving ready owner when shared pin unblocks");
 }
 {
  Fixture f;f.pending();completion_read=[&](int read){if(read==1){completion_read=nullptr;intel_hpd_block(&f.encoder);intel_hpd_clear_and_unblock(&f.encoder);}};
  f.irq();check(!f.waiting()&&!f.ready()&&!f.configs(),"clear before arm cancels in-flight dispatch");
  f.publish();check(!queued,"cancelled late completion cannot resurrect work");
  f.pending();intel_ddi_hotplug(&f.encoder,&f.connector);f.publish();f.drain();
  check(f.configs()==1&&hpd_events==1,"new callback can arm after clear without a new physical IRQ");
 }
 {
  Fixture f;f.pending();f.irq();intel_hpd_cancel_work(&f.display);f.publish();
  check(!queued&&!f.waiting()&&!f.ready()&&!f.configs(),"terminal cancel discards old completion after workers stop");
 }
 {
  Fixture f;f.pending();f.irq();cancel_sync=[&]{intel_hpd_hdmi_wait_for_commit(&f.encoder,PIPE_A,&f.commit);};
  intel_hpd_cancel_work(&f.display);f.publish();
  check(!queued&&!f.waiting()&&!f.ready(),"cancel clears callback rearm after synchronization, not before it");
 }
 for(bool replace:{false,true}){
  Fixture f;f.pending();f.irq();intel_crtc_state next_state;next_state.hdmi_scrambling=next_state.hdmi_high_tmds_clock_ratio=false;
  intel_crtc next_crtc{{2,&next_state}};::commit next_commit;drm_connector_state next_conn{&next_crtc.base,&next_commit};
  if(replace)f.connector.base.state=&next_conn;else f.state.hw.active=false;
  f.publish();f.drain();check(!f.configs()&&!f.waiting()&&!queued,"STOP or replacement current-state guard cancels old obligation");
 }
 {
  Fixture f;f.pending();f.irq();probe_connected=false;f.publish();f.drain();
  check(!f.configs()&&!f.waiting()&&notifications==2,"unplug detector preserves accurate notification and cancels old check");
 }
 {
  Fixture f;f.pending();f.irq();drm_crtc_commit next_commit;next_commit.hw_done=false;f.conn.commit=&next_commit;
  f.publish();f.drain();check(!f.configs()&&f.waiting()&&!queued,"old same-pipe completion rearms current pending replacement without polling");
  f.state.commit=&next_commit;f.publish();f.drain();check(f.configs()==1&&!f.waiting(),"replacement actual completion checks current owner");
 }
 {
  Fixture f;f.pending();f.irq();intel_crtc_state next_state;drm_crtc_commit next_commit;next_commit.hw_done=false;next_state.commit=&next_commit;
  intel_crtc next_crtc{{2,&next_state},PIPE_B};drm_connector_state next_conn{&next_crtc.base,&next_commit};f.connector.base.state=&next_conn;
  f.publish();f.drain();check(!f.configs()&&f.display.hotplug.hdmi_wait_encoders[PIPE_B]==f.bit(),"replacement on another pipe rekeys association");
  f.publish();check(!queued&&f.waiting(),"old-pipe completions cannot wake replacement pipe");
  drm_crtc_state previous;intel_atomic_state update{};update.base.crtc=&next_crtc.base;update.base.old_state=&previous;update.base.new_state=&next_state;update.crtc=&next_crtc;update.new_state=&next_state;
  native_publish(&f.display,&update);f.drain();if(previous.commit)drm_crtc_commit_put(previous.commit);
  check(f.configs()==1&&!f.waiting(),"new pipe native completion delivers current check");
 }
 for(int error:{0,-EIO}){
  Fixture f;f.pending();f.irq();f.bus.config=0;f.display.result=error;f.publish();f.drain();
  check(f.configs()==1&&f.display.resets==1&&!queued&&warns==(error?1:0),"existing CONFIG reset result and real error diagnosis preserved");
 }
 {
  Fixture f;f.pending();f.irq();f.bus.config_error=-EIO;f.publish();f.drain();
  check(f.configs()==1&&!f.display.resets&&!queued,"typed CONFIG I/O error is not rearmed as pending");
 }
 {
  Fixture f;f.connector.base.status=1;f.irq();check(f.drain()==1&&f.configs()==2,"ordinary unchanged native retry preserved");
 }
 {
  Fixture f;f.port.tc=true;f.connector.base.status=1;f.irq();check(f.drain()==5&&f.configs()==6,"ordinary TC five retries preserved");
 }
 {
  Fixture f;f.port.dp.is_mst=true;f.connector.base.status=1;f.irq();check(!queued&&f.configs()==1,"MST ordinary retry exclusion preserved");
 }
 {
  Fixture f;f.connector.base.connector_type=10;f.irq();check(dp_checks==1&&!f.configs()&&!queued,"DP physical path unchanged");
 }
 {
  Fixture f;f.pending();f.irq();intel_connector dp=f.connector;dp.base.connector_type=10;dp.base.status=1;f.device.connectors.insert(f.device.connectors.begin(),&dp);
  f.publish();f.drain();check(f.configs()==1&&!f.waiting()&&!queued&&dp_checks==0,"DP logical connector first on same encoder cannot swallow HDMI completion");
 }
 {
  Fixture f,g;f.add(g,HPD_A);f.connector.base.status=1;f.pending();f.irq();
  check(single_notifications==1&&global_notifications==0&&f.waiting(),"shared CHANGED sibling does not cancel or falsely notify unchanged pending owner");
  f.publish();f.drain();check(f.configs()==1&&!queued,"unchanged pending survives shared-pin notification");
 }
 {
  Fixture f;f.pending();completion_read=[&](int read){if(read==1){completion_read=nullptr;f.publish();}};f.irq();
  check(f.configs()==1&&!f.waiting(),"completion before IRQ-lock arm recheck is consumed by current check");
  f.drain();
 }
 {
  Fixture f;f.pending();std::thread completer;std::promise<void>published_signal;
  completion_read=[&](int read){if(read==2){completion_read=nullptr;
   published=[&]{published_signal.set_value();};
   completer=std::thread([&]{f.publish();});published_signal.get_future().wait();}};
  f.irq();completer.join();check(queued&&f.ready(),"completion between lock recheck and registration cannot lose wakeup");
  f.drain();check(f.configs()==1&&!queued&&!f.waiting(),"raced completion executes one current-state check");
 }
 {
  Fixture f;f.pending();completion_read=[&](int read){if(read==2){completion_read=nullptr;after_irq_unlock=[&]{f.publish();};}};
  f.irq();check(queued&&f.ready(),"completion immediately after registration survives active callback");
  f.drain();check(f.configs()==1&&!queued,"post-registration completion is not duplicated by ordinary retry");
 }
 {
  Fixture f;f.pending();completion_read=[&](int read){if(read==2){completion_read=nullptr;
   after_irq_unlock=[&]{intel_hpd_block(&f.encoder);intel_hpd_clear_and_unblock(&f.encoder);};}};
  f.irq();check(!f.waiting()&&!f.configs()&&!queued&&!warns,"clear after arm stops pending callback without CONFIG or false failure");
  f.publish();check(!queued,"completion after clear cannot recreate removed request");
 }
 {
  Fixture f;f.pending();f.irq();intel_hpd_cancel_work(&f.display);f.publish();intel_hpd_enable_detection_work(&f.display);
  f.pending();intel_ddi_hotplug(&f.encoder,&f.connector);f.publish();f.drain();
  check(f.configs()==1&&hpd_events==1,"fresh resumed transaction rearms without a new IRQ after terminal cancel");
 }
 {
  Fixture f,g;f.add(g,HPD_A);g.crtc.pipe=PIPE_B;f.pending();g.pending();
  completion_read=[&](int read){if(read==1){completion_read=nullptr;intel_hpd_block(&g.encoder);intel_hpd_clear_and_unblock(&g.encoder);}};
  f.irq();check(f.waiting()&&!g.waiting()&&!g.configs(),"same-pin clear cancels not-yet-called sibling dispatch without cancelling caller");
  f.publish();f.drain();check(f.configs()==1&&!g.configs(),"surviving owner alone consumes its native completion");
  intel_ddi_hotplug(&g.encoder,&g.connector);g.publish();f.drain();
  check(g.configs()==1,"sibling cancel epoch ends with dispatch and never permanently blocks port");
 }
 std::cout<<checks-failures<<'/'<<checks<<" actual native completion invariants pass\n";return failures?1:0;
}
'''

 code+=main
 with tempfile.TemporaryDirectory() as temporary:
  cpp=Path(temporary)/'check.cpp';binary=Path(temporary)/'check';cpp.write_text(code,encoding='utf-8')
  built=subprocess.run(['c++','-std=gnu++20','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-missing-field-initializers',str(cpp),'-o',str(binary)],capture_output=True,text=True)
  ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30) if built.returncode==0 else None
  return built,ran

class HDMIDeferredHotplug(unittest.TestCase):
 def test_pending_checks_follow_native_completion_and_lifecycle(self):
  kernel=Path(os.environ.get('CB1_KERNEL_SOURCE','/nonexistent'))
  if not kernel.is_dir():self.skipTest('Set CB1_KERNEL_SOURCE to the full patched kernel')
  built,ran=run_owner_proof(kernel)
  self.assertEqual(built.returncode,0,built.stdout+built.stderr)
  self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
