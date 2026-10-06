/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
/* Exercise production retirement, replacing only its external sync edge.
 * Include the owning unit to access private state without a test API. */
#define CB1_TEST_LEGACY_ANALYSIS 1
#include "../src/dvbridge_render.c"
#include <sys/wait.h>
#include <unistd.h>
#include <time.h>
#include <libavutil/buffer.h>

#ifdef DVBRIDGE_DV_POLICY_API
static GLenum completion=GL_TIMEOUT_EXPIRED;
static unsigned checks,deletes;
static GLenum fake_wait(GLsync sync,GLbitfield flags,GLuint64 timeout)
{ assert(sync && !flags && !timeout);++checks;return completion; }
static void fake_delete(GLsync sync) { assert(sync);++deletes; }
static GLsync failed_fence(GLenum condition,GLbitfield flags)
{ assert(condition==GL_SYNC_GPU_COMMANDS_COMPLETE && !flags);return NULL; }

static void pending(struct dvbridge_renderer *r)
{
    r->dv.active=true;r->dv.retiring=false;r->dv.quarantined=false;
    r->dv.fence=(GLsync)(uintptr_t)1;
    r->dv.wait_sync=fake_wait;r->dv.delete_sync=fake_delete;
}
static void quarantine_process(void)
{
    /* A process-owned fake GPU lease cannot become reusable recovery. The
     * deliberate quarantined allocation dies at process teardown, not free. */
    pid_t child=fork();assert(child>=0);
    if(!child){
        struct dvbridge_retirement_owner *o=calloc(1,sizeof(*o));
        struct dvbridge_renderer *r=calloc(1,sizeof(*r));assert(o&&r);
        o->attached=r;r->owner=o;pending(r);completion=GL_WAIT_FAILED;
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_FAILED);
        assert(!dvbridge_render_dv_policy_output(r) && !deletes);
        dvbridge_renderer_reset(r);
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_FAILED);
        dvbridge_renderer_destroy(r);
        assert(o->lease && !o->attached);
        assert(dvbridge_retirement_owner_poll(o)==DVBRIDGE_DV_FAILED);
        assert(!dvbridge_retirement_owner_destroy(&o));
        assert(!dvbridge_renderer_create_with_owner(o) && !deletes);
        puts("PASS WAIT_FAILED/reset/destroy quarantine held until process teardown");fflush(stdout);
        _Exit(0);
    }
    int result;assert(waitpid(child,&result,0)==child && WIFEXITED(result) && !WEXITSTATUS(result));
}
static void failed_fence_process(void)
{
    pid_t child=fork();assert(child>=0);
    if(!child){
        struct reference_gpu g=reference_gpu_create();
        struct dvbridge_retirement_owner *o=dvbridge_retirement_owner_create(g.gl->gpu);assert(o);
        struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(o);assert(r && dv_allocate(r));
        r->dv.active=true;r->dv.fence_sync=failed_fence;
        assert(!dv_last_use(r) && r->dv.quarantined);
        dvbridge_render_dv_policy_cancel(r);
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_FAILED && !dvbridge_render_dv_policy_output(r));
        dvbridge_renderer_reset(r);dvbridge_renderer_destroy(r);
        assert(o->lease && !dvbridge_retirement_owner_destroy(&o));
        assert(dvbridge_retirement_owner_poll(o)==DVBRIDGE_DV_FAILED && !dvbridge_renderer_create_with_owner(o));
        puts("PASS injected failed fence creation quarantines real allocated resources through reset/destroy; no reusable recovery");fflush(stdout);
        _Exit(0); /* Process teardown is the only claimed quarantine recovery. */
    }
    int result;assert(waitpid(child,&result,0)==child && WIFEXITED(result) && !WEXITSTATUS(result));
}
static void state_probe(struct dvbridge_renderer *r)
{
    assert(dv_allocate(r));
    const GLuint analysis_program=r->dv.programs[0];
    struct dvbridge_gl_packer *transport_packer=r->dv.packer;
    r->dv.active=true;
    r->dv.output.value.identity=(struct dvbridge_identity){1,2,3};
    memcpy(r->dv.output.value.margins,(unsigned[4]){0,3838,0,2158},sizeof(unsigned)*4);
    GLuint buffers[3],sampler,program=dv_compute_program();assert(program);
    glGenBuffers(3,buffers);glGenSamplers(1,&sampler);
    for(unsigned i=0;i<3;i++){
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,buffers[i]);
        glBufferData(GL_SHADER_STORAGE_BUFFER,1024,NULL,GL_STREAM_DRAW);
        glBindBufferRange(GL_SHADER_STORAGE_BUFFER,i,buffers[i],256,512);
    }
    pl_tex foreign=reference_texture(r->gpu,2,2,(float[16]){.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1});
    GLuint texture=pl_opengl_unwrap(r->gpu,foreign,NULL,NULL,NULL);
    glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);glBindSampler(0,sampler);
    glActiveTexture(GL_TEXTURE5);glUseProgram(program);
    assert(glGetError()==GL_NO_ERROR && dv_analyze(r));
    GLint value;glGetIntegerv(GL_CURRENT_PROGRAM,&value);assert((GLuint)value==program);
    glGetIntegerv(GL_ACTIVE_TEXTURE,&value);assert(value==GL_TEXTURE5);
    glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&value);assert((GLuint)value==texture);
    glGetIntegerv(GL_SAMPLER_BINDING,&value);assert((GLuint)value==sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&value);assert((GLuint)value==buffers[2]);
    for(unsigned i=0;i<3;i++){
        GLint64 offset,size;glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,i,&value);assert((GLuint)value==buffers[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,i,&offset);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,i,&size);
        assert(offset==256 && size==512);
    }
    glUseProgram(0);glBindSampler(0,0);glBindTexture(GL_TEXTURE_2D,0);
    for(unsigned i=0;i<3;i++)glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,0);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,0);
    dvbridge_render_dv_policy_cancel(r);
    enum dvbridge_dv_policy_status status=DVBRIDGE_DV_BUSY;
    for(unsigned i=0;i<10000 && status==DVBRIDGE_DV_BUSY;i++){
        status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(status==DVBRIDGE_DV_IDLE && glIsTexture(texture));
    /* Completed pictures retain immutable programs, not frame-owned storage. */
    assert(glIsProgram(analysis_program));
    assert(!r->dv.active && !r->dv.mapped && !r->dv.buffers[2]);
    assert(dv_allocate(r) && r->dv.programs[0]==analysis_program &&
           r->dv.packer==transport_packer);
    r->dv.active=true;
    assert(dv_last_use(r));
    dvbridge_render_dv_policy_cancel(r);
    do {
        status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    } while(status==DVBRIDGE_DV_BUSY);
    assert(status==DVBRIDGE_DV_IDLE && glIsProgram(analysis_program));
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);metadata->num_ext_blocks=1;
    av_dovi_get_ext(metadata,0)->level=1;av_dovi_get_ext(metadata,0)->l1.max_pq=3079;av_dovi_get_ext(metadata,0)->l1.avg_pq=1667;
    struct pl_frame source=reference_frame(foreign,2,2);
    struct dvbridge_renderer *baseline=dvbridge_renderer_create(r->gpu);assert(baseline);
    struct dvbridge_hdr10_session session;assert(dvbridge_hdr10_session_init(&session,metadata,bytes));
    for(unsigned basic=0;basic<2;basic++){
        float expected[16],actual[16];struct dvbridge_geometry geometry={2,2,0,0,2,2};
        assert(basic?dvbridge_render_hdr10_rgb(baseline,&session,&source,metadata,bytes,0,0,geometry):
                     dvbridge_render_rgb(baseline,&source,metadata,bytes,0,0,geometry));
        reference_read(r->gpu,dvbridge_render_texture(baseline),0,0,2,2,expected);
        assert(basic?dvbridge_render_hdr10_rgb(r,&session,&source,metadata,bytes,0,0,geometry):
                     dvbridge_render_rgb(r,&source,metadata,bytes,0,0,geometry));
        reference_read(r->gpu,dvbridge_render_texture(r),0,0,2,2,actual);
        assert(!memcmp(expected,actual,sizeof(expected)));
        assert(dvbridge_render_commit(r) && dvbridge_render_commit(baseline));
    }
    dvbridge_renderer_destroy(baseline);av_free(metadata);
    glDeleteBuffers(3,buffers);glDeleteSamplers(1,&sampler);glDeleteProgram(program);pl_tex_destroy(r->gpu,&foreign);
    puts("PASS genuine analysis state isolation, foreign texture ownership, next native/Basic bit-exact fresh-renderer control");
}
struct imported_handle { GLuint texture;unsigned *released; };
static void import_release(void *opaque,uint8_t *data)
{
    struct imported_handle *h=opaque;assert(data==(uint8_t *)h && glIsTexture(h->texture));
    glDeleteTextures(1,&h->texture);++*h->released;av_free(h);
}
static enum dvbridge_dv_policy_status complete(struct dvbridge_renderer *r);
static void imported_lifetime(struct reference_gpu *g)
{
    unsigned released=0;struct imported_handle *handle=av_mallocz(sizeof(*handle));assert(handle);
    handle->released=&released;glGenTextures(1,&handle->texture);GLuint texture=handle->texture;
    glBindTexture(GL_TEXTURE_2D,texture);glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA32F,2,2);
    float pixels[16]={.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1};
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,2,2,GL_RGBA,GL_FLOAT,pixels);glBindTexture(GL_TEXTURE_2D,0);
    AVBufferRef *decoder=av_buffer_create((uint8_t *)handle,sizeof(*handle),import_release,handle,0);assert(decoder);
    AVBufferRef *caller=av_buffer_ref(decoder);assert(caller);
    pl_tex wrapped=pl_opengl_wrap(g->gl->gpu,pl_opengl_wrap_params(.texture=texture,.width=2,.height=2,.iformat=GL_RGBA32F));assert(wrapped);
    struct pl_frame source=reference_frame(wrapped,2,2);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);metadata->num_ext_blocks=1;
    av_dovi_get_ext(metadata,0)->level=1;av_dovi_get_ext(metadata,0)->l1.max_pq=3079;av_dovi_get_ext(metadata,0)->l1.avg_pq=1667;
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g->gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    struct dvbridge_policy policy=reference_policy();policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;
    struct dvbridge_identity identity={1,7,1};
    assert(dvbridge_render_dv_policy_prepare(r,&policy,&identity,&source,metadata,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2})==DVBRIDGE_DV_READY);
    av_buffer_unref(&decoder);assert(!released && glIsTexture(texture));
    assert(complete(r)==DVBRIDGE_DV_READY);
    pl_fmt format=pl_find_named_fmt(g->gl->gpu,"rgba8");assert(format);
    pl_tex target=pl_tex_create(g->gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=format,.renderable=true));assert(target);
    GLuint framebuffer=0;
    assert(pl_opengl_unwrap(g->gl->gpu,target,NULL,NULL,&framebuffer) && framebuffer);
    assert(dvbridge_render_dv_policy_resolve(r,target,framebuffer,false));
    const uint64_t serial=dvbridge_render_dv_policy_output(r)->resolve_serial;
    assert(dvbridge_render_dv_policy_commit(r,&identity,target,serial));
    /* Actual renderer commands were submitted. Hold their genuine fence but
     * inject TIMEOUT at the external completion edge for deterministic checks. */
    PFNGLCLIENTWAITSYNCPROC genuine=r->dv.wait_sync;r->dv.wait_sync=fake_wait;completion=GL_TIMEOUT_EXPIRED;
    dvbridge_renderer_destroy(r);assert(owner->lease && !released && glIsTexture(texture));
    struct dvbridge_dv_policy_snapshot committed;
    assert(glIsFramebuffer(framebuffer) && dvbridge_render_dv_policy_committed(owner->lease,&committed));
    assert(committed.final_target==target && committed.final_framebuffer==framebuffer);
    assert(dvbridge_retirement_owner_poll(owner)==DVBRIDGE_DV_BUSY && !released);
    assert(glIsFramebuffer(framebuffer));
    owner->lease->dv.wait_sync=genuine;enum dvbridge_dv_policy_status status=DVBRIDGE_DV_BUSY;
    for(unsigned i=0;i<10000 && status==DVBRIDGE_DV_BUSY;i++){
        status=dvbridge_retirement_owner_poll(owner);
        if(status==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(status==DVBRIDGE_DV_IDLE && !released && glIsTexture(texture));
    assert(dvbridge_retirement_owner_destroy(&owner));
    assert(glIsFramebuffer(framebuffer));pl_tex_destroy(g->gl->gpu,&target);
    assert(!glIsFramebuffer(framebuffer));
    pl_tex_destroy(g->gl->gpu,&wrapped);assert(glIsTexture(texture));
    av_buffer_unref(&caller);assert(released==1 && !glIsTexture(texture));av_free(metadata);
    puts("PASS caller-retained AVBufferRef foreign GL import survives unsignaled renderer destruction; release only after genuine last-use fence");
}
static enum dvbridge_dv_policy_status complete(struct dvbridge_renderer *r)
{
    enum dvbridge_dv_policy_status status=DVBRIDGE_DV_PENDING;
    for(unsigned i=0;i<10000 && (status==DVBRIDGE_DV_PENDING || status==DVBRIDGE_DV_BUSY);i++){
        status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_PENDING || status==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    return status;
}
static void temporal_probe(struct dvbridge_renderer *r)
{
    /* Isolate initial packet numbering from the prior native/Basic control's
     * correctly shared serializer history. Reset preserves resolve serials. */
    dvbridge_renderer_reset(r);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);metadata->num_ext_blocks=1;
    AVDOVIDmData *l1=av_dovi_get_ext(metadata,0);l1->level=1;l1->l1.max_pq=3079;l1->l1.avg_pq=1667;
    pl_tex input=reference_texture(r->gpu,2,2,(float[16]){.2,.2,.2,1,.4,.4,.4,1,.6,.6,.6,1,.8,.8,.8,1});
    struct pl_frame source=reference_frame(input,2,2);
    pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE);assert(fmt);
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(target);
    struct dvbridge_policy policy=reference_policy();policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;
    struct dvbridge_identity identity={1,7,1};uint64_t previous_serial=r->resolve_serial;
    unsigned packet_ids[5]={0,17,34,34,0},refresh[5]={1,0,1,1,1};
    for(unsigned step=0;step<5;step++){
        if(step==1){identity.picture=8;l1->l1.avg_pq=2771;}
        if(step==2){identity.revision=policy.revision=2;policy.enhancement=DVBRIDGE_ENHANCEMENT_INTENSE;
            policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;policy.tv.peak_nits=1500.25;
            metadata->num_ext_blocks=2;
            *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=8,
                .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=10};}
        if(step==3){identity.revision=policy.revision=3;policy.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;}
        if(step==4){dvbridge_renderer_reset(r);struct dvbridge_dv_policy_snapshot absent;
            assert(!dvbridge_render_dv_policy_committed(r,&absent));identity=(struct dvbridge_identity){2,1,4};policy.revision=4;}
        assert(dvbridge_render_dv_policy_prepare(r,&policy,&identity,&source,metadata,bytes,step? .04:0,step? .04:0,(struct dvbridge_geometry){2,2,0,0,2,2})==DVBRIDGE_DV_READY);
        assert(dvbridge_render_dv_policy_output(r) && complete(r)==DVBRIDGE_DV_READY);
        const struct dvbridge_dv_policy_output *output=dvbridge_render_dv_policy_output(r);assert(output);
        assert(output->value.source_cm_version==(step>=2?40:29));
        assert(output->value.nominal_max_nits==(step>=2?1500.25:1500));
        unsigned count;const uint32_t *packet=dvbridge_packets(output->candidate,&count);
        fprintf(stderr,"TEMPORAL step=%u actual_id=%u actual_refresh=%u expected_id=%u expected_refresh=%u\n",step,packet[1],packet[6],packet_ids[step],refresh[step]);
        assert(count==1 && packet[1]==packet_ids[step] && packet[6]==refresh[step]);
        if(step==3){
            struct dvbridge_dv_policy_snapshot before;assert(dvbridge_render_dv_policy_committed(r,&before));
            assert(!dvbridge_render_dv_policy_resolve(r,NULL,0,false));
            struct dvbridge_dv_policy_snapshot after;assert(dvbridge_render_dv_policy_committed(r,&after));
            assert(!memcmp(&before,&after,sizeof(before)) && !dvbridge_render_dv_policy_output(r));
            assert(complete(r)==DVBRIDGE_DV_IDLE);
            assert(dvbridge_render_dv_policy_prepare(r,&policy,&identity,&source,metadata,bytes,.04,.04,(struct dvbridge_geometry){2,2,0,0,2,2})==DVBRIDGE_DV_READY);
            assert(complete(r)==DVBRIDGE_DV_READY);output=dvbridge_render_dv_policy_output(r);
            packet=dvbridge_packets(output->candidate,&count);assert(packet[1]==34 && packet[6]==1);
        }
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_READY);
        unsigned target_framebuffer;assert(pl_opengl_unwrap(r->gpu,target,NULL,NULL,&target_framebuffer));
        assert(dvbridge_render_dv_policy_resolve(r,target,target_framebuffer,false));
        uint64_t captured=dvbridge_render_dv_policy_output(r)->resolve_serial;assert(captured>previous_serial);
        /* Actual test caller submission succeeds before the captured receipt is
         * acknowledged. It does not manufacture a Kodi/scanout receipt. */
        glFlush();assert(glGetError()==GL_NO_ERROR);
        assert(dvbridge_render_dv_policy_commit(r,&identity,target,captured));previous_serial=captured;
        assert(complete(r)==DVBRIDGE_DV_IDLE && glIsTexture(pl_opengl_unwrap(r->gpu,target,NULL,NULL,NULL)));
        struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
        assert(dvbridge_identity_equal(&committed.identity,&identity) && committed.final_target==target);
        printf("PASS genuine temporal step=%u packet_id=%u refresh=%u source_cm=%u serial=%llu\n",step,packet_ids[step],refresh[step],committed.source_cm_version,(unsigned long long)captured);
    }
    pl_tex_destroy(r->gpu,&target);pl_tex_destroy(r->gpu,&input);av_free(metadata);dvbridge_renderer_reset(r);
}
static void derive_record(struct dvbridge_renderer *r,const uint32_t record[12],bool valid)
{
    size_t bytes;r->dv.source_metadata=task3_fixture(&bytes);assert(r->dv.source_metadata);
    r->dv.active=true;r->dv.groups=record[3];
    r->dv.output.value=(struct dvbridge_dv_policy_snapshot){.identity={1,7,1},.nominal_max_nits=1500,
        .output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL};
    bool accepted=dv_derive(r,record);
    fprintf(stderr,"CONSTANT-RECORD min=%08x sum=%08x max=%08x groups=%u accepted=%d expected=%d\n",record[0],record[1],record[2],record[3],accepted,valid);
    assert(accepted==valid);
    if(valid){
        float raw[3];memcpy(raw,record,sizeof(raw));
        double selected=raw[0]==raw[2]?raw[0]:(double)raw[1]/record[3];
        assert(r->dv.output.value.statistics[1]==floor(selected*100000+.5)/100000);
        if(raw[0]==raw[2]){
            assert(fabs((double)raw[1]/record[3]-raw[0])<=1e-6);
            assert(r->dv.output.value.statistics[0]==r->dv.output.value.statistics[1] &&
                   r->dv.output.value.statistics[1]==r->dv.output.value.statistics[2]);
            assert(r->dv.output.value.l1[0]==r->dv.output.value.l1[1] && r->dv.output.value.l1[1]==r->dv.output.value.l1[2]);
        }
        fprintf(stderr,"CONSTANT-MEAN raw_CPU=%.17g selected=%.17g\n",(double)raw[1]/record[3],selected);
    }else assert(!r->pending && !r->dv.output_metadata);
    dvbridge_render_dv_policy_cancel(r);assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
}
static void constant_validation(struct dvbridge_renderer *r)
{
    /* Independent authored tree records, including raw means on both sides.
     * No production helper computes these expectations. Odd partial count12. */
    const uint32_t cases[][3]={
        {0x3f000000u,3u,0x3fc00000u},{0x3f000000u,129u,0x42810000u},
        {0x3f000000u,2073600u,0x497d2000u},{0x3f000000u,12u,0x40c00000u},
        {0x3f333333u,3u,0x40066666u},{0x3f333333u,129u,0x42b49999u},
        {0x3f333333u,2073600u,0x49b13000u},{0x3f333333u,12u,0x41066666u},
        {0x3f333335u,3u,0x40066668u},{0x3f333335u,129u,0x42b4999bu},
        {0x3f333335u,2073600u,0x49b13002u},{0x3f333335u,12u,0x41066668u},
        {0x3f333333u,528u,0x43b8cccdu},{0x3f333333u,581u,0x43cb5999u},
        {0,2073600u,0},{0x3f800000u,2073600u,0x49fd2000u},
        {0x3c800000u,3u,0x3d400000u}}; /* .015625*100000=1562.5, exact upper tie. */
    for(unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++){
        uint32_t record[12]={cases[i][0],cases[i][2],cases[i][0],cases[i][1],1,0,7,0,1,0,1,0};
        derive_record(r,record,true);
        record[1]++;derive_record(r,record,false);
    }
    const uint32_t malformed[][2]={{0,0x7fc00000},{1,0x7f800000},{2,0xff800000},
        {1,0x3f000000},{0,0xbf000000},{2,0x40000000},{3,0},{3,2073601},
        {4,2},{5,1},{6,8},{7,1},{8,2},{9,1},{10,0},{10,2},{11,1}};
    for(unsigned i=0;i<sizeof(malformed)/sizeof(*malformed);i++){
        uint32_t record[12]={0x3f333333,0x40066666,0x3f333333,3,1,0,7,0,1,0,1,0};
        record[malformed[i][0]]=malformed[i][1];derive_record(r,record,false);
    }
    uint32_t record[12]={0x3ecccccd,0x3fc00000,0x3f19999a,3,1,0,7,0,1,0,1,0};
    derive_record(r,record,true);record[1]=0x3f000000;derive_record(r,record,false);
    record[1]=0x40000000;derive_record(r,record,false);
    puts("PASS exact constant tree consistency, raw/selected mean, corruption and unchanged nonconstant ordering");
}
static void constant_probe(struct dvbridge_renderer *r,bool unresolved_constant)
{
    size_t bytes;r->dv.source_metadata=task3_fixture(&bytes);assert(r->dv.source_metadata);
    void *copy=av_memdup(r->dv.source_metadata,bytes);assert(copy);
    r->dv.active=true;r->dv.groups=3;
    r->dv.output.value=(struct dvbridge_dv_policy_snapshot){.identity={1,7,1},.nominal_max_nits=1500,
        .output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL};
    float q=unresolved_constant?.7f:.5f;
    double wanted=unresolved_constant?.7:.5;
    unsigned wanted_code=unresolved_constant?2867:2048;
    float values[3]={q,q*3,q};
    uint32_t record[12]={0,0,0,3,1,0,7,0,1,0,1,0};memcpy(record,values,sizeof(values));
    assert(dv_derive(r,record));
    const struct dvbridge_dv_policy_snapshot *v=&r->dv.output.value;
    assert(v->statistics[0]==wanted && v->statistics[1]==wanted && v->statistics[2]==wanted);
    assert(v->l1[0]==wanted_code && v->l1[1]==wanted_code && v->l1[2]==wanted_code);
    assert(v->source_pq[0]==0 && v->source_pq[1]==3261 && !v->measured && !v->max_cll && !v->max_fall);
    assert(!memcmp(copy,r->dv.source_metadata,bytes));av_free(copy);
    assert(r->dv.output_metadata->num_ext_blocks==2 && av_dovi_get_ext(r->dv.output_metadata,0)->level==1 && av_dovi_get_ext(r->dv.output_metadata,1)->level==5);
    r->dv.ready=r->ready=true;r->dv.output.value.resolved=true;
    pl_tex surface=(pl_tex)(uintptr_t)17;r->dv.output.value.final_target=surface;
    r->resolve_serial=r->dv.output.resolve_serial=7;
    struct dvbridge_identity wrong={1,8,1},right={1,7,1};
    assert(!dvbridge_render_dv_policy_commit(r,&wrong,surface,7));
    assert(!dvbridge_render_dv_policy_commit(r,&right,(pl_tex)(uintptr_t)19,7));
    assert(!dvbridge_render_dv_policy_commit(r,&right,surface,6));
    assert(!dvbridge_render_dv_policy_commit(r,&right,surface,0));
    assert(!r->dv_has_committed && r->pending);
    assert(dvbridge_render_dv_policy_commit(r,&right,surface,7));
    assert(!dvbridge_render_dv_policy_commit(r,&right,surface,7));
    struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
    assert(committed.final_target==surface && committed.statistics[0]==wanted);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    dvbridge_renderer_reset(r);
    assert(!dvbridge_render_dv_policy_committed(r,&committed) && r->resolve_serial==7);
    puts("PASS literal true constant equal statistics/codes and immutable source");
}
#endif

