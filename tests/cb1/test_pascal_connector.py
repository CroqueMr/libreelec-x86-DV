"""Exercise the R580 DRM adapter lifecycle with a small DRM boundary double."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class PascalConnector(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CB1_PASCAL_SOURCE'), 'requires patched pinned R580 sources')
    def test_blob_ownership_and_failed_restore_are_not_lost(self):
        root = Path(os.environ['CB1_PASCAL_SOURCE'])/'kernel-open/nvidia-drm'
        header = (root/'nvidia-drm-connector.h').read_text()
        struct = re.search(r'struct nv_cb1_connector_state \{.*?^};', header, re.S|re.M).group()
        source = (root/'nvidia-drm-connector.c').read_text()
        start = source.index('static struct nv_cb1_connector_state *nv_cb1_state')
        end = source.index('static struct drm_connector_funcs nv_connector_funcs', start)
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <errno.h>
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct drm_property {int id;};
struct drm_property_blob {struct {unsigned id;} base; unsigned length; int refs;};
struct nv_drm_device {struct drm_property *cb1_vsif_property,*cb1_bpc_property,*cb1_dither_property;};
struct drm_connector;
struct drm_connector_state {struct drm_connector *connector; unsigned max_requested_bpc,max_bpc;};
struct drm_connector {struct drm_connector_state *state; struct nv_drm_device *dev;};
static bool alloc_fail;
static struct drm_property_blob blob={{91},27,1};
static void *nv_drm_calloc(size_t n,size_t s){return alloc_fail?NULL:calloc(n,s);}
static void nv_drm_free(void *p){free(p);}
static struct nv_drm_device *to_nv_device(struct nv_drm_device *d){return d;}
static struct drm_property_blob *drm_property_blob_get(struct drm_property_blob *b){if(b)b->refs++;return b;}
static void drm_property_blob_put(struct drm_property_blob *b){if(b){assert(b->refs>0);b->refs--;}}
static struct drm_property_blob *drm_property_lookup_blob(struct nv_drm_device *d,uint64_t id){(void)d;return id==91?drm_property_blob_get(&blob):NULL;}
static void __drm_atomic_helper_connector_destroy_state(struct drm_connector_state *s){(void)s;}
static void __drm_atomic_helper_connector_reset(struct drm_connector *c,struct drm_connector_state *s){c->state=s;s->connector=c;}
static void __drm_atomic_helper_connector_duplicate_state(struct drm_connector *c,struct drm_connector_state *s){*s=*c->state;}
'''+struct+'\n'+source[start:end]+r'''
int main(void){
 struct drm_property vsif={1},bpc={2},dither={3},other={4};
 struct nv_drm_device d={&vsif,&bpc,&dither};
 struct drm_connector c={NULL,&d};
 uint64_t value;
 nv_cb1_reset(&c);assert(c.state && c.state->max_requested_bpc==12);
 assert(nv_cb1_set_property(&c,c.state,&vsif,91)==0 && blob.refs==2);
 struct drm_connector_state *copy=nv_cb1_duplicate_state(&c);
 assert(copy && blob.refs==3);
 assert(nv_cb1_set_property(&c,c.state,&vsif,999)==-EINVAL && blob.refs==3);
 assert(nv_cb1_get_property(&c,c.state,&vsif,&value)==0 && value==91);
 assert(nv_cb1_set_property(&c,c.state,&vsif,0)==0 && blob.refs==2);
 assert(nv_cb1_get_property(&c,copy,&vsif,&value)==0 && value==91);
 blob.length=28;
 assert(nv_cb1_set_property(&c,c.state,&vsif,91)==-EINVAL && blob.refs==2);
 blob.length=27;
 assert(nv_cb1_set_property(&c,c.state,&dither,1)==0);
 assert(nv_cb1_get_property(&c,c.state,&dither,&value)==0 && value==1);
 assert(nv_cb1_set_property(&c,c.state,&dither,2)==-EINVAL);
 assert(nv_cb1_get_property(&c,c.state,&dither,&value)==0 && value==1);
 assert(nv_cb1_set_property(&c,c.state,&other,1)==-EINVAL);
 alloc_fail=true;assert(!nv_cb1_duplicate_state(&c));alloc_fail=false;
 nv_cb1_destroy_state(&c,copy);assert(blob.refs==1);
 nv_cb1_reset(&c);assert(c.state && !nv_cb1_state(c.state)->vsif && !nv_cb1_state(c.state)->dither_off);
 alloc_fail=true;nv_cb1_reset(&c);assert(!c.state);alloc_fail=false;
 assert(blob.refs==1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'check.c'; path.write_text(code)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Wno-unused-parameter',str(path),'-o',str(Path(tmp)/'check')],check=True)
            subprocess.run([str(Path(tmp)/'check')],check=True)


if __name__ == '__main__':
    unittest.main()
