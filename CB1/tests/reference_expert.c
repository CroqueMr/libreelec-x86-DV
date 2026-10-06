/* SPDX-License-Identifier: MIT */
#include "reference_test.h"

/* Catch silent final-storage downgrade, not intermediate FBO precision. */
static void final_target_precision(pl_gpu gpu, struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy, const struct dvbridge_identity *id,
    const struct pl_frame *frame, const void *metadata, size_t bytes,
    struct dvbridge_geometry geometry)
{
    struct dvbridge_hdr10_policy_output saved, snapshot;
    assert(dvbridge_render_policy_committed(r,&saved));
    const struct {const char *name; unsigned bits;} rejected[]={
        {"rgba8",10},{"rgba8",16},{"rgba16f",12},{"rgba16f",16},
        {"rgba16s",16},{"rgba16u",16}};
    const char *only=getenv("CB1_FINAL_TARGET_RED");
    for(unsigned i=0;i<sizeof(rejected)/sizeof(*rejected);i++) {
        if(only && strcmp(only,rejected[i].name))continue;
        pl_fmt fmt=pl_find_named_fmt(gpu,rejected[i].name);
        if(!fmt || !(fmt->caps&PL_FMT_CAP_RENDERABLE)) {
            assert(i>=4); /* Required UNORM8 and binary16 cases must run. */
            fprintf(stderr,"FINAL_TARGET_UNAVAILABLE format=%s not renderable\n",rejected[i].name);
            continue;
        }
        pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(target);
        assert(dvbridge_render_hdr10_policy_rgb(r,policy,id,frame,metadata,bytes,0,0,geometry));
        bool accepted=dvbridge_render_hdr10_policy_resolve(r,target,false,false,rejected[i].bits);
        fprintf(stderr,"FINAL_TARGET_REJECT format=%s type=%d RGB=%d/%d/%d bits=%u accepted=%d\n",
            fmt->name,fmt->type,fmt->component_depth[0],fmt->component_depth[1],fmt->component_depth[2],rejected[i].bits,accepted);
        assert(!accepted);
        assert(!dvbridge_render_policy_output(r) && !dvbridge_render_texture(r));
        assert(!dvbridge_render_policy_commit(r,id,target));
        assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==saved.final_target &&
            dvbridge_identity_equal(&snapshot.identity,&saved.identity));
        assert(glIsTexture(pl_opengl_unwrap(gpu,target,NULL,NULL,NULL)) &&
            glIsTexture(pl_opengl_unwrap(gpu,saved.final_target,NULL,NULL,NULL)));
        pl_tex_destroy(gpu,&target);
    }
    const char *valid[]={"rgba16","rgba32f"};
    const unsigned bits[]={10,12,16};
    /* Independently hand-derived code values for PQ 0,.5,1,.25. */
    const unsigned expected[2][3][4]={
        {{0,512,1023,256},{0,2048,4095,1024},{0,32768,65535,16384}},
        {{64,502,940,283},{256,2008,3760,1132},{4096,32128,60160,18112}}};
    const float composed[]={0,0,0,1,.5,.5,.5,1,1,1,1,1,.25,.25,.25,1};
    for(unsigned f=0;f<2;f++) {
        pl_fmt fmt=pl_find_named_fmt(gpu,valid[f]);
        assert(fmt && fmt->num_components==4 && (fmt->caps&PL_FMT_CAP_HOST_READABLE));
        pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true,.host_readable=true));assert(target);
        for(unsigned n=0;n<3;n++)for(unsigned limited=0;limited<2;limited++) {
            assert(dvbridge_render_hdr10_policy_rgb(r,policy,id,frame,metadata,bytes,0,0,geometry));
            glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(gpu,dvbridge_render_texture(r),NULL,NULL,NULL));
            glTexSubImage2D(GL_TEXTURE_2D,0,0,0,2,2,GL_RGBA,GL_FLOAT,composed);assert(glGetError()==GL_NO_ERROR);glBindTexture(GL_TEXTURE_2D,0);
            assert(dvbridge_render_hdr10_policy_resolve(r,target,false,limited,bits[n]));
            float values[16]; uint16_t stored[16];
            if(f==0) {
                assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.rc={.x1=2,.y1=2},.ptr=stored)));
                for(unsigned c=0;c<16;c++)values[c]=stored[c]/65535.0f;
            } else reference_read(gpu,target,0,0,2,2,values);
            for(unsigned p=0;p<4;p++)for(unsigned c=0;c<3;c++) {
                unsigned code=(unsigned)lround(values[4*p+c]*((1u<<bits[n])-1));
                assert(abs((int)code-(int)expected[limited][n][p])<=1);
                if(!p)assert(code==expected[limited][n][p]);
                if(!p && !limited)assert(values[c]==0);
            }
            dvbridge_render_policy_cancel(r);
            assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==saved.final_target);
            fprintf(stderr,"FINAL_TARGET_VALID format=%s bits=%u limited=%u code/black pass\n",fmt->name,bits[n],limited);
        }
        assert(glIsTexture(pl_opengl_unwrap(gpu,target,NULL,NULL,NULL)));
        pl_tex_destroy(gpu,&target);
    }
}