int main(int argc,char **argv)
{
#ifndef DVBRIDGE_DV_POLICY_API
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;av_dovi_get_ext(m,0)->level=1;
    av_dovi_get_ext(m,0)->l1.max_pq=3079;av_dovi_get_ext(m,0)->l1.avg_pq=1667;
    struct dvbridge_policy p=reference_policy();p.mode=DVBRIDGE_MODE_ENHANCED_DV;
    p.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;
    struct dvbridge_color color;struct pl_color_space nominal;struct dvbridge_hdr10_metadata signal;
    assert(dvbridge_reference_map(&color,&nominal,&signal,&p,m,bytes,false));
    av_free(m);
#else
    if(argc==1){quarantine_process();failed_fence_process();}
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    assert(!dvbridge_retirement_owner_destroy(&owner));
    assert(!dvbridge_renderer_create_with_owner(owner));
    if(argc==1){state_probe(r);temporal_probe(r);}
    if(argc==2 && !strncmp(argv[1],"tree-",5)){
        bool larger=strstr(argv[1],"581"),corrupt=strstr(argv[1],"corrupt");
        uint32_t sum=larger?(corrupt?0x43cb599au:0x43cb5999u):(corrupt?0x43b8ccccu:0x43b8cccdu);
        uint32_t record[12]={0x3f333333,sum,0x3f333333,larger?581:528,1,0,7,0,1,0,1,0};
        derive_record(r,record,!corrupt);
    }
    if(argc==2 && !strcmp(argv[1],"constant"))constant_validation(r);
    constant_probe(r,argc==2 && !strcmp(argv[1],"constant"));
    /* A legacy entry must not commit a DV candidate without a submit receipt. */
    pending(r);r->ready=r->dv.ready=true;
    assert(!dvbridge_render_commit(r));
    assert(!dvbridge_render_rgb(r,NULL,NULL,0,0,0,(struct dvbridge_geometry){0}));
    assert(!dvbridge_render_dv_policy_output(r) && r->dv.retiring);
    completion=GL_ALREADY_SIGNALED;
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    /* Every failed foreign prepare invalidates views before eligibility. */
    pending(r);r->ready=r->dv.ready=true;
    assert(!dvbridge_render_packed(r,NULL,NULL,0,0,0,(struct dvbridge_geometry){0},NULL,false));
    assert(!dvbridge_render_dv_policy_output(r) && r->dv.retiring);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    pending(r);r->ready=r->dv.ready=true;
    assert(!dvbridge_render_hdr10_policy_rgb(r,NULL,NULL,NULL,NULL,0,0,0,(struct dvbridge_geometry){0}));
    assert(!dvbridge_render_dv_policy_output(r) && r->dv.retiring);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    /* Already completed analysis with no later pack needs no extra fence. */
    r->dv.active=r->dv.ready=r->ready=true;
    unsigned prior=checks;
    dvbridge_render_dv_policy_cancel(r);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE && checks==prior);
    completion=GL_TIMEOUT_EXPIRED;checks=deletes=0;
    pending(r);dvbridge_render_dv_policy_cancel(r);
    assert(!dvbridge_render_texture(r) && !dvbridge_render_dv_policy_output(r));
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_BUSY && checks==1 && deletes==0);
    dvbridge_renderer_reset(r);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_BUSY && checks==2 && deletes==0);
    completion=GL_ALREADY_SIGNALED;
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE && checks==3 && deletes==1);
    const GLuint retained_program=r->dv_analysis_program;
    pending(r);completion=GL_TIMEOUT_EXPIRED;
    dvbridge_renderer_destroy(r);
    if(retained_program)assert(glIsProgram(retained_program));
    assert(!dvbridge_retirement_owner_destroy(&owner));
    assert(dvbridge_retirement_owner_poll(owner)==DVBRIDGE_DV_BUSY && checks==4 && deletes==1);
    completion=GL_CONDITION_SATISFIED;
    assert(dvbridge_retirement_owner_poll(owner)==DVBRIDGE_DV_IDLE && checks==5 && deletes==2);
    if(retained_program)assert(!glIsProgram(retained_program));
    assert(dvbridge_retirement_owner_destroy(&owner) && !owner);
    assert(dvbridge_retirement_owner_destroy(&owner));
    if(argc==1)imported_lifetime(&g);
    reference_gpu_destroy(&g);
    puts("PASS fake completion backend: unsignaled cancel/reset/outliving owner and exact destroy readiness");
#endif
}
