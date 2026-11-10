/* SPDX-License-Identifier: MIT */
#define main prior_dv_guard_main
#include "sdr_direct_guards.c"
#undef main
#include "dvbridge_gl_frame.h"
extern bool raw_native_import(struct dvbridge_gl_frame*,pl_gpu,enum dvbridge_gl_layout,
    int,int,const struct dvbridge_gl_plane[3],unsigned,bool,unsigned,unsigned*);

static unsigned raster_controls(struct reference_gpu* gpu,struct dvbridge_renderer* r,
                               const struct pl_frame* raw)
{
    uint16_t y[64],uv[32];for(unsigned i=0;i<64;i++)y[i]=400u<<6;
    for(unsigned i=0;i<32;i++)uv[i]=512u<<6;
    GLuint ids[2];glGenTextures(2,ids);
    for(unsigned i=0;i<2;i++){
        glBindTexture(GL_TEXTURE_2D,ids[i]);glTexImage2D(GL_TEXTURE_2D,0,i?0x822C:0x822A,
            i?4:8,i?4:8,0,i?GL_RG:GL_RED,GL_UNSIGNED_SHORT,i?uv:y);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    }
    struct dvbridge_gl_plane planes[3]={{ids[0],8,8},{ids[1],4,4}};
    struct dvbridge_gl_frame dv={0};unsigned used;
    assert(raw_native_import(&dv,gpu->gl->gpu,DVBRIDGE_P010,8,8,planes,100,false,AVCHROMA_LOC_LEFT,&used));
    size_t bytes;AVDOVIMetadata* metadata=task3_fixture(&bytes);
    const struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    const struct dvbridge_identity id={9,1,3};const struct dvbridge_geometry g={8,8,0,0,8,8,8,8};
    const int sizes[][2]={{4,8},{16,8},{8,4},{8,16}};unsigned failures=0;
    for(unsigned origin=0;origin<2;origin++){
        const struct pl_frame* frame=origin?&dv.frame:raw;
        const void* m=origin?metadata:NULL;size_t n=origin?bytes:0;
        assert(frame->repr.alpha==PL_ALPHA_UNKNOWN);
        pl_tex matched=reference_texture(gpu->gl->gpu,8,8,NULL);
        assert(dvbridge_render_sdr_policy_direct_eligible(r,&p,&id,frame,m,n,1,1,g,matched,8));
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,frame,m,n,1,1,g,matched,false,false,8));
        assert(dvbridge_render_policy_commit(r,&id,matched));
        struct dvbridge_hdr10_policy_output accepted;assert(dvbridge_render_policy_committed(r,&accepted));
        for(unsigned size=0;size<4;size++){
            pl_tex target=reference_texture(gpu->gl->gpu,sizes[size][0],sizes[size][1],NULL);
            struct pl_frame saved=*frame;struct dvbridge_renderer before=*r;
            bool eligible=dvbridge_render_sdr_policy_direct_eligible(r,&p,&id,frame,m,n,1,1,g,target,8);
            bool pure=!memcmp(&saved,frame,sizeof(saved))&&!memcmp(&before,r,sizeof(before));
            unsigned prior=draws;
            bool prepared=dvbridge_render_hdr10_policy_direct(r,&p,&id,frame,m,n,1,1,g,target,false,false,8);
            bool pending=dvbridge_render_policy_output(r)!=NULL;
            struct dvbridge_hdr10_policy_output after;
            bool retained=dvbridge_render_policy_committed(r,&after)&&
                dvbridge_identity_equal(&accepted.identity,&after.identity)&&after.final_target==matched;
            bool failed=eligible||!pure||draws!=prior||prepared||pending||!retained;
            failures+=failed;
            printf("RASTER %s %dx%d eligible=%d pure=%d draws=%u prepared=%d pending=%d retained=%d %s\n",
                origin?"DV":"raw",sizes[size][0],sizes[size][1],eligible,pure,draws-prior,
                prepared,pending,retained,failed?"FAIL":"PASS");fflush(stdout);
            dvbridge_render_policy_cancel(r);pl_tex_destroy(gpu->gl->gpu,&target);
        }
        pl_tex_destroy(gpu->gl->gpu,&matched);
    }
    av_free(metadata);dvbridge_gl_frame_release(&dv);glDeleteTextures(2,ids);return failures;
}
int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer* r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    GLuint ids[2];glGenTextures(2,ids);uint8_t y[64],uv[32];memset(y,100,sizeof(y));memset(uv,128,sizeof(uv));
    for(unsigned i=0;i<2;i++){
        glBindTexture(GL_TEXTURE_2D,ids[i]);glTexImage2D(GL_TEXTURE_2D,0,i?GL_RG8:GL_R8,
            i?4:8,i?4:8,0,i?GL_RG:GL_RED,GL_UNSIGNED_BYTE,i?uv:y);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    }
    struct dvbridge_gl_plane planes[3]={{ids[0],8,8},{ids[1],4,4}};
    struct dvbridge_gl_frame imported={0};unsigned used;
    assert(raw_native_import(&imported,gpu.gl->gpu,DVBRIDGE_NV12,8,8,planes,0,false,AVCHROMA_LOC_LEFT,&used));
    const struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    const struct dvbridge_identity id={1,1,3};struct dvbridge_geometry g={8,8,0,0,8,8,8,8};
    pl_tex output=reference_texture(gpu.gl->gpu,8,8,NULL);unsigned checks=0;