int main(void)
{
    assert(dvbridge_render_hdr10_policy_rgb && dvbridge_render_policy_output &&
        dvbridge_render_hdr10_policy_resolve && dvbridge_render_policy_commit &&
        dvbridge_render_policy_cancel && dvbridge_render_policy_committed);
    struct reference_gpu g=reference_gpu_create(); pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu); assert(r);
    float pixels[16]={.5,.5,.5,1,.2,.2,.2,1,0,0,0,1,.7,.6,.5,1};
    pl_tex input=reference_texture(gpu,2,2,pixels), a=reference_texture(gpu,3840,2160,NULL), b=reference_texture(gpu,3840,2160,NULL);
    struct pl_frame frame=reference_frame(input,2,2);
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0),*l6=av_dovi_get_ext(m,1);
    *l1=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.avg_pq=1667,.max_pq=3079}};
    *l6=(AVDOVIDmData){.level=6,.l6={.max_luminance=1000}};
    void *original=av_memdup(m,bytes); assert(original);
    struct dvbridge_policy policy=reference_policy(); struct dvbridge_identity id={1,7,1};
    struct dvbridge_geometry geometry={2,2,0,0,2,2};
    struct dvbridge_hdr10_policy_output snapshot;
    assert(!dvbridge_render_policy_output(r) && !dvbridge_render_policy_committed(r,&snapshot));
    assert(!dvbridge_render_policy_commit(r,&id,a));
