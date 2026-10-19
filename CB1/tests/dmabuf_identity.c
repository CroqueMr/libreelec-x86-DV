/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_dmabuf.h"
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include <libdrm/drm_fourcc.h>

int main(void)
{
    FILE *first = tmpfile(), *second = tmpfile(); assert(first && second);
    AVDRMFrameDescriptor desc = {.nb_objects=1, .nb_layers=2};
    desc.objects[0] = (AVDRMObjectDescriptor){.fd=fileno(first), .size=4096,
                                            .format_modifier=DRM_FORMAT_MOD_LINEAR};
    desc.layers[0].format=DRM_FORMAT_R16; desc.layers[0].nb_planes=1;
    desc.layers[0].planes[0]=(AVDRMPlaneDescriptor){.object_index=0,.offset=0,.pitch=32};
    desc.layers[1].format=DRM_FORMAT_GR1616; desc.layers[1].nb_planes=1;
    desc.layers[1].planes[0]=(AVDRMPlaneDescriptor){.object_index=0,.offset=512,.pitch=32};
    struct dvbridge_dmabuf_key key, other;
    assert(dvbridge_dmabuf_make_key(&key,&desc,16,16,(void*)1,(void*)2,(void*)3));
    int duplicate=dup(fileno(first)); assert(duplicate>=0);
    desc.objects[0].fd=duplicate;
    assert(dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)1,(void*)2,(void*)3));
    assert(dvbridge_dmabuf_key_equal(&key,&other));
    assert(dup2(fileno(second),duplicate)==duplicate);
    assert(dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)1,(void*)2,(void*)3));
    assert(!dvbridge_dmabuf_key_equal(&key,&other));
    desc.objects[0].fd=fileno(first);
    assert(dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)4,(void*)2,(void*)3));
    assert(!dvbridge_dmabuf_key_equal(&key,&other));
    assert(dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)1,(void*)2,(void*)4));
    assert(!dvbridge_dmabuf_key_equal(&key,&other));
    desc.objects[0].format_modifier=123;
    assert(dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)1,(void*)2,(void*)3));
    assert(!dvbridge_dmabuf_key_equal(&key,&other));
    close(duplicate); fclose(first); fclose(second);
    desc.objects[0].fd=-1;
    assert(!dvbridge_dmabuf_make_key(&other,&desc,16,16,(void*)1,(void*)2,(void*)3));
}