#define QUERY(frame,policy,identity) dvbridge_render_sdr_policy_direct_eligible(r,policy,identity,frame,NULL,0,1,1,g,output,8)
#define DRAW() dvbridge_render_hdr10_policy_direct(r,&p,&id,&imported.frame,NULL,0,1,1,g,output,false,false,8)
    struct pl_frame saved=imported.frame;struct dvbridge_renderer before=*r;
    assert(QUERY(&imported.frame,&p,&id));checks++;
    assert(!QUERY(&imported.frame,NULL,&id));assert(!QUERY(&imported.frame,&p,NULL));
    assert(!QUERY(NULL,&p,&id));checks+=3;
    struct dvbridge_policy wrong=p;wrong.mode=DVBRIDGE_MODE_HDR10_EXPERT;assert(!QUERY(&imported.frame,&wrong,&id));checks++;
    assert(!memcmp(&saved,&imported.frame,sizeof(saved))&&!memcmp(&before,r,sizeof(before)));
    /* Actual UNKNOWN-without-A is reachable; malformed/explicit alpha is not. */
    imported.frame.planes[1].component_mapping[1]=PL_CHANNEL_A;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.planes[1].component_mapping[0]=0;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.repr.alpha=PL_ALPHA_PREMULTIPLIED;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.planes[0].components=4;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.repr.sys=PL_COLOR_SYSTEM_RGB;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.color.transfer=PL_COLOR_TRC_HLG;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;imported.frame.color.hdr.max_luma=NAN;assert(!QUERY(&imported.frame,&p,&id));checks++;
    imported.frame=saved;g.crop[0]=2;g.crop[2]=6;g.crop[3]=8;assert(!QUERY(&imported.frame,&p,&id));checks++;memset(g.crop,0,sizeof(g.crop));
    assert(DRAW());assert(dvbridge_render_texture(r)==NULL);assert(dvbridge_render_policy_commit(r,&id,output));checks++;
    struct dvbridge_hdr10_policy_output accepted;assert(dvbridge_render_policy_committed(r,&accepted));
    fail_intermediate=true;unsigned prior=draws;
    assert(!DRAW()&&draws==prior+1&&hook_failures==1&&!dvbridge_render_policy_output(r));
    struct dvbridge_hdr10_policy_output after;assert(dvbridge_render_policy_committed(r,&after));
    assert(dvbridge_identity_equal(&accepted.identity,&after.identity));checks++;fail_intermediate=false;
    dvbridge_renderer_destroy(r);r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    /* Real pending-P5 copy must finish before the new direct-only output, with
     * no stale RGB exposed as the newly prepared SDR image. */
    float backing[256];for(unsigned i=0;i<256;i++)backing[i]=i%4==3?1:.7f;
    pl_fmt format=pl_find_fmt(gpu.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    r->p5_native=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=8,.h=8,.format=format,
        .sampleable=true,.renderable=true,.blit_src=true,.initial_data=backing));
    assert(r->p5_native);r->p5_native_pending=true;
    assert(!r->rgb&&DRAW()&&r->rgb&&!r->p5_native_pending);
    float retained[256];reference_read(gpu.gl->gpu,r->rgb,0,0,8,8,retained);assert(!memcmp(backing,retained,sizeof(backing)));
    assert(!r->dv.output.intermediate&&dvbridge_render_texture(r)==NULL);checks++;
    printf("PASS %u raw pure-query/alpha/failure/P5 controls\n",checks);
    unsigned failures=raster_controls(&gpu,r,&imported.frame);
    printf("RASTER SUMMARY invalid=8 matched_positive=2 failures=%u\n",failures);fflush(stdout);
    assert(!failures);
    dvbridge_gl_frame_release(&imported);glDeleteTextures(2,ids);pl_tex_destroy(gpu.gl->gpu,&output);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&gpu);return 0;
}