#define PREPARE() dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,0,geometry)
    assert(PREPARE());
    const struct dvbridge_hdr10_policy_output *out=dvbridge_render_policy_output(r);
    assert(out && out->identity.picture==7 && out->policy.mode==DVBRIDGE_MODE_HDR10_EXPERT);
    assert(out->nominal_target.primaries==PL_COLOR_PRIM_BT_709 && out->nominal_target.transfer==PL_COLOR_TRC_LINEAR);
    assert(out->container.primaries==PL_COLOR_PRIM_BT_2020 && out->container.transfer==PL_COLOR_TRC_PQ);
    assert(out->hdr10.max_luminance==1500 && !out->hdr10.min_luminance && !out->hdr10.max_cll && !out->hdr10.max_fall);
    assert(!out->resolved && !out->final_target && dvbridge_render_texture(r));
    float before[4],after[4]; reference_read(gpu,dvbridge_render_texture(r),0,0,1,1,before);
    float composed[4]={.9,.1,.7,1};
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(gpu,dvbridge_render_texture(r),NULL,NULL,NULL));
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,GL_RGBA,GL_FLOAT,composed);assert(glGetError()==GL_NO_ERROR);glBindTexture(GL_TEXTURE_2D,0);
    reference_read(gpu,dvbridge_render_texture(r),0,0,1,1,after);
    assert(!memcmp(composed,after,sizeof(composed))); /* Prove actual exposed mutation. */
    assert(PREPARE()); reference_read(gpu,dvbridge_render_texture(r),0,0,1,1,after);
    assert(!memcmp(before,after,sizeof(before))); /* Same identity treats original, not composed pixels. */
    assert(!dvbridge_render_commit(r)); /* The legacy entry cannot consume Expert. */
    assert(!dvbridge_render_policy_commit(r,&id,a));
    assert(dvbridge_render_hdr10_policy_resolve(r,a,false,true,10));
    assert(dvbridge_render_policy_output(r)->resolved);
    assert(!dvbridge_render_policy_commit(r,&id,b));
    struct dvbridge_identity wrong=id; ++wrong.revision;
    assert(!dvbridge_render_policy_commit(r,&wrong,a));
    assert(dvbridge_render_policy_commit(r,&id,a));
    assert(!dvbridge_render_policy_commit(r,&id,a) && !dvbridge_render_policy_output(r));
    assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==a);
    assert(PREPARE()); assert(dvbridge_render_hdr10_policy_resolve(r,b,true,false,12));
    assert(!dvbridge_render_policy_commit(r,&id,a));
    dvbridge_render_policy_cancel(r); dvbridge_render_policy_cancel(r);
    assert(!dvbridge_render_policy_output(r) && !dvbridge_render_texture(r));
    assert(dvbridge_render_policy_committed(r,&snapshot) && snapshot.final_target==a);
    assert(PREPARE()); ++id.picture; assert(PREPARE());
    struct dvbridge_identity old=id; --old.picture;
    assert(dvbridge_render_hdr10_policy_resolve(r,b,false,false,16));
    assert(!dvbridge_render_policy_commit(r,&old,b));
    assert(dvbridge_render_policy_commit(r,&id,b));
    final_target_precision(gpu,r,&policy,&id,&frame,m,bytes,geometry);
    ++policy.revision; ++id.revision; policy.tv.gamut=DVBRIDGE_GAMUT_P3_D65;
    assert(PREPARE()); assert(dvbridge_render_policy_output(r)->nominal_target.primaries==PL_COLOR_PRIM_DISPLAY_P3);
    const double bad[]={NAN,INFINITY,-INFINITY};
    for(unsigned i=0;i<3;i++) {
        assert(!dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,bad[i],0,geometry));
        assert(!dvbridge_render_policy_output(r) && dvbridge_render_policy_committed(r,&snapshot));
        assert(!dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,bad[i],geometry));
    }
    --id.revision; assert(!PREPARE()); ++id.revision;
    const double rejected[]={1e-300,1e-6,1.000001e-6};
    for(unsigned i=0;i<3;i++) { policy.tv.peak_nits=rejected[i]; assert(!PREPARE()); }
    policy.tv.peak_nits=1500.000001; assert(PREPARE());
    assert(dvbridge_render_policy_output(r)->hdr10.max_luminance==1501);
    policy.tv.peak_nits=1500;
    m->num_ext_blocks=1; *l1=(AVDOVIDmData){.level=6,.l6={.max_luminance=1000}}; assert(!PREPARE());
    memcpy(m,original,bytes); l1=av_dovi_get_ext(m,0); l6=av_dovi_get_ext(m,1);
    l1->l1.max_pq=0; assert(!PREPARE()); memcpy(m,original,bytes);
    l6->level=1; assert(!PREPARE()); memcpy(m,original,bytes);
    l6->l6.min_luminance=10000; l6->l6.max_luminance=1; assert(!PREPARE()); memcpy(m,original,bytes);
    m->num_ext_blocks=1; assert(PREPARE()); /* Optional L6 absent, RPU mastering. */
    m->num_ext_blocks=2; *l6=(AVDOVIDmData){.level=8,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=10}; assert(PREPARE()); /* Valid unapplied optional creative block. */
    *l6=(AVDOVIDmData){.level=254,.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=2}; assert(PREPARE()); memcpy(m,original,bytes);
    av_dovi_get_header(m)->disable_residual_flag=0;
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++) { av_dovi_get_mapping(m)->nlq[c].nlq_offset=512; av_dovi_get_mapping(m)->nlq[c].linear_deadzone_slope=1; }
    assert(!PREPARE());
    float ep[16]; for(int i=0;i<16;i++) ep[i]=i%4==3?1:513.0f/1023;
    pl_tex el=reference_texture(gpu,2,2,ep); struct pl_frame ef=reference_frame(el,2,2); frame.enhancement_layer=&ef;
    assert(!dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,.000001,geometry));
    assert(PREPARE() && dvbridge_render_policy_output(r)->fel_reconstructed);
    ef.planes[0].texture=NULL; assert(!PREPARE()); ef.planes[0].texture=el;
    frame.enhancement_layer=NULL; memcpy(m,original,bytes);
    frame.planes[0].texture=NULL; assert(!PREPARE()); frame.planes[0].texture=input;
    frame.rotation=1; assert(!PREPARE()); frame.rotation=0;
    /* The allocation can include unused capacity; truncate an essential header,
     * not merely one byte of unused tail padding. */
    assert(!dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,1,0,0,geometry));
    geometry.width=0; assert(!PREPARE()); geometry.width=2;
    geometry.x=3840; assert(!PREPARE()); geometry.x=0;
    /* Fractional L5 edge: source left 1 of 2 -> destination x=1.5 of 3.
     * Pixel center exactly on the left edge is included; right is excluded.
     */
    pl_tex_clear(gpu,input,(float[4]){.5,.5,.5,1});
    m->num_ext_blocks=3; AVDOVIDmData *l5=av_dovi_get_ext(m,2);
    *l5=(AVDOVIDmData){.level=5,.l5={.left_offset=1}};
    geometry.width=geometry.height=3; assert(PREPARE());
    float fractional[3*3*4]; reference_read(gpu,dvbridge_render_texture(r),0,0,3,3,fractional);
    for(int y=0;y<3;y++)for(int x=0;x<3;x++)for(int c=0;c<3;c++)
        assert(x==0 ? fractional[4*(y*3+x)+c]==0 : fractional[4*(y*3+x)+c]>0);
    l5->l5.right_offset=1; assert(!PREPARE()); memcpy(m,original,bytes);
    geometry.width=geometry.height=2;
    /* Full-raster source and target, not just a small image in a 4K container. */
    /* Initial data is independent of the GL scissor left by the renderer.
     * A raw GPU clear respects that state and is not a full-source fixture.
     */
    float *full_pixels=malloc(3840*2160*4*sizeof(float));assert(full_pixels);
    for(int i=0;i<3840*2160*4;i++)full_pixels[i]=i%4==3?1:.5;
    pl_tex full=reference_texture(gpu,3840,2160,full_pixels);free(full_pixels);
    reference_read(gpu,full,0,0,1,1,after);fprintf(stderr,"FULL_RASTER_SOURCE=%.17g,%.17g,%.17g\n",after[0],after[1],after[2]);
    frame=reference_frame(full,3840,2160);geometry=(struct dvbridge_geometry){3840,2160,0,0,3840,2160};
    assert(PREPARE());
    const int corners[4][2]={{0,0},{3839,0},{0,2159},{3839,2159}};
    for(int i=0;i<4;i++){reference_read(gpu,dvbridge_render_texture(r),corners[i][0],corners[i][1],1,1,after);
        fprintf(stderr,"FULL_RASTER_CORNER=%d,%d PQ=%.17g,%.17g,%.17g\n",corners[i][0],corners[i][1],after[0],after[1],after[2]);
        for(int c=0;c<3;c++)assert(after[c]>0 && isfinite(after[c]));}
    assert(dvbridge_render_hdr10_policy_resolve(r,a,false,false,16));
    frame=reference_frame(input,2,2);geometry=(struct dvbridge_geometry){2,2,0,0,2,2};
    assert(PREPARE()); assert(!dvbridge_render_hdr10_policy_resolve(r,a,false,false,8));
    assert(!dvbridge_render_policy_output(r) && dvbridge_render_policy_committed(r,&snapshot));
    assert(PREPARE()); dvbridge_renderer_reset(r);
    assert(!dvbridge_render_policy_output(r) && !dvbridge_render_policy_committed(r,&snapshot));
    assert(glIsTexture(pl_opengl_unwrap(gpu,a,NULL,NULL,NULL)) && glIsTexture(pl_opengl_unwrap(gpu,b,NULL,NULL,NULL)));
    assert(PREPARE() && !memcmp(original,m,bytes));
    dvbridge_renderer_destroy(r); pl_tex_destroy(gpu,&input); pl_tex_destroy(gpu,&a); pl_tex_destroy(gpu,&b); pl_tex_destroy(gpu,&el); pl_tex_destroy(gpu,&full);
    av_free(original); av_free(m); reference_gpu_destroy(&g);
    puts("PASS Expert policy, descriptors, eligibility, pairing and presentation lifetime");
}
