/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include <libplacebo/utils/libav.h>
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/custom.h>
#include "dvbridge_gl_frame.h"
#ifndef DVBRIDGE_GL_CHROMA_API
extern void dvbridge_gl_frame_set_chroma(struct dvbridge_gl_frame *,enum pl_chroma_location) __attribute__((weak));
#endif
#ifndef DVBRIDGE_CHROMA_MAP_API
extern enum pl_chroma_location dvbridge_map_chroma(enum AVChromaLocation) __attribute__((weak));
#endif

static void chroma(struct reference_gpu *g)
{
    assert(dvbridge_map_chroma);
    assert(dvbridge_map_chroma(AVCHROMA_LOC_TOPLEFT)==PL_CHROMA_TOP_LEFT);
    assert(dvbridge_map_chroma(AVCHROMA_LOC_LEFT)==PL_CHROMA_LEFT);
    assert(dvbridge_map_chroma(AVCHROMA_LOC_UNSPECIFIED)==PL_CHROMA_UNKNOWN);
    GLuint tex[2];glGenTextures(2,tex);
    for(int i=0;i<2;i++){
        glBindTexture(GL_TEXTURE_2D,tex[i]);
        glTexStorage2D(GL_TEXTURE_2D,1,i?GL_RG8:GL_R8,i?4:8,i?4:8);
    }
    struct dvbridge_gl_plane planes[3]={{tex[0],8,8},{tex[1],4,4}};
    struct dvbridge_gl_frame f={0};
    assert(dvbridge_gl_frame_import(&f,g->gl->gpu,DVBRIDGE_NV12,8,8,planes));
    assert(f.frame.planes[1].shift_x==0 && f.frame.planes[1].shift_y==0);
    assert(dvbridge_gl_frame_set_chroma);
    dvbridge_gl_frame_set_chroma(&f,PL_CHROMA_TOP_LEFT);
    assert(f.frame.planes[1].shift_x==-.5f && f.frame.planes[1].shift_y==-.5f);
    assert(f.frame.planes[0].shift_x==0 && f.frame.planes[0].shift_y==0);
    assert(f.frame.repr.sys==PL_COLOR_SYSTEM_UNKNOWN);
    dvbridge_gl_frame_set_chroma(&f,PL_CHROMA_LEFT);
    assert(f.frame.planes[1].shift_x==-.5f && f.frame.planes[1].shift_y==0);
    dvbridge_gl_frame_release(&f);glDeleteTextures(2,tex);
}

static float sample(struct reference_gpu *g, AVDOVIMetadata *m,
                    float input, float enhancement, bool native)
{
    struct pl_dovi_metadata d={0};pl_map_dovi_metadata(&d,m);
#ifdef PL_HAVE_CB1_NATIVE_BOUNDS
    d.cb1_native_bounds=native;
#else
    (void)native;
#endif
    pl_dispatch dp=pl_dispatch_create(NULL,g->gl->gpu);
    pl_shader sh=pl_dispatch_begin(dp),el=NULL;
    char body[128];
    snprintf(body,sizeof(body),"color=vec4(%.9g,%.9g,%.9g,1.0);",input,input,input);
    assert(pl_shader_custom(sh,&(struct pl_custom_shader){.input=PL_SHADER_SIG_NONE,
        .output=PL_SHADER_SIG_COLOR,.body=body}));
    if(d.nlq_active){
        el=pl_shader_alloc(NULL,pl_shader_params(.gpu=g->gl->gpu,.id=1));
        snprintf(body,sizeof(body),"color=vec4(%.9g,%.9g,%.9g,1.0);",enhancement,enhancement,enhancement);
        assert(pl_shader_custom(el,&(struct pl_custom_shader){.input=PL_SHADER_SIG_NONE,
            .output=PL_SHADER_SIG_COLOR,.body=body}));
    }
    struct pl_color_repr repr={.sys=PL_COLOR_SYSTEM_DOLBYVISION,.levels=PL_COLOR_LEVELS_FULL,
        .bits={.sample_depth=10,.color_depth=10},.dovi=&d};
    pl_shader_dovi_reconstruct(sh,&repr,el);pl_shader_free(&el);
    pl_tex target=reference_texture(g->gl->gpu,1,1,NULL);
    assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
    float value[4];reference_read(g->gl->gpu,target,0,0,1,1,value);
    pl_tex_destroy(g->gl->gpu,&target);pl_dispatch_destroy(&dp);
    return value[0];
}

int main(int argc,char **argv)
{
    assert(argc==2);struct reference_gpu g=reference_gpu_create();
    if(!strcmp(argv[1],"chroma")){
        chroma(&g);reference_gpu_destroy(&g);puts("PASS source chroma phase");return 0;
    }
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    AVDOVIDataMapping *map=av_dovi_get_mapping(m);
    h->vdr_bit_depth=12;h->coef_log2_denom=23;
    if(!strcmp(argv[1],"nlq") || !strcmp(argv[1],"legacy")){
        h->disable_residual_flag=0;map->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(int c=0;c<3;c++){
            map->curves[c].poly_coef[0][0]=1<<21;map->curves[c].poly_coef[0][1]=0;
            map->nlq[c].nlq_offset=512;map->nlq[c].linear_deadzone_slope=1<<13;
            map->nlq[c].linear_deadzone_threshold=1<<12;map->nlq[c].vdr_in_max=1<<17;
        }
        bool native=strcmp(argv[1],"legacy")!=0;
        float high=sample(&g,m,.5f,768.0f/1023,native);
        float low=sample(&g,m,.5f,256.0f/1023,native);
        assert(fabsf(high-(native?.265625f:.5f))<1e-6f);
        assert(fabsf(low-(native?.234375f:0.f))<1e-6f);
        assert(fabsf(sample(&g,m,.5f,512.0f/1023,native)-.25f)<1e-6f);
    }else{
        assert(!strcmp(argv[1],"pivots"));
        for(int c=0;c<3;c++){
            map->curves[c].pivots[0]=256;map->curves[c].pivots[1]=768;
            map->curves[c].poly_order[0]=2;map->curves[c].poly_coef[0][1]=0;
            map->curves[c].poly_coef[0][2]=1<<23;
        }
        /* Existing normalized domain, independently squared endpoint. */
        assert(fabsf(sample(&g,m,.9f,0,true)-.563600003f)<2e-6f);
        assert(fabsf(sample(&g,m,0,0,true)-.062622249f)<2e-6f);
        assert(fabsf(sample(&g,m,.9f,0,false)-.750733137f)<1e-6f);
    }
    av_free(m);reference_gpu_destroy(&g);puts("PASS native bounds and legacy isolation");
}
