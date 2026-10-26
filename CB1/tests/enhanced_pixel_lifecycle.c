/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
static unsigned compute_compilations;
static GLuint count_shader(GLenum type)
{if(type==GL_COMPUTE_SHADER)compute_compilations++;return glCreateShader(type);}
#define glCreateShader count_shader
#include "../src/dvbridge_render.c"
#undef glCreateShader
#include <time.h>
extern bool dvbridge_gl_patch(struct dvbridge_gl_packer *,unsigned,unsigned,int,int,
    const uint32_t[512],unsigned,bool) __attribute__((weak));
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
static void exact_prepack(struct dvbridge_renderer *r,unsigned fbo,bool flip)
{
    assert(r->dv.prepacked);
    const size_t bytes=3840u*2160u*4;unsigned char *expected=malloc(bytes),*actual=malloc(bytes);
    assert(expected && actual);
    unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
    uint32_t complete[512];
    if(!r->dv.enhanced_overlay){
        for(unsigned i=0;i<512;i++)complete[i]=(i*137u+29u)&255u;
        packets=complete;count=4;
    }
    pl_tex pq=r->dv.output.intermediate;
    if(!pq){
        r->enhanced_skip_aux=false;
        assert(dve_run(r,&r->dv.enhanced_plan,r->rgb,r->dv.output.value.margins));
        glFinish();pq=r->enhanced_rgb;r->enhanced_skip_aux=true;
    }
    if(r->dv.enhanced_overlay){pq=dve_compose(r,pq,true);assert(pq);}
    assert(dvbridge_gl_pack(r->dv.packer,pl_opengl_unwrap(r->gpu,pq,NULL,NULL,NULL),fbo,3840,2160,packets,count,flip));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,expected);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    const GLenum caps[]={GL_BLEND,GL_DEPTH_TEST,GL_STENCIL_TEST,GL_SCISSOR_TEST,
        GL_DITHER,GL_CULL_FACE,GL_RASTERIZER_DISCARD,GL_SAMPLE_ALPHA_TO_COVERAGE,GL_SAMPLE_COVERAGE};
    glScissor(13,17,29,31);for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++)glEnable(caps[i]);
    glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
    assert(dve_copy_packed(r,fbo,flip,packets,count));
    GLint box[4];glGetIntegerv(GL_SCISSOR_BOX,box);assert(box[0]==13 && box[1]==17 && box[2]==29 && box[3]==31);
    for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){assert(glIsEnabled(caps[i]));glDisable(caps[i]);}
    GLboolean mask[4];glGetBooleanv(GL_COLOR_WRITEMASK,mask);for(unsigned i=0;i<4;i++)assert(!mask[i]);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,actual);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    for(size_t i=0;i<bytes;i++)if(expected[i]!=actual[i]){
        fprintf(stderr,"prepack mismatch byte=%zu expected=%u actual=%u flip=%d\n",i,expected[i],actual[i],flip);
        assert(!"Prepacked transport changed bytes");
    }
    free(expected);free(actual);
}
static void adaptive_ordered_handoff(pl_gpu,const struct pl_frame *,const AVDOVIMetadata *,size_t);
static void adaptive_guidance_equivalence(pl_gpu gpu)
{
    enum {W=3840,H=2160};
    float *pixels=malloc((size_t)W*H*4*sizeof(*pixels));assert(pixels);
    pl_matrix3x3 matrix=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    float tile[64][4];
    for(unsigned i=0;i<64;i++){
        double rgb[3];
        for(unsigned c=0;c<3;c++)rgb[c]=i<8?(double[]){0,.001,.1,1,5,9,10,10.1}[i]:
            20+((i*(17+13*c))%880);
        for(unsigned c=0;c<3;c++)tile[i][c]=dv_ideal_pq(
            matrix.m[c][0]*rgb[0]+matrix.m[c][1]*rgb[1]+matrix.m[c][2]*rgb[2]);
        tile[i][3]=1;
    }
    for(unsigned i=0;i<W*H;i++)memcpy(pixels+4*i,tile[(i+i/W)%64],sizeof(tile[0]));
    pl_tex input=reference_texture(gpu,W,H,pixels);free(pixels);
    struct pl_frame frame=reference_frame(input,W,H);
    pl_fmt fmt=pl_find_named_fmt(gpu,"rgba8");assert(fmt);
    pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=W,.h=H,.format=fmt,.renderable=true));assert(target);
    unsigned fbo;pl_opengl_unwrap(gpu,target,NULL,NULL,&fbo);
    const size_t n=(size_t)W*H*4;
    unsigned char *expected=malloc(n),*actual=malloc(n);assert(expected && actual);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    av_dovi_get_color(metadata)->source_max_pq=3079;metadata->num_ext_blocks=3;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    *av_dovi_get_ext(metadata,2)=(AVDOVIDmData){.level=5,.l5={.top_offset=18,.bottom_offset=22}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_P3_D65}};
    for(unsigned color=0;color<3;color++){
        if(color){av_dovi_get_ext(metadata,1)->l2.trim_chroma_weight=2300;
            av_dovi_get_ext(metadata,1)->l2.trim_saturation_gain=2200;}
        if(color==2)for(unsigned c=1;c<3;c++){
            AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(metadata)->curves[c];
            curve->mapping_idc[0]=AV_DOVI_MAPPING_MMR;curve->mmr_order[0]=1;
            curve->mmr_coef[0][0][c]=4096;curve->mmr_coef[0][0][0]=16;
        }
        void *reference=NULL;size_t reference_bytes=0;
        for(unsigned repeat=0;repeat<2;repeat++){
            struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
            struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
            const char *vendor=(const char *)glGetString(GL_VENDOR);
            assert(r->reuse_authored_storage==(vendor && !strcmp(vendor,"Intel")));
            r->reuse_authored_storage=true; /* Verify the optimized contract on both GPUs. */

            compute_compilations=0;
            struct dvbridge_identity id={71,83,1};
            enum dvbridge_dv_policy_status prepared=dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,metadata,bytes,0,0,
                (struct dvbridge_geometry){W,H,0,0,W,H},target,false,NULL);
            assert(prepared==DVBRIDGE_DV_PENDING);
            assert(!r->rgb && !r->enhanced_rgb &&
                "Packed FP16 Adaptive must not allocate unused full-frame FP32 images");
            assert(compute_compilations==1u &&
                "Only the active authored kernel may be compiled");
            GLuint storage[3],sampler=r->dv.sampler;memcpy(storage,r->dv.buffers,sizeof(storage));
            const uint32_t *mapping=r->dv.mapped;
            assert(finish(r)==DVBRIDGE_DV_READY);
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
            assert(out && out->value.output_generation==DVBRIDGE_RECONSTRUCTED_ENHANCED &&
                out->value.expansion_reason==CB1_DVE_ACTIVE);
            if(!repeat){reference_bytes=out->bytes;reference=av_memdup(out->output_metadata,reference_bytes);assert(reference);}
            else assert(out->bytes==reference_bytes && !memcmp(reference,out->output_metadata,reference_bytes) &&
                "Authored transport must preserve every output metadata byte");
            assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glReadPixels(0,0,W,H,GL_RGBA,GL_UNSIGNED_BYTE,repeat?actual:expected);
            glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
            if(repeat && memcmp(expected,actual,n)){
                unsigned max_y=0,max_c=0,max_black=0;size_t changed=0;double sum_y=0,sum_c=0;
                for(size_t i=0;i<n;i+=4){
                    unsigned y0=16*expected[i+1]+(expected[i+2]&15),y1=16*actual[i+1]+(actual[i+2]&15);
                    unsigned c0=(16*expected[i]+(expected[i+2]>>4))&~1u,c1=(16*actual[i]+(actual[i+2]>>4))&~1u;
                    unsigned y=abs((int)y0-(int)y1),c=abs((int)c0-(int)c1);
                    if(y>max_y)max_y=y;if(c>max_c)max_c=c;sum_y+=y;sum_c+=c;changed+=y||c;
                    if(y0<=256 && y>max_black)max_black=y;
                }
                fprintf(stderr,"Adaptive carrier error12: maxY=%u maxC=%u meanY=%g meanC=%g black=%u changed=%zu/%u\n",
                    max_y,max_c,sum_y/(W*H),sum_c/(W*H),max_black,changed,W*H);
                assert(!memcmp(expected,actual,n) &&
                    "Authored transport must preserve every movie byte");
            }
            uint64_t digest=UINT64_C(14695981039346656037);
            const unsigned char *carrier=repeat?actual:expected;
            for(size_t i=0;i<n;i++)digest=(digest^carrier[i])*UINT64_C(1099511628211);
            fprintf(stderr,"CARRIER_HASH colour=%u repeat=%u fnv1a=%016llx\n",color,repeat,(unsigned long long)digest);
            if(repeat)memcpy(expected,actual,n);
            dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
            for(unsigned k=0;k<3;k++)assert(glIsBuffer(storage[k]) &&
                "Completed Adaptive storage must stay owned by the renderer");
            assert(glIsSampler(sampler));
            if(repeat){
                id.picture++;
                assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,metadata,bytes,0,0,
                    (struct dvbridge_geometry){W,H,0,0,W,H},target,false,NULL)==DVBRIDGE_DV_PENDING);
                assert(!memcmp(storage,r->dv.buffers,sizeof(storage)) && r->dv.mapped==mapping &&
                    r->dv.sampler==sampler && "Reuse storage, never the previous frame identity");
                assert(finish(r)==DVBRIDGE_DV_READY);
                assert(dvbridge_render_dv_policy_update_overlay(r,NULL,true));
                assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
                assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
                glBindFramebuffer(GL_FRAMEBUFFER,fbo);
                glReadPixels(0,0,W,H,GL_RGBA,GL_UNSIGNED_BYTE,actual);
                glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
                assert(!memcmp(expected,actual,n) && "Late GUI materialization must preserve carrier/RPU");
                dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
            }
            dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
            for(unsigned k=0;k<3;k++)assert(!glIsBuffer(storage[k]));
            assert(!glIsSampler(sampler));
        }
        av_free(reference);
        if(color==1)adaptive_ordered_handoff(gpu,&frame,metadata,bytes);
    }
    av_free(metadata);free(expected);free(actual);
    pl_tex_destroy(gpu,&target);pl_tex_destroy(gpu,&input);
    puts("PASS Adaptive transport: exact4K carrier/RPU/late-GUI, colour guidance, shadows and L5");
}
static GLenum storage_timeout(GLsync sync,GLbitfield flags,GLuint64 timeout)
{assert(sync && !flags && !timeout);return GL_TIMEOUT_EXPIRED;}
static void adaptive_storage_ownership(pl_gpu gpu)
{
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    r->reuse_authored_storage=true;
    GLuint held[3]={0},sampler=0;const uint32_t *mapping=NULL;
    const size_t sizes[]={256,128,4096};
    r->enhanced_authored=true;
    for(unsigned step=0;step<3;step++){
        assert(dv_allocate(r,sizes[step]));
        if(step==1)assert(!memcmp(held,r->dv.buffers,sizeof(held)) && r->dv.mapped==mapping && r->dv.sampler==sampler);
        memcpy(held,r->dv.buffers,sizeof(held));mapping=r->dv.mapped;sampler=r->dv.sampler;
        GLint previous;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&previous);
        for(unsigned k=0;k<2;k++){
            glBindBuffer(GL_SHADER_STORAGE_BUFFER,held[k]);GLint64 capacity;
            glGetBufferParameteri64v(GL_SHADER_STORAGE_BUFFER,GL_BUFFER_SIZE,&capacity);assert(capacity>=(GLint64)sizes[step]);
        }
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,previous);
        r->dv.active=true;assert(dv_last_use(r));
        PFNGLCLIENTWAITSYNCPROC genuine=r->dv.wait_sync;
        r->dv.wait_sync=storage_timeout;dvbridge_render_dv_policy_cancel(r);
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_BUSY);
        assert(!dv_allocate(r,sizes[step]) && "Pending cancellation cannot recycle storage");
        for(unsigned k=0;k<3;k++)assert(glIsBuffer(held[k]));
        r->dv.wait_sync=genuine;assert(finish(r)==DVBRIDGE_DV_IDLE);
    }
    /* The AI allocation contract remains frame-owned while DV storage is idle. */
    r->enhanced_authored=false;assert(dv_allocate(r,128));
    GLuint owned[3];memcpy(owned,r->dv.buffers,sizeof(owned));assert(!r->dv.borrowed_storage);
    r->dv.active=true;assert(dv_last_use(r));dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    for(unsigned k=0;k<3;k++)assert(!glIsBuffer(owned[k]) && glIsBuffer(held[k]));
    r->enhanced_authored=true;assert(dv_allocate(r,256));
    assert(!memcmp(held,r->dv.buffers,sizeof(held)) && r->dv.mapped==mapping);
    r->dv.active=true;assert(dv_last_use(r));PFNGLCLIENTWAITSYNCPROC genuine=r->dv.wait_sync;
    r->dv.wait_sync=storage_timeout;dvbridge_renderer_destroy(r);
    assert(owner->lease && !owner->attached && dvbridge_retirement_owner_poll(owner)==DVBRIDGE_DV_BUSY);
    for(unsigned k=0;k<3;k++)assert(glIsBuffer(held[k]));
    owner->lease->dv.wait_sync=genuine;glFinish();
    assert(dvbridge_retirement_owner_poll(owner)==DVBRIDGE_DV_IDLE);
    for(unsigned k=0;k<3;k++)assert(!glIsBuffer(held[k]));
    assert(!glIsSampler(sampler) && dvbridge_retirement_owner_destroy(&owner));
    puts("PASS Adaptive storage: capacity/reuse, AI isolation, pending cancellation and deferred destruction");
}
static void adaptive_ordered_handoff(pl_gpu gpu,const struct pl_frame *frame,
    const AVDOVIMetadata *metadata,size_t bytes)
{
    const size_t size=3840u*2160u*4;unsigned char *reference[2]={malloc(size),malloc(size)},*actual=malloc(size);
    void *expected_metadata[2]={0};size_t expected_bytes[2]={0};assert(reference[0]&&reference[1]&&actual);
    AVDOVIMetadata *changed=av_memdup(metadata,bytes);assert(changed);
    AVDOVIDmData *l1=(AVDOVIDmData *)av_dovi_find_level(changed,1);assert(l1);
    l1->l1.max_pq=2800;l1->l1.avg_pq=1229;
    pl_fmt fmt=pl_find_named_fmt(gpu,"rgba8");pl_tex targets[2];unsigned fbos[2];
    for(unsigned i=0;i<2;i++){
        targets[i]=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(targets[i]);
        pl_opengl_unwrap(gpu,targets[i],NULL,NULL,&fbos[i]);
    }
    for(unsigned ordered=0;ordered<2;ordered++){
        struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
        struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
        if(ordered)r->reuse_authored_storage=true; /* Exercise the ordered contract on both drivers. */

        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_P3_D65}};
        for(unsigned i=0;i<2;i++){
            const AVDOVIMetadata *m=i?changed:metadata;struct dvbridge_identity id={71,83+i,1};
            assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,frame,m,bytes,i/60.0,i/60.0,
                (struct dvbridge_geometry){3840,2160,0,0,3840,2160},targets[i],false,NULL)==DVBRIDGE_DV_PENDING);
            assert(finish(r)==DVBRIDGE_DV_READY);
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
            if(!ordered){expected_bytes[i]=out->bytes;expected_metadata[i]=av_memdup(out->output_metadata,out->bytes);assert(expected_metadata[i]);}
            else assert(out->bytes==expected_bytes[i] && !memcmp(out->output_metadata,expected_metadata[i],out->bytes));
            assert(dvbridge_render_dv_policy_resolve(r,targets[i],fbos[i],false));
            uint64_t serial=out->resolve_serial;
            assert(dvbridge_render_dv_policy_commit(r,&id,targets[i],serial));
            if(!ordered && !i){
                const char *vendor=(const char *)glGetString(GL_VENDOR);
                assert(r->dv.ordered_handoff==(vendor && !strcmp(vendor,"Intel")) &&
                    "Only measured beneficial drivers may overlap Adaptive analysis");
            }
            if(!ordered)assert(finish(r)==DVBRIDGE_DV_IDLE);
            else if(!i){
                PFNGLCLIENTWAITSYNCPROC genuine=r->dv.wait_sync;r->dv.wait_sync=storage_timeout;
                assert(dvbridge_render_dv_policy_advance(r)==DVBRIDGE_DV_IDLE &&
                    "A committed resolve must hand off without a CPU final-fence wait");
                assert(r->retired_packed.active && !r->dv.active);
                r->retired_packed.wait_sync=genuine;
            }else{
                PFNGLCLIENTWAITSYNCPROC genuine=r->retired_packed.wait_sync;r->retired_packed.wait_sync=storage_timeout;
                assert(dvbridge_render_dv_policy_advance(r)==DVBRIDGE_DV_BUSY && "Only one retired transaction is allowed");
                r->retired_packed.wait_sync=genuine;
            }
        }
        glFinish();assert(finish(r)==DVBRIDGE_DV_IDLE);
        for(unsigned i=0;i<2;i++){
            glBindFramebuffer(GL_FRAMEBUFFER,fbos[i]);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,ordered?actual:reference[i]);
            glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
            if(ordered)assert(!memcmp(actual,reference[i],size) && "Ordered handoff must preserve both complete carriers");
        }
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    }
    assert(memcmp(reference[0],reference[1],size) && "The two graded frames must be distinguishable");
    for(unsigned i=0;i<2;i++){free(reference[i]);av_free(expected_metadata[i]);pl_tex_destroy(gpu,&targets[i]);}
    av_free(changed);free(actual);puts("PASS Adaptive ordered handoff: distinct carriers/RPUs and bounded final-fence retirement");
}

