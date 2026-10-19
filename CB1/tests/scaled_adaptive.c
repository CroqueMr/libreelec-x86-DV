/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
#include "../src/dvbridge_render.c"
#include <time.h>

static enum dvbridge_dv_policy_status finish(struct dvbridge_renderer *r)
{
    enum dvbridge_dv_policy_status status;
    for(unsigned i=0;i<10000;i++){
        status=dvbridge_render_dv_policy_poll(r);
        if(status!=DVBRIDGE_DV_PENDING && status!=DVBRIDGE_DV_BUSY)return status;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Completion timed out");return DVBRIDGE_DV_FAILED;
}

static void check_prepacked_output(struct dvbridge_renderer *r,unsigned fbo,bool flip,
                                  const AVDOVIMetadata *source,size_t source_bytes)
{
    const size_t size=3840u*2160u*4;
    unsigned char *optimized=malloc(size),*control=malloc(size);assert(optimized && control);
    unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
    uint32_t saved_packets[512];assert(count<=512);memcpy(saved_packets,packets,count*sizeof(*packets));
    const size_t bytes=r->dv.output_bytes;
    void *metadata=av_memdup(r->dv.output_metadata,bytes);assert(metadata);
    /* Save the actual optimized carrier before any reference dispatch. */
    assert(dve_copy_packed(r,fbo,flip,saved_packets,count));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,optimized);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    /* This control writes only PQ RGB; it cannot overwrite the optimized carrier. */
    r->enhanced_skip_aux=false;r->enhanced_prepack=false;
    assert(dve_program(r,r->enhanced_pq_lookup));
    assert(dve_run(r,&r->dv.enhanced_plan,r->rgb,r->dv.output.value.margins));glFinish();
    uint32_t record[16];memcpy(record,r->dv.mapped,sizeof(record));
    av_free(r->dv.output_metadata);r->dv.output_metadata=av_memdup(source,source_bytes);assert(r->dv.output_metadata);
    r->dv.output_bytes=source_bytes;
    assert(dve_derive(r,record));
    assert(r->dv.output_bytes==bytes && !memcmp(metadata,r->dv.output_metadata,bytes));
    assert(dvbridge_gl_pack(r->dv.packer,pl_opengl_unwrap(r->gpu,r->enhanced_rgb,NULL,NULL,NULL),
        fbo,3840,2160,saved_packets,count,flip));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,control);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    for(size_t i=0;i<size;i++)if(optimized[i]!=control[i]){
        fprintf(stderr,"scaled carrier byte=%zu optimized=%u reference=%u\n",i,optimized[i],control[i]);
        assert(!"Scaled prepacking changed a carrier byte");
    }
    free(metadata);free(optimized);free(control);
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3079;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_identity id={1,1,1};
    pl_fmt fmt=pl_find_named_fmt(r->gpu,"rgba8");assert(fmt);
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(target);
    unsigned fbo=0;pl_opengl_unwrap(r->gpu,target,NULL,NULL,&fbo);assert(fbo);
    const struct dvbridge_geometry cases[]={
        {1920,1080,0,0,3840,2160}, {1920,800,0,280,3840,1600}, {1280,720,0,0,3840,2160}};
    for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);c++){
        struct dvbridge_geometry geometry=cases[c];
        size_t size=(size_t)geometry.source_width*geometry.source_height;
        float *pixels=malloc(size*4*sizeof(float));assert(pixels);
        for(size_t i=0;i<size;i++){
            double nits=100+(i%251);
            for(unsigned j=0;j<4;j++)pixels[4*i+j]=j==3?1:dv_ideal_pq(nits);
        }
        pl_tex texture=reference_texture(r->gpu,geometry.source_width,geometry.source_height,pixels);free(pixels);
        struct pl_frame frame=reference_frame(texture,geometry.source_width,geometry.source_height);
        for(unsigned flip=0;flip<2;flip++){
            assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,m,bytes,
                id.picture/60.0,id.picture/60.0,geometry,target,flip,NULL)==DVBRIDGE_DV_PENDING);
            assert(!r->enhanced_linear && !r->enhanced_input && "Preserve PQ-domain scaling and intermediate precision");
            assert(r->enhanced_prepack && r->enhanced_skip_aux && "Scaled Adaptive must reuse final-domain prepacking");
            assert(finish(r)==DVBRIDGE_DV_READY);
            const struct dvbridge_dv_policy_output *output=dvbridge_render_dv_policy_output(r);assert(output);
            fprintf(stderr,"case=%u measured=%d samples=%llu reason=%d guards=%u/%u master=%g envelope=%g\n",c,
                output->value.measured,(unsigned long long)output->value.sample_count,
                output->value.expansion_reason,r->dv.mapped[10],r->dv.mapped[11],r->dv.enhanced_plan.master,r->dv.enhanced_plan.envelope);
            assert(output->value.measured && output->value.sample_count==(uint64_t)geometry.width*geometry.height);
            check_prepacked_output(r,fbo,flip,m,bytes);
            dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
        }
        pl_tex_destroy(r->gpu,&texture);
    }
    /* A rejected expansion must still pack the unchanged PQ-scaled source. */
    float level[4]={.99f,.99f,.99f,1};
    pl_tex guard=reference_texture(r->gpu,1920,1080,NULL);pl_tex_clear(r->gpu,guard,level);
    struct pl_frame guarded=reference_frame(guard,1920,1080);
    assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&guarded,m,bytes,1,1,
        (struct dvbridge_geometry){1920,1080,0,0,3840,2160},target,false,NULL)==DVBRIDGE_DV_PENDING);
    /* Inject a valid source-bound completion at the existing GPU-record seam. */
    glFinish();uint32_t record[16];memcpy(record,r->dv.mapped,sizeof(record));record[11]=1;
    assert(dve_derive(r,record));r->dv.ready=true;
    const struct dvbridge_dv_policy_output *rejected=dvbridge_render_dv_policy_output(r);assert(rejected);
    fprintf(stderr,"guarded reason=%d measured=%d flags=%u/%u\n",rejected->value.expansion_reason,
        rejected->value.measured,r->dv.mapped[10],r->dv.mapped[11]);
    assert(rejected->value.expansion_reason==CB1_DVE_SOURCE_BOUND && !rejected->value.measured);
    assert(!memcmp(m,rejected->output_metadata,bytes));
    unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
    assert(dvbridge_gl_pack(r->dv.packer,pl_opengl_unwrap(r->gpu,r->rgb,NULL,NULL,NULL),
        fbo,3840,2160,packets,count,false));
    const size_t packed_bytes=3840u*2160u*4;
    unsigned char *expected=malloc(packed_bytes),*actual=malloc(packed_bytes);assert(expected && actual);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,expected);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,actual);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(!memcmp(expected,actual,packed_bytes) && "Guarded PQ scaling must not be interpreted as linear");
    free(expected);free(actual);
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    pl_tex_destroy(r->gpu,&guard);
    pl_tex_destroy(r->gpu,&target);av_free(m);dvbridge_renderer_destroy(r);
    assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&g);
    puts("PASS scaled Adaptive: unchanged PQ scaling, full carrier equality, metadata and resource reuse");
}
