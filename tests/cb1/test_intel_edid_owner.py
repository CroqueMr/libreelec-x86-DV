"""Execute HDMI detect/force owners; atomic DV must not borrow an EDID blob."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelEdidOwner(unittest.TestCase):
    def test_owned_snapshot_and_all_invalidation_paths(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        hdmi = (kernel/'drivers/gpu/drm/i915/display/intel_hdmi.c').read_text()
        edid = (kernel/'drivers/gpu/drm/drm_edid.c').read_text()
        accessor = function(edid, 'drm_edid_size')
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
#include "drm_dvbridge_edid.h"
struct edid {u8 raw[126];u8 extensions;u8 checksum;};
struct drm_edid {size_t size; const struct edid *edid;};
static size_t edid_size(const struct edid *e){return ((size_t)e->extensions+1)*128;}
#define WARN_ON(x) (x)
@@RAW@@
@@SIZE@@
struct i2c_adapter {int unused;}; struct ref_tracker {int unused;};
struct intel_display {int version;void *drm;bool enabled,access,port;};
struct intel_encoder {int unused;};
struct intel_hdmi {struct{int type,max_tmds_clock;}dp_dual_mode;void *cec_notifier;};
enum drm_connector_force {DRM_FORCE_UNSPECIFIED,DRM_FORCE_OFF,DRM_FORCE_ON,DRM_FORCE_ON_DIGITAL};
struct drm_connector {int status;enum drm_connector_force force;struct i2c_adapter *ddc;
 struct{struct{int id;}base;const char *name;}base;
 struct{int source_physical_address;}display_info;};
struct intel_connector {struct drm_connector base;struct intel_display *display;
 const struct drm_edid *detect_edid; struct dvbridge_sink_caps dv_sink_caps;
 struct intel_hdmi hdmi;};
enum drm_connector_status {connector_status_disconnected,connector_status_connected};
#define to_intel_connector(p) ((struct intel_connector *)(p))
#define to_intel_display(p) ((p)->display)
#define intel_attached_hdmi(p) (&(p)->hdmi)
static struct{struct intel_encoder base;}port;
#define hdmi_to_dig_port(p) ((void)(p),&port)
#define DISPLAY_VER(p) ((p)->version)
#define DRM_DP_DUAL_MODE_NONE 0
#define POWER_DOMAIN_GMBUS 0
#define drm_dbg_kms(...) ((void)0)
static const struct drm_edid *next_edid;static int publication_result,ddc_reads;
static struct ref_tracker *intel_display_power_get(struct intel_display*d,int p)
{(void)d;(void)p;return NULL;}
static void intel_display_power_put(struct intel_display*d,int p,struct ref_tracker*r)
{(void)d;(void)p;(void)r;}
static const struct drm_edid *drm_edid_read_ddc(struct drm_connector*c,struct i2c_adapter*a)
{(void)a;ddc_reads++;return c->force==DRM_FORCE_OFF?NULL:next_edid;}
static bool intel_gmbus_is_forced_bit(struct i2c_adapter*a){(void)a;return true;}
static void intel_gmbus_force_bit(struct i2c_adapter*a,bool b){(void)a;(void)b;}
static int drm_edid_connector_update(struct drm_connector*c,const struct drm_edid*e)
{(void)c;(void)e;return publication_result;}
static bool drm_edid_is_digital(const struct drm_edid*e)
{return e && e->size>=128 && (((const u8*)e->edid)[20]&128);}
static void drm_edid_free(const struct drm_edid*e){(void)e;}
static void intel_hdmi_dp_dual_mode_detect(struct drm_connector*c){(void)c;}
static void cec_notifier_set_phys_addr(void*p,int addr){(void)p;(void)addr;}
static void cec_notifier_phys_addr_invalidate(void*p){(void)p;}
static bool intel_display_device_enabled(struct intel_display*d){return d->enabled;}
static bool intel_display_driver_check_access(struct intel_display*d){return d->access;}
static struct intel_display *current_display;
static bool intel_digital_port_connected(struct intel_encoder*e)
{(void)e;return current_display->port;}
@@OWNERS@@
static void checksum(u8*b){u8 s=0;b[127]=0;for(int i=0;i<127;i++)s+=b[i];b[127]=-s;}
int main(void){
 u8 raw[384]={0}; const u8 magic[]={0,255,255,255,255,255,255,0};
 memcpy(raw,magic,8);raw[20]=128;raw[126]=1;
 u8*cta=raw+128;cta[0]=2;cta[1]=3;cta[2]=7;cta[4]=0xe2;cta[5]=0x78;cta[6]=2;
 u8*b=raw+256;b[0]=2;b[1]=3;b[2]=16;b[4]=0xeb;
 b[5]=1;b[6]=0x46;b[7]=0xd0;b[9]=0x42;b[11]=2;
 checksum(raw);checksum(raw+128);checksum(b);
 struct drm_edid source={sizeof(raw),(const struct edid*)raw};
 struct intel_display display={12,NULL,true,true,true};current_display=&display;
 struct intel_connector c={.base={.status=connector_status_connected},.display=&display};
 next_edid=&source;
 assert(intel_hdmi_set_edid(&c.base));
 assert(c.dv_sink_caps.status==DV_EDID_STANDARD && c.dv_sink_caps.version==2);
 /* Cached capabilities own their values, not the source bytes. */
 u8 saved_block[128];memcpy(saved_block,raw+256,128);
 memset(raw+256,0,128);
 assert(c.dv_sink_caps.status==DV_EDID_STANDARD);
 display.access=false;intel_hdmi_force(&c.base);
 assert(c.dv_sink_caps.status==DV_EDID_STANDARD);
 c.base.status=connector_status_disconnected;intel_hdmi_force(&c.base);
 assert(c.dv_sink_caps.status!=DV_EDID_STANDARD);
 for(int scenario=0;scenario<6;scenario++){
  memcpy(raw+256,saved_block,128);
  c.dv_sink_caps.status=DV_EDID_STANDARD;display.enabled=display.access=display.port=true;
  c.base.status=connector_status_connected;next_edid=&source;publication_result=0;
  if(scenario==0)display.enabled=false;
  if(scenario==1)display.port=false;
  if(scenario==2)next_edid=NULL;
  if(scenario==3)raw[20]=0;
  if(scenario==4)publication_result=-12;
  if(scenario==5)source.size=128; /* raw accessor rejects truncated extensions. */
  checksum(raw);
  (void)intel_hdmi_detect(&c.base,false);
  assert(c.dv_sink_caps.status!=DV_EDID_STANDARD);
  raw[20]=128;source.size=sizeof(raw);
 }
 /* A forced, published-connected connector must refresh EDID despite a
  * transient low live pin. Never authorize using the old sink alone. */
 for(int force=DRM_FORCE_ON;force<=DRM_FORCE_ON_DIGITAL;force++){
  for(int scenario=0;scenario<7;scenario++){
   memcpy(raw+256,saved_block,128);raw[20]=128;checksum(raw);
   source.size=sizeof(raw);next_edid=&source;publication_result=0;
   c.base.status=connector_status_connected;c.base.force=force;
   display.enabled=display.access=true;display.port=false;
   c.dv_sink_caps=dvbridge_parse_edid(raw,sizeof(raw));ddc_reads=0;
   assert(c.dv_sink_caps.status==DV_EDID_STANDARD && c.dv_sink_caps.supports_2160p60);
   if(scenario==1)next_edid=NULL; /* Cable absent, no old permission. */
   if(scenario==2)publication_result=-12;
   if(scenario==3){b[6]=0;checksum(b);} /* New sink without DV. */
   if(scenario==4){b[4]=0xeb;b[9]=0x20;checksum(b);} /* V1, no 2160p60. */
   if(scenario==5)source.size=128;
   if(scenario==6){b[9]^=1;} /* Bad checksum. */
   enum drm_connector_status status=intel_hdmi_detect(&c.base,false);
   assert(ddc_reads>0);
   if(scenario==0){
    assert(status==connector_status_connected);
    assert(c.dv_sink_caps.status==DV_EDID_STANDARD && c.dv_sink_caps.supports_2160p60);
   }else if(scenario==4){
    assert(c.dv_sink_caps.status==DV_EDID_STANDARD && !c.dv_sink_caps.supports_2160p60);
   }else assert(c.dv_sink_caps.status!=DV_EDID_STANDARD);
  }
 }
 /* Unforced, OFF and disabled connectors retain their strict invalidation. */
 for(int force=DRM_FORCE_UNSPECIFIED;force<=DRM_FORCE_OFF;force++){
  c.base.force=force;c.base.status=connector_status_connected;
  c.dv_sink_caps.status=DV_EDID_STANDARD;ddc_reads=0;
  display.port=false;(void)intel_hdmi_detect(&c.base,false);
  assert(ddc_reads==0 && c.dv_sink_caps.status!=DV_EDID_STANDARD);
 }
 for(int force=DRM_FORCE_ON;force<=DRM_FORCE_ON_DIGITAL;force++){
  c.base.force=force;c.base.status=connector_status_connected;
  c.dv_sink_caps.status=DV_EDID_STANDARD;display.enabled=false;ddc_reads=0;
  (void)intel_hdmi_detect(&c.base,false);
  assert(ddc_reads==0 && c.dv_sink_caps.status!=DV_EDID_STANDARD);
 }
 /* A forced mode with no published connection is not a cached permission. */
 for(int force=DRM_FORCE_ON;force<=DRM_FORCE_ON_DIGITAL;force++){
  c.base.force=force;c.base.status=connector_status_disconnected;
  c.dv_sink_caps.status=DV_EDID_STANDARD;display.enabled=true;ddc_reads=0;
  (void)intel_hdmi_detect(&c.base,false);
  assert(ddc_reads==0 && c.dv_sink_caps.status!=DV_EDID_STANDARD);
 }
 /* Fresh ON without EDID must not manufacture a supported sink. */
 c.base.force=DRM_FORCE_ON;c.base.status=connector_status_connected;
 c.dv_sink_caps=(struct dvbridge_sink_caps){};display.enabled=true;
 next_edid=NULL;(void)intel_hdmi_detect(&c.base,false);
 assert(c.dv_sink_caps.status!=DV_EDID_STANDARD);
 /* The ordinary high-pin path recovers from all previous failures. */
 memcpy(raw+256,saved_block,128);raw[20]=128;checksum(raw);
 source.size=sizeof(raw);next_edid=&source;publication_result=0;
 display.port=true;c.base.force=DRM_FORCE_UNSPECIFIED;
 assert(intel_hdmi_detect(&c.base,false)==connector_status_connected);
 assert(c.dv_sink_caps.status==DV_EDID_STANDARD && c.dv_sink_caps.supports_2160p60);
 /* Old display generations still use DDC without the live-pin gate. */
 display.version=10;display.port=false;
 assert(intel_hdmi_detect(&c.base,false)==connector_status_connected);
 assert(c.dv_sink_caps.status==DV_EDID_STANDARD);
 display.version=12;display.port=true;c.base.force=DRM_FORCE_OFF;
 (void)intel_hdmi_detect(&c.base,false);
 assert(c.dv_sink_caps.status!=DV_EDID_STANDARD);
 c.dv_sink_caps.status=DV_EDID_STANDARD;intel_hdmi_unset_edid(&c.base);
 assert(c.dv_sink_caps.status!=DV_EDID_STANDARD && !c.detect_edid);
 assert(drm_edid_size(&source)==384 && drm_edid_size(NULL)==0);
 source.size=128;assert(drm_edid_size(&source)==128 && !drm_edid_raw(&source));
}
'''
        owners = '\n'.join(function(hdmi, n) for n in (
            'intel_hdmi_unset_edid', 'intel_hdmi_set_edid', 'intel_hdmi_detect', 'intel_hdmi_force'))
        code = code.replace('@@RAW@@', function(edid, 'drm_edid_raw')).replace('@@SIZE@@', accessor)
        code = code.replace('@@OWNERS@@', owners)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c'; binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer',
                '-no-pie','-I'+str(kernel/'include/drm'),str(path),'-o',str(binary)],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
