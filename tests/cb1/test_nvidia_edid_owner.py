"""Execute native detect/get-modes ownership; record the DRM publication boundary."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_hdr10_transport import function
import test_nvidia_native_hdr as native_hdr


class NvidiaEdidOwner(unittest.TestCase):
    sources = native_hdr.NvidiaNativeHdr.sources

    def test_complete_edid_survives_detect_override_and_failed_publication(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/drm_edid.c'
        drm = kernel.read_text()
        # Real DRM allocation/copy/free and legacy-size wrapper. Validation and
        # property allocation are the public kernel boundaries injected below.
        allocation = '\n'.join(function(drm, name) for name in (
            '_drm_edid_alloc','drm_edid_alloc','drm_edid_free',
            'drm_edid_legacy_init','drm_connector_update_edid_property'))
        for root in self.sources():
            source = (root/'kernel-open/nvidia-drm/nvidia-drm-connector.c').read_text()
            source = re.sub(r'#if defined\(NV_DRM_CONNECTOR_HAS_OVERRIDE_EDID\)\n(.*?)#else\n.*?#endif',
                            r'\1',source,flags=re.S)
            header = (root/'kernel-open/nvidia-drm/nvidia-drm-connector.h').read_text()
            field = next(line.strip() for line in header.splitlines() if '*edid;' in line)
            native = '\n'.join(function(source, name) for name in (
                'nv_drm_connector_destroy','__nv_drm_detect_encoder',
                '__nv_drm_connector_detect_internal','nv_drm_connector_get_modes'))
            program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned NvU32;typedef bool NvBool;
#define NV_TRUE true
#define NV_FALSE false
#define EDID_LENGTH 128
#define GFP_KERNEL 0
#define WARN_ON(x) ((void)(x))
#define BUG_ON(x) assert(!(x))
#define NV_DRM_LOG_ERR(...) ((void)0)
#define NV_DRM_DEV_LOG_ERR(...) ((void)0)
#define NV_DRM_CONNECTOR_HAS_OVERRIDE_EDID
#define DRM_MODE_CONNECTOR_DVII 1
#define DRM_MODE_ENCODER_DAC 1
#define DRM_FORCE_UNSPECIFIED 0
#define DRM_FORCE_ON 1
#define DRM_FORCE_OFF 2
#define DRM_FORCE_ON_DIGITAL 3
#define NVKMS_CONNECTOR_TYPE_DVI_I 1
#define DRM_MODE_SUBCONNECTOR_DVIA 1
#define DRM_MODE_SUBCONNECTOR_DVID 2
#define DRM_MODE_TYPE_PREFERRED 8
enum drm_connector_status {connector_status_disconnected,connector_status_connected};
struct edid {uint8_t data[126],extensions,checksum;};
struct drm_edid {size_t size;const struct edid*edid;};
static int allocations,fail_alloc,fail_publish,publish_calls,validation_calls;
static unsigned published_size;static uint8_t published[2048];
static void*tracked_alloc(size_t n){if(fail_alloc && --fail_alloc==0)return NULL;
 void*p=calloc(1,n);if(p)allocations++;return p;}
static void tracked_free(const void*p){if(p){allocations--;free((void*)p);}}
static void*dup(const void*p,size_t n,int flags){(void)flags;void*q=tracked_alloc(n);if(q)memcpy(q,p,n);return q;}
#define kmemdup dup
#define kzalloc_obj(x) tracked_alloc(sizeof(x))
#define kfree tracked_free
#define nv_drm_calloc(n,s) tracked_alloc((n)*(s))
#define nv_drm_free tracked_free
static int edid_size(const struct edid*e){return 128*(e->extensions+1);}
struct drm_property_blob {size_t length;void*data;};
struct drm_device {struct {int mutex,max_width,max_height,dvi_i_subconnector_property;}mode_config;};
struct drm_connector {struct drm_device*dev;int connector_type,force,base;
 bool override_edid;struct drm_property_blob*edid_blob_ptr;};
struct drm_encoder {int encoder_type;};
struct nv_drm_encoder {struct drm_encoder base;unsigned hDisplay;};
struct nv_drm_device {void*pDevice;};
struct nv_drm_connector {struct drm_connector base;@@FIELD@@
 struct nv_drm_encoder*nv_detected_encoder;int type;void*modeset_permission_filep;};
struct NvKmsKapiDynamicDisplayParams {unsigned handle;bool forceConnected,forceDisconnected,overrideEdid,
 connected,vrrSupported;unsigned maxWidthInPixels,maxHeightInPixels;
 struct {uint8_t buffer[2048];unsigned bufferSize;}edid;};
struct NvKmsKapiDisplayMode {int unused;};struct drm_display_mode {int type;};
static struct nv_drm_device device;
static struct nv_drm_encoder test_encoder={.hDisplay=9};
#define to_nv_connector(c) ((struct nv_drm_connector*)(c))
#define to_nv_encoder(e) ((struct nv_drm_encoder*)(e))
#define to_nv_device(d) ((void)(d),&device)
#define nv_drm_connector_for_each_possible_encoder(c,e) for(int once=1;once&&(e=&test_encoder.base);once=0)
#define nv_drm_connector_for_each_possible_encoder_end
static bool mutex_is_locked(int*x){return *x==1;}
static void drm_connector_unregister(struct drm_connector*c){(void)c;}
static void drm_connector_cleanup(struct drm_connector*c){(void)c;}
static void drm_object_property_set_value(int*b,int p,int v){(void)b;(void)p;(void)v;}
static void nv_drm_connector_revoke_permissions(struct drm_device*d,struct nv_drm_connector*c){(void)d;(void)c;}
static uint8_t incoming[2048];static unsigned incoming_size=384;static bool connected=true;
static bool get_dynamic(void*d,struct NvKmsKapiDynamicDisplayParams*p){
 (void)d;assert(p->handle==9);p->connected=connected;
 if(!p->overrideEdid){memcpy(p->edid.buffer,incoming,sizeof(incoming));p->edid.bufferSize=incoming_size;}
 return true;
}
static int get_mode(void*d,unsigned h,unsigned index,struct NvKmsKapiDisplayMode*m,NvBool*v,NvBool*p){
 (void)d;(void)m;assert(h==9);*v=*p=true;return index==0?1:0;
}
static struct {bool(*getDynamicDisplayInfo)(void*,struct NvKmsKapiDynamicDisplayParams*);
 int(*getDisplayMode)(void*,unsigned,unsigned,struct NvKmsKapiDisplayMode*,NvBool*,NvBool*);} api={get_dynamic,get_mode};
static typeof(api)*nvKms=&api;
static struct drm_display_mode*drm_mode_create(struct drm_device*d){(void)d;return tracked_alloc(sizeof(struct drm_display_mode));}
static void nvkms_display_mode_to_drm_mode(struct NvKmsKapiDisplayMode*m,struct drm_display_mode*d){(void)m;(void)d;}
static void drm_mode_probed_add(struct drm_connector*c,struct drm_display_mode*m){(void)c;tracked_free(m);}
static int drm_edid_connector_update(struct drm_connector*c,const struct drm_edid*e){
 (void)c;publish_calls++;if(fail_publish){fail_publish--;return -12;}
 published_size=e?e->size:0;if(e)memcpy(published,e->edid,e->size);return 0;
}
static bool drm_edid_valid(const struct drm_edid*e){
 validation_calls++;if(!e || e->size<128 || e->size%128)return false;
 const uint8_t*p=(const void*)e->edid;
 unsigned blocks=p[126]+1;
 if(e->size>=256 && p[128]==2 && p[129]>=3 && p[132]==0xe2 && p[133]==0x78)blocks=p[134]+1;
 if(e->size!=blocks*128)return false;
 for(unsigned i=0;i<e->size;i+=128){unsigned sum=0;for(unsigned j=0;j<128;j++)sum+=p[i+j];if(sum&255)return false;}
 return true;
}
@@ALLOCATION@@
static int nv_drm_connector_update_edid_property(struct drm_connector*c,const struct edid*e){
 return drm_connector_update_edid_property(c,e);
}
@@NATIVE@@
static void fixture(void){
 memset(incoming,0,sizeof(incoming));incoming[126]=1;
 incoming[128]=2;incoming[129]=3;incoming[130]=7;incoming[132]=0xe2;incoming[133]=0x78;incoming[134]=2;
 incoming[256]=0x70;incoming[300]=0xd0;incoming[382]=0x46;
 for(unsigned i=0;i<384;i+=128){unsigned sum=0;for(unsigned j=0;j<127;j++)sum+=incoming[i+j];incoming[i+127]=-sum;}
 incoming_size=384;
}
static void detect(struct drm_connector*c){assert(__nv_drm_connector_detect_internal(c)==connector_status_connected);}
int main(void){
 fixture();struct drm_device dev={.mode_config={.mutex=1}};
 struct nv_drm_connector*c=tracked_alloc(sizeof(*c));c->base.dev=&dev;
 detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1);
 assert(published_size==384 && "HF-EEODB third block must survive the native EDID owner");
 assert(memcmp(published,incoming,384)==0);
 incoming[300]^=1;nv_drm_connector_get_modes(&c->base);assert(published[300]!=incoming[300]);
 fixture();struct drm_property_blob override={384,incoming};c->base.edid_blob_ptr=&override;c->base.override_edid=true;
 detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==384);
 c->base.override_edid=false;fail_publish=1;publish_calls=0;
 assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==0 && publish_calls==2);
 const unsigned bad[]={0,127,256,383,2049};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){
  incoming_size=bad[i];detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==0);
 }
 fixture();incoming[300]^=1;detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==0);
 fixture();detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==384);
 for(unsigned failure=2;failure<=3;failure++){
  fail_alloc=failure;detect(&c->base);
  assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==0);
 }
 detect(&c->base);assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==384);
 connected=false;assert(__nv_drm_connector_detect_internal(&c->base)==connector_status_disconnected);
 assert(nv_drm_connector_get_modes(&c->base)==1 && published_size==0);
 assert(validation_calls>0);nv_drm_connector_destroy(&c->base);assert(allocations==0);
}
'''.replace('@@FIELD@@',field).replace('@@ALLOCATION@@',allocation).replace('@@NATIVE@@',native)
            with self.subTest(stack=str(root)), tempfile.TemporaryDirectory() as tmp:
                src, exe = Path(tmp)/'check.c', Path(tmp)/'check'
                src.write_text(program)
                build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                    '-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined',
                    str(src),'-o',str(exe)],capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stderr)
                run=subprocess.run([str(exe)],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stderr)


if __name__ == '__main__': unittest.main()