int main(void)
{
    assert(dvbridge_gl_patch && "Prepacked transport requires metadata-only patching");
    struct reference_gpu g=reference_gpu_create();
    adaptive_storage_ownership(g.gl->gpu);
    adaptive_guidance_equivalence(g.gl->gpu);
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3079;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    void *original=av_memdup(m,bytes);
    float pixels[16];for(unsigned i=0;i<16;i++)pixels[i]=i%4==3?1:dv_ideal_pq(500);
    pl_tex input=reference_texture(g.gl->gpu,2,2,pixels);
    struct pl_frame frame=reference_frame(input,2,2);
    struct dvbridge_policy p={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_identity id={1,7,1};struct dvbridge_geometry geometry={2,2,0,0,2,2};
    /* A constant authored scene must not acquire frame-dependent DM oscillation. */
    av_dovi_get_ext(m,0)->l1.max_pq=2498;av_dovi_get_ext(m,0)->l1.avg_pq=1229;
    for(unsigned preset=1;preset<2;preset++){
        uint16_t scene_l1[3]={0},scene_peak=0;
        for(unsigned step=0;step<3;step++){
            float level=dv_ideal_pq(step==1?100:500),sample[16];
            for(unsigned i=0;i<16;i++)sample[i]=i%4==3?1:level;
            pl_tex variable=reference_texture(g.gl->gpu,2,2,sample);
            struct pl_frame changing=reference_frame(variable,2,2);
            assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&changing,m,bytes,0,0,geometry)==DVBRIDGE_DV_PENDING);
            assert(finish(r)==DVBRIDGE_DV_READY);
            const struct dvbridge_dv_policy_output *ready=dvbridge_render_dv_policy_output(r);assert(ready);
            const struct dvbridge_dv_policy_snapshot *v=&ready->value;
            if(!step){memcpy(scene_l1,v->l1,sizeof(scene_l1));scene_peak=v->source_pq[1];}
            else assert(!memcmp(scene_l1,v->l1,sizeof(scene_l1)) && scene_peak==v->source_pq[1] &&
                "Stable authored guidance must produce stable display-management metadata");
            dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
            pl_tex_destroy(g.gl->gpu,&variable);
        }
    }
    memcpy(m,original,bytes);

    /* Under-conservative scene descriptors cannot hide a measured output peak. */
    av_dovi_get_color(m)->source_max_pq=2771;
    av_dovi_get_ext(m,0)->l1.max_pq=3080;
    float bright_pixels[16];for(unsigned i=0;i<16;i++)bright_pixels[i]=i%4==3?1:dv_ideal_pq(490);
    pl_tex bright_input=reference_texture(g.gl->gpu,2,2,bright_pixels);
    struct pl_frame bright_frame=reference_frame(bright_input,2,2);
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&bright_frame,m,bytes,0,0,geometry)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *bright_ready=dvbridge_render_dv_policy_output(r);assert(bright_ready);
    const struct dvbridge_dv_policy_snapshot *bright_meta=&bright_ready->value;
    assert(bright_meta->measured && bright_meta->source_pq[1]>=dv_wire_code(bright_meta->statistics[2]) &&
        "Declared output peak must cover accepted expanded pixels");
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
    pl_tex_destroy(g.gl->gpu,&bright_input);memcpy(m,original,bytes);
    /* Dark frames keep the graded scene metadata without lifting their pixels. */
    float protected_pixels[16];
    for(unsigned i=0;i<16;i++)protected_pixels[i]=i%4==3?1:dv_ideal_pq(1);
    pl_tex protected_input=reference_texture(g.gl->gpu,2,2,protected_pixels);
    struct pl_frame protected_frame=reference_frame(protected_input,2,2);
    for(unsigned preset=1;preset<2;preset++){

        size_t supplied=preset?bytes:m->ext_block_offset+m->num_ext_blocks*m->ext_block_size;
        assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&protected_frame,m,supplied,0,0,geometry)==DVBRIDGE_DV_PENDING);
        assert(finish(r)==DVBRIDGE_DV_READY);
        const struct dvbridge_dv_policy_output *protected_out=dvbridge_render_dv_policy_output(r);
        const AVDOVIMetadata *pair=protected_out->output_metadata;
        assert(dvbridge_metadata_bounds(pair,protected_out->bytes) && "Adding L5 must allocate storage beyond a compact source record");
        const AVDOVIDmData *source_l1=av_dovi_find_level(m,1),*output_l1=av_dovi_find_level(pair,1);
        assert(output_l1 && output_l1->l1.min_pq==source_l1->l1.min_pq &&
               output_l1->l1.max_pq>=source_l1->l1.max_pq && output_l1->l1.avg_pq>=source_l1->l1.avg_pq);
        float shadow_sample[4];reference_read(g.gl->gpu,protected_out->intermediate,0,0,1,1,shadow_sample);
        for(unsigned c=0;c<3;c++)assert(fabs(shadow_sample[c]-protected_pixels[c])*4096<=1);
        assert(av_dovi_find_level(pair,2) &&
               !memcmp(&av_dovi_find_level(pair,2)->l2,&av_dovi_find_level(m,2)->l2,sizeof(source_l1->l2)));
        assert(av_dovi_get_color(pair)->source_max_pq>=3079);
        dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
    }
    /* Optional CM4 fields retain their authored wire payload, not a second grade. */
    const unsigned lengths[]={10,12,13,19,25};
    for(unsigned i=0;i<5;i++){
        *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=8,
            .l8={.target_display_index=49,.trim_slope=2048,.trim_offset=2048,.trim_power=2048,
                 .trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=2048},
            .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=lengths[i],
            .dvbridge_original_bytes={49,0x80,0x08,0,0x80,0x08,0,0x80,0x08,0}};
        assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&protected_frame,m,bytes,0,0,geometry)==DVBRIDGE_DV_PENDING);
        assert(finish(r)==DVBRIDGE_DV_READY);
        const AVDOVIMetadata *pair=dvbridge_render_dv_policy_output(r)->output_metadata;
        assert(av_dovi_find_level(pair,8) &&
               !memcmp(av_dovi_find_level(pair,8),av_dovi_get_ext(m,1),sizeof(AVDOVIDmData)));
        dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
    }
    memcpy(m,original,bytes);
    pl_tex_destroy(g.gl->gpu,&protected_input);
    /* Keep effective L1 ordered when signed L3 narrows the authored range. */
    m->num_ext_blocks=3;
    av_dovi_get_ext(m,0)->l1.max_pq=3000;av_dovi_get_ext(m,0)->l1.avg_pq=2900;
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=3,.l3={2048,2028,2077},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5,
        .dvbridge_original_bytes={0x80,0x07,0xec,0x81,0xd0}};
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&frame,m,bytes,0,0,geometry)==DVBRIDGE_DV_PENDING);
    glFinish();uint32_t tight[16];memcpy(tight,r->dv.mapped,sizeof(tight));
    float before_stats[3]={0,4*2000.0f/4096,3000.0f/4096};
    float after_stats[3]={0,4*2020.0f/4096,3010.0f/4096};
    memcpy(tight,after_stats,sizeof(after_stats));memcpy(tight+12,before_stats,sizeof(before_stats));
    assert(dve_derive(r,tight));
    struct dvbridge_creative_plan effective_l3;
    assert(dvbridge_creative_resolve(&effective_l3,r->dv.output_metadata,r->dv.output_bytes,&p)!=DVBRIDGE_CREATIVE_INVALID &&
           "Measured deltas must not invert effective L1 through preserved L3 offsets");
    assert(effective_l3.analysis[1]>=2960 && effective_l3.analysis[2]>=2958 &&
           effective_l3.analysis[2]<=effective_l3.analysis[1]);
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);id.picture++;
    memcpy(m,original,bytes);
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&frame,m,bytes,0,0,geometry)==DVBRIDGE_DV_PENDING);
    assert(r->processing.selected_groups&CB1_PROCESSING_COLOUR);
    assert(!dvbridge_render_dv_policy_output(r) && !dvbridge_render_dv_policy_commit(r,&id,NULL,0));
    assert(finish(r)==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.output_generation==3 && out->value.sample_count==4 && out->value.measured);
    assert(out->value.l1[0]==0 && "Protected authored black must not move with a bright frame's measured minimum");
    assert(out->value.l1[1]>3079 && out->value.l1[2]>1463 && out->value.l1[2]<out->value.l1[1]);
    const AVDOVIMetadata *effective=out->output_metadata;
    assert(effective->num_ext_blocks==3 && av_dovi_find_level(effective,2) && !av_dovi_find_level(effective,3));
    pl_fmt fmt=pl_find_named_fmt(r->gpu,"rgba8");assert(fmt);
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(target);
    unsigned fbo=0;pl_opengl_unwrap(r->gpu,target,NULL,NULL,&fbo);assert(fbo);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    unsigned char before_overlay[4];glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,before_overlay);glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(dvbridge_render_dv_policy_commit(r,&id,target,dvbridge_render_dv_policy_output(r)->resolve_serial));
    assert(finish(r)==DVBRIDGE_DV_IDLE);
    struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
    struct cb1_dv_enhanced_plan committed_plan=r->enhanced_committed;
    float gui[4]={.8f,0,0,1};pl_tex overlay_texture=reference_texture(g.gl->gpu,1,1,gui);
    float lut[256*4];for(unsigned i=0;i<256;i++)for(unsigned j=0;j<4;j++)lut[4*i+j]=j==3?1:i/255.0f;
    pl_tex degamma=reference_texture(g.gl->gpu,256,1,lut),pq_lut=reference_texture(g.gl->gpu,256,1,lut);
    struct dvbridge_native_overlay overlay={.texture=overlay_texture,.degamma=degamma,
        .pq=pq_lut,.rect={0,0,2,2},.input_pq=true};
    id.picture++;
    dvbridge_renderer_set_overlay_visible(r,true);
    assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&frame,m,bytes,3.0/24,3.0/24,geometry,target,false,&overlay)==DVBRIDGE_DV_PENDING);
    GLsync analysis_fence=r->dv.fence;
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true));
    assert(r->dv.fence==analysis_fence && !r->dv.ready);
    struct dvbridge_native_overlay invalid_overlay=overlay;invalid_overlay.pq=NULL;
    assert(!dvbridge_render_dv_policy_update_overlay(r,&invalid_overlay,false));
    assert(r->overlay_visible && r->dv.overlay.pq==pq_lut);
    assert(finish(r)==DVBRIDGE_DV_READY);
    out=dvbridge_render_dv_policy_output(r);assert(out && out->value.sample_count==4);
    assert(!memcmp(out->value.l1,committed.l1,sizeof(committed.l1)));
    if(r->fragment_quad){
        /* The fused overlay must preserve the established composition/packing,
         * including flipped scanout, transparent edges and SDR GUI decoding. */
        unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
        for(unsigned alpha=0;alpha<2;alpha++)for(unsigned pq=0;pq<2;pq++)for(unsigned flip=0;flip<2;flip++){
            float a=alpha?.4f:1;
            pl_tex_destroy(r->gpu,&overlay_texture);
            overlay_texture=reference_texture(g.gl->gpu,1,1,(float[4]){.8f*a,0,0,a});
            r->dv.overlay.texture=overlay_texture;
            r->dv.overlay.input_pq=pq;
            pl_tex composed=dve_compose(r,out->intermediate,true);assert(composed);
            unsigned texture=pl_opengl_unwrap(r->gpu,composed,NULL,NULL,NULL);
            assert(dvbridge_gl_pack(r->dv.packer,texture,fbo,3840,2160,packets,count,flip));
            unsigned char expected[64],actual[64];
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,flip?2156:0,4,4,GL_RGBA,GL_UNSIGNED_BYTE,expected);
            glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);
            glBindFramebuffer(GL_FRAMEBUFFER,0);
            const GLenum caps[]={GL_BLEND,GL_DEPTH_TEST,GL_STENCIL_TEST,GL_SCISSOR_TEST,
                GL_DITHER,GL_CULL_FACE,GL_RASTERIZER_DISCARD,GL_SAMPLE_ALPHA_TO_COVERAGE,GL_SAMPLE_COVERAGE};
            bool hostile=true;
            for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){if(hostile)glEnable(caps[i]);else glDisable(caps[i]);}
            glColorMask(!hostile,!hostile,!hostile,!hostile);
            assert(dve_pack_overlay(r,out->intermediate,target,flip,packets,count,false));
            GLboolean mask[4];glGetBooleanv(GL_COLOR_WRITEMASK,mask);
            for(unsigned i=0;i<4;i++)assert(mask[i]==!hostile);
            for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){assert(glIsEnabled(caps[i])==hostile);glDisable(caps[i]);}
            glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,flip?2156:0,4,4,GL_RGBA,GL_UNSIGNED_BYTE,actual);
            glBindFramebuffer(GL_FRAMEBUFFER,0);
            if(memcmp(expected,actual,sizeof(expected))){
                fprintf(stderr,"overlay mismatch alpha=%u pq=%u flip=%u\n",alpha,pq,flip);
                for(unsigned i=0;i<16;i++)fprintf(stderr,"%u: %u,%u,%u,%u -> %u,%u,%u,%u\n",i,
                    expected[4*i],expected[4*i+1],expected[4*i+2],expected[4*i+3],
                    actual[4*i],actual[4*i+1],actual[4*i+2],actual[4*i+3]);
                assert(!"Fused overlay changed packed bytes");
            }
        }
        pl_tex_destroy(r->gpu,&overlay_texture);
        overlay_texture=reference_texture(g.gl->gpu,1,1,gui);r->dv.overlay.texture=overlay_texture;
        r->dv.overlay.input_pq=true;
    }
    /* Late GUI changes update composition/L5 without re-running video analysis. */
    const struct dvbridge_candidate *previous_candidate=r->pending;
    const pl_tex previous_intermediate=out->intermediate;
    uint16_t previous_l1[3];memcpy(previous_l1,out->value.l1,sizeof(previous_l1));
    overlay=r->dv.overlay;
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
    assert(!r->dv.enhanced_overlay && r->pending!=previous_candidate);
    assert(!memcmp(previous_l1,out->value.l1,sizeof(previous_l1)) && out->intermediate==previous_intermediate);
    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true));
    assert(r->dv.enhanced_overlay && r->dv.overlay.texture==overlay.texture);
    struct dvbridge_candidate *expected_overlay=dvbridge_prepare_output(r->context,out->output_metadata,
        out->bytes,3.0/24,(struct dvbridge_geometry){3840,2160,0,0,3840,2160},false,false);assert(expected_overlay);
    unsigned wanted_count,actual_count;
    const uint32_t *wanted_packets=dvbridge_packets(expected_overlay,&wanted_count);
    const uint32_t *actual_packets=dvbridge_packets(r->pending,&actual_count);
    assert(wanted_count==actual_count && !memcmp(wanted_packets,actual_packets,wanted_count*sizeof(*wanted_packets)));
    dvbridge_candidate_destroy(expected_overlay);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    assert(!dvbridge_render_dv_policy_update_overlay(r,NULL,false));
    unsigned char after_overlay[4];glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,after_overlay);glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(memcmp(before_overlay,after_overlay,3) && "Subtitles must appear after analysis");
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    pl_tex_destroy(g.gl->gpu,&overlay_texture);
    pl_tex_destroy(g.gl->gpu,&degamma);pl_tex_destroy(g.gl->gpu,&pq_lut);
    assert(committed.output_generation==3 && !memcmp(original,m,bytes));
    id.picture++;
    av_dovi_get_ext(m,0)->l1.max_pq=1000;av_dovi_get_ext(m,0)->l1.avg_pq=0;
    assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&frame,m,bytes,1.0/24,1.0/24,geometry,target,false,NULL)==DVBRIDGE_DV_PENDING);
    assert(!dvbridge_render_dv_policy_output(r));
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    assert(!memcmp(&committed_plan,&r->enhanced_committed,sizeof(committed_plan)));
    av_dovi_get_ext(m,0)->l1.max_pq=3079;av_dovi_get_ext(m,0)->l1.avg_pq=1463;
    struct dvbridge_dv_policy_snapshot after;assert(dvbridge_render_dv_policy_committed(r,&after));
    assert(!memcmp(&after,&committed,sizeof(after)));
    id.picture++;
    assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&frame,m,bytes,2.0/24,2.0/24,geometry,target,false,NULL)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    assert(dvbridge_render_dv_policy_commit(r,&id,target,dvbridge_render_dv_policy_output(r)->resolve_serial));
    assert(finish(r)==DVBRIDGE_DV_IDLE);
    /* Matched FEL reconstruction precedes the new expansion, exactly once. */
    av_dovi_get_header(m)->disable_residual_flag=0;
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(unsigned j=0;j<3;j++){mapping->nlq[j].nlq_offset=512;mapping->nlq[j].linear_deadzone_slope=1;}
    pl_tex el=reference_texture(g.gl->gpu,2,2,(float[16]){.75,.75,.75,1,.75,.75,.75,1,.75,.75,.75,1,.75,.75,.75,1});
    struct pl_frame enhancement=reference_frame(el,2,2);frame.enhancement_layer=&enhancement;id.picture++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&frame,m,bytes,.125,.125,geometry)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);
    assert(out && out->value.fel_reconstructed && av_dovi_get_header((AVDOVIMetadata *)out->output_metadata)->disable_residual_flag);
    float native[16],expanded[16];reference_read(g.gl->gpu,r->rgb,0,0,2,2,native);
    reference_read(g.gl->gpu,out->intermediate,0,0,2,2,expanded);
    for(unsigned i=0;i<4;i++){
        double rgb[3],wanted[3];
        for(unsigned j=0;j<3;j++)rgb[j]=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,native[4*i+j]);
        assert(cb1_dv_enhanced_pixel(&r->dv.enhanced_plan,rgb,wanted));
        for(unsigned j=0;j<3;j++)assert(fabs(expanded[4*i+j]-dv_ideal_pq(wanted[j]))*4096<=1);
    }
    uint32_t stale[16];memcpy(stale,r->dv.mapped,sizeof(stale));stale[6]++;
    assert(!dve_derive(r,stale));
    memcpy(stale,r->dv.mapped,sizeof(stale));stale[10]=0;assert(!dve_derive(r,stale));
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    pl_tex_destroy(g.gl->gpu,&el);
    frame.enhancement_layer=NULL;av_dovi_get_header(m)->disable_residual_flag=1;
    av_dovi_get_color(m)->source_max_pq=2710;id.picture++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&frame,m,bytes,.167,.167,geometry)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.output_generation==DVBRIDGE_SOURCE_METADATA && out->intermediate==r->rgb);
    assert(out->value.expansion_reason==CB1_DVE_SOURCE_BOUND && !out->value.measured);
    assert(out->bytes==bytes && !memcmp(m,out->output_metadata,bytes));
    reference_read(g.gl->gpu,r->rgb,0,0,2,2,native);
    reference_read(g.gl->gpu,out->intermediate,0,0,2,2,expanded);
    assert(!memcmp(native,expanded,sizeof(native)) && "A bound violation must retain every original pixel");
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    /* Source-bound identity retains native pixels but refreshes late L5 too. */
    m->num_ext_blocks=3;*av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=5,.l5={.left_offset=1}};
    dvbridge_renderer_set_overlay_visible(r,false);id.picture++;
    assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&frame,m,bytes,.25,.25,geometry,target,false,NULL)==DVBRIDGE_DV_PENDING);
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,true));
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.output_generation==DVBRIDGE_SOURCE_METADATA && out->intermediate==r->rgb);
    expected_overlay=dvbridge_prepare_output(r->context,m,bytes,.25,geometry,false,false);assert(expected_overlay);
    wanted_packets=dvbridge_packets(expected_overlay,&wanted_count);actual_packets=dvbridge_packets(r->pending,&actual_count);
    assert(wanted_count==actual_count && !memcmp(wanted_packets,actual_packets,wanted_count*sizeof(*wanted_packets)));
    dvbridge_candidate_destroy(expected_overlay);
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    /* Full-raster reconstruction stays linear until expansion. Compare its PQ
     * output and guarded identity against the canonical native renderer. */
    m->num_ext_blocks=2;av_dovi_get_color(m)->source_max_pq=3079;
    pl_tex full=reference_texture(g.gl->gpu,3840,2160,NULL);
    GLuint full_fbo;glGenFramebuffers(1,&full_fbo);glBindFramebuffer(GL_FRAMEBUFFER,full_fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
        pl_opengl_unwrap(r->gpu,full,NULL,NULL,NULL),0);
    glClearColor(dv_ideal_pq(500),dv_ideal_pq(250),dv_ideal_pq(100),1);glClear(GL_COLOR_BUFFER_BIT);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&full_fbo);
    float stripe[3840*4];for(unsigned i=0;i<3840;i++)for(unsigned j=0;j<4;j++)
        stripe[4*i+j]=j==3?1:dv_ideal_pq(10+(i*(j*17+11)%300));
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,full,NULL,NULL,NULL));
    for(unsigned row=0;row<3;row++)glTexSubImage2D(GL_TEXTURE_2D,0,0,row==2?2159:row*7,3840,1,GL_RGBA,GL_FLOAT,stripe);
    glBindTexture(GL_TEXTURE_2D,0);
    struct pl_frame full_frame=reference_frame(full,3840,2160);
    struct dvbridge_geometry full_geometry={3840,2160,0,0,3840,2160};
    struct dvbridge_renderer *canonical=dvbridge_renderer_create(g.gl->gpu);assert(canonical);
    assert(dvbridge_render_rgb(canonical,&full_frame,m,bytes,1,1,full_geometry));
    float canonical_pixel[4],result_pixel[4];reference_read(r->gpu,canonical->rgb,500,500,1,1,canonical_pixel);
    id.picture++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&full_frame,m,bytes,1,1,full_geometry)==DVBRIDGE_DV_PENDING);
    assert(r->reconstructed_color.transfer==PL_COLOR_TRC_LINEAR);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.output_generation==3 && out->value.container.transfer==PL_COLOR_TRC_PQ);
    exact_prepack(r,fbo,false);exact_prepack(r,fbo,true);
    double linear[3],wanted[3];
    for(unsigned j=0;j<3;j++)linear[j]=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,canonical_pixel[j]);
    assert(cb1_dv_enhanced_pixel(&r->dv.enhanced_plan,linear,wanted));
    reference_read(r->gpu,out->intermediate,500,500,1,1,result_pixel);
    for(unsigned j=0;j<3;j++){
        assert(fabs(result_pixel[j]-dv_ideal_pq(wanted[j]))*4096<=1);
    }
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    for(unsigned pq=0;pq<2;pq++)for(unsigned alpha=0;alpha<2;alpha++){
        float a=alpha?.4f:1;
        overlay_texture=reference_texture(r->gpu,1,1,(float[4]){.8f*a,.2f*a,.1f*a,a});
        degamma=reference_texture(r->gpu,256,1,lut);pq_lut=reference_texture(r->gpu,256,1,lut);
        overlay=(struct dvbridge_native_overlay){.texture=overlay_texture,.degamma=degamma,
            .pq=pq_lut,.rect={0,0,3840,48},.input_pq=pq};id.picture++;
        assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&full_frame,m,bytes,1,1,full_geometry,target,false,&overlay)==DVBRIDGE_DV_PENDING);
        assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
        exact_prepack(r,fbo,false);exact_prepack(r,fbo,true);
        /* GUI removal keeps the prepared video and composes at resolve. */
        assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
        dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
        pl_tex_destroy(r->gpu,&overlay_texture);pl_tex_destroy(r->gpu,&degamma);pl_tex_destroy(r->gpu,&pq_lut);
    }
    /* ROI clearing must ignore inherited rasterizer state and restore it. */
    glBindFramebuffer(GL_FRAMEBUFFER,r->enhanced_packed_fbo);
    glClearBufferfv(GL_COLOR,0,(float[4]){1,1,1,1});
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    glEnable(GL_RASTERIZER_DISCARD);glEnable(GL_DITHER);
    assert(dve_clear_rows(r->enhanced_packed_fbo,273,1883));
    assert(glIsEnabled(GL_RASTERIZER_DISCARD) && glIsEnabled(GL_DITHER));
    glDisable(GL_RASTERIZER_DISCARD);glDisable(GL_DITHER);
    unsigned char black[4];glBindFramebuffer(GL_FRAMEBUFFER,r->enhanced_packed_fbo);
    glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,black);glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(black[0]==128 && black[1]==16 && black[2]==0 && black[3]==255 &&
        "Excluded rows must contain exact tunnel black under hostile GL state");
    /* Packed Signature needs no expanded 4K cache. */
    id.picture++;
    m->num_ext_blocks=3;*av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=5,.l5={.top_offset=272,.bottom_offset=276}};
    const size_t packed_bytes=3840u*2160u*4;
    unsigned char *cached=malloc(packed_bytes),*lean=malloc(packed_bytes);assert(cached && lean);
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&full_frame,m,bytes,1,1,full_geometry)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,cached);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&full_frame,m,bytes,1,1,full_geometry,target,false,NULL)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(r->dv.prepacked && !out->intermediate && !dvbridge_render_texture(r));
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,true));
    GLsync materialized=r->dv.fence;
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
    assert(r->dv.fence==materialized && "GUI changes must retain materialized video");
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,lean);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    assert(!memcmp(cached,lean,packed_bytes) && "Omitting the unused cache must preserve every transport byte");
    free(cached);free(lean);
    dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
    m->num_ext_blocks=2;

    av_dovi_get_color(m)->source_max_pq=2500;id.picture++;
    assert(dvbridge_render_dv_policy_prepare(r,&p,&id,&full_frame,m,bytes,2,2,full_geometry)==DVBRIDGE_DV_PENDING);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.output_generation==DVBRIDGE_SOURCE_METADATA && out->value.container.transfer==PL_COLOR_TRC_PQ);
    assert(out->bytes==bytes && !memcmp(out->output_metadata,m,bytes));
    assert(dvbridge_render_rgb(canonical,&full_frame,m,bytes,2,2,full_geometry));
    reference_read(r->gpu,canonical->rgb,500,500,1,1,canonical_pixel);
    reference_read(r->gpu,out->intermediate,500,500,1,1,result_pixel);
    for(unsigned j=0;j<3;j++)assert(fabs(result_pixel[j]-canonical_pixel[j])*4096<=1);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    assert(dvbridge_render_dv_policy_commit(r,&id,target,out->resolve_serial));
    assert(finish(r)==DVBRIDGE_DV_IDLE);
    /* A native identity scene must not leak its PQ domain into the next
     * expanding scene, nor reuse the wrong compute program. */
    for(unsigned active=0;active<2;active++){
        m->num_ext_blocks=active?2:1;
        av_dovi_get_color(m)->source_max_pq=active?3079:3696;id.picture++;
        enum dvbridge_dv_policy_status state=dvbridge_render_dv_policy_prepare(r,&p,&id,&full_frame,m,bytes,3+active,3+active,full_geometry);
        assert(state==(active?DVBRIDGE_DV_PENDING:DVBRIDGE_DV_READY));
        assert(r->reconstructed_color.transfer==(active?PL_COLOR_TRC_LINEAR:PL_COLOR_TRC_PQ));
        assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
        assert(out->value.output_generation==(active?3:DVBRIDGE_SOURCE_METADATA));
        assert(out->value.container.transfer==PL_COLOR_TRC_PQ);
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
        assert(dvbridge_render_dv_policy_commit(r,&id,target,out->resolve_serial));
        assert(finish(r)==DVBRIDGE_DV_IDLE);
    }
    if(r->fragment_quad){
        /* B must retain the whole-frame guard without materializing a PQ cache. */
        for(unsigned precision=0;precision<2;precision++){
        p.adaptive=precision?DVBRIDGE_ADAPTIVE_B_FP16:DVBRIDGE_ADAPTIVE_B_FP32;

        av_dovi_get_color(m)->source_max_pq=2500;id.picture++;
        assert(dvbridge_render_dv_policy_prepare_packed(r,&p,&id,&full_frame,m,bytes,5,5,full_geometry,target,false,NULL)==DVBRIDGE_DV_PENDING);
        assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);
        assert(out && out->value.expansion_reason==CB1_DVE_SOURCE_BOUND && !out->intermediate);
        assert(out->bytes==bytes && !memcmp(out->output_metadata,m,bytes));
        size_t size=3840u*2160u*4;
        uint8_t *expected=malloc(size),*actual=malloc(size);assert(expected && actual);
        assert(dve_native_pq(r));
        unsigned count;const uint32_t *packets=dvbridge_packets(r->pending,&count);
        assert(dvbridge_gl_pack(r->dv.packer,pl_opengl_unwrap(r->gpu,r->enhanced_rgb,NULL,NULL,NULL),fbo,3840,2160,packets,count,false));
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,expected);
        glBindFramebuffer(GL_FRAMEBUFFER,0);
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,actual);
        glBindFramebuffer(GL_FRAMEBUFFER,0);
        assert(!memcmp(expected,actual,size) && "Fused B recovery must preserve every transport byte");
        free(expected);free(actual);
        dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
        }
    }
    dvbridge_renderer_destroy(canonical);pl_tex_destroy(r->gpu,&full);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    pl_tex_destroy(g.gl->gpu,&input);pl_tex_destroy(g.gl->gpu,&target);av_free(m);av_free(original);
    reference_gpu_destroy(&g);puts("PASS Pending RGB/packed, minimal fresh metadata, successful commit and cancelled-frame isolation");
}
