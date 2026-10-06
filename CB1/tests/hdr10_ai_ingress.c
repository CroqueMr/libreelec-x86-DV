/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "reference_test.h"
#include "cb1_hdr10_ingress.h"
#include <libswscale/swscale.h>
#include <libavutil/pixfmt.h>

static unsigned gpu_errors;
static void ingress_log(void *priv,enum pl_log_level level,const char *message)
{
    (void)priv;if(level<=PL_LOG_ERR){++gpu_errors;fprintf(stderr,"%s\n",message);}
}

static void check(struct reference_gpu *gpu,struct cb1_hdr10_ingress *ctx,
                  int width,int height,int depth,bool sub,bool packed,bool small,int padding)
{
    const int tw=width+2*padding,th=height+2*padding;
    const int ow=small?128:width,oh=small?72:height;
    uint16_t *planes[3],*expected=calloc(ow*oh*3,sizeof(uint16_t));assert(expected);
    struct pl_frame source={.num_planes=packed?2:3,.crop={padding,padding,width+padding,height+padding},
        .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
            .bits={.sample_depth=16,.color_depth=depth,.bit_shift=packed?16-depth:0}},
        .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ}};
    for (unsigned c=0; c<3; ++c) {
        const int w=c&&sub?tw/2:tw,h=c&&sub?th/2:th;
        planes[c]=calloc(w*h,sizeof(uint16_t));assert(planes[c]);
        const unsigned scale=1u<<(depth-8);
        for (int i=0; i<w*h; ++i)
            planes[c][i]=c?64*scale+(i*(c==1?7:23))%(128*scale+1):16*scale+(i*13)%(219*scale+1);
    }
    struct SwsContext *sws=sws_getContext(width,height,
        sub?(depth==10?AV_PIX_FMT_YUV420P10LE:AV_PIX_FMT_YUV420P12LE):
            (depth==10?AV_PIX_FMT_YUV444P10LE:AV_PIX_FMT_YUV444P12LE),
        ow,oh,AV_PIX_FMT_RGB48LE,SWS_BILINEAR,NULL,NULL,NULL);assert(sws);
    const int *coefficients=sws_getCoefficients(SWS_CS_BT2020);
    assert(!sws_setColorspaceDetails(sws,coefficients,0,coefficients,1,0,1<<16,1<<16));
    const uint8_t *input[4]={(uint8_t *)planes[0],(uint8_t *)planes[1],(uint8_t *)planes[2],NULL};
    int strides[4]={tw*2,sub?tw:tw*2,sub?tw:tw*2,0};
    for(unsigned c=0;c<3;++c){int offset=c&&sub?padding/2:padding;
        input[c]+=(size_t)offset*strides[c]+offset*2;}
    uint8_t *output[4]={(uint8_t *)expected,NULL,NULL,NULL};int out_strides[4]={ow*6,0,0,0};
    assert(sws_scale(sws,input,strides,0,height,output,out_strides)==oh);sws_freeContext(sws);
    for (int c=0; c<source.num_planes; ++c) {
        const int w=c&&sub?tw/2:tw,h=c&&sub?th/2:th,components=packed&&c?2:1;
        uint16_t *data=calloc(w*h*components,sizeof(uint16_t));assert(data);
        for (int i=0; i<w*h; ++i) {
            data[i*components]=planes[c][i]<<(packed?16-depth:0);
            if (components==2) data[i*2+1]=planes[2][i]<<(16-depth);
        }
        pl_fmt fmt=pl_find_fmt(gpu->gl->gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE);
        assert(fmt);source.planes[c]=(struct pl_plane){.components=components,.component_mapping={c,c+1},
            .texture=pl_tex_create(gpu->gl->gpu,pl_tex_params(.w=w,.h=h,.format=fmt,.sampleable=true,.initial_data=data))};
        free(data);assert(source.planes[c].texture);
    }
    pl_tex texture=NULL;
    assert((small?cb1_hdr10_ingress_small(ctx,&source,&texture):
        cb1_hdr10_ingress_rgb(ctx,&source,&texture))==CB1_AI_READY && texture);
    assert(gpu_errors==0);
    uint16_t *actual=calloc(ow*oh*4,sizeof(uint16_t));assert(actual);
    float *small_rgb=small?calloc(ow*oh*4,sizeof(float)):NULL;
    GLuint fbo,id=pl_opengl_unwrap(gpu->gl->gpu,texture,NULL,NULL,NULL);
    glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,id,0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(0,0,ow,oh,GL_RGBA,small?GL_FLOAT:GL_UNSIGNED_SHORT,small?(void *)small_rgb:actual);
    assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
    unsigned different=0,max_error=0;
    for (int i=0; i<ow*oh; ++i) for (unsigned c=0; c<3; ++c) {
        if(small){
            float reference=(float)(_Float16)((float)expected[3*i+c]/65535.f);
            if(small_rgb[4*i+c]!=reference && different<8)
                fprintf(stderr,"small pixel%d channel%u actual %.8g expected %.8g code%u\n",i,c,small_rgb[4*i+c],reference,expected[3*i+c]);
            different+=small_rgb[4*i+c]!=reference;
            continue;
        }
        const unsigned code=actual[4*i+c];
        const unsigned e=expected[3*i+c];const unsigned delta=code>e?code-e:e-code;
        different+=delta!=0;if(delta>max_error)max_error=delta;
    }
    if (different) fprintf(stderr,"%dx%d %d-bit sub=%d packed=%d: %u components, max=%u\n",
        width,height,depth,sub,packed,different,max_error);
    assert(different==0);
    source.color.transfer=PL_COLOR_TRC_BT_1886;
    pl_tex prior=texture;
    assert(cb1_hdr10_ingress_rgb(ctx,&source,&texture)==CB1_AI_INCOMPATIBLE && texture==prior);
    for (int c=0; c<source.num_planes; ++c) pl_tex_destroy(gpu->gl->gpu,&source.planes[c].texture);
    for (unsigned c=0; c<3; ++c)free(planes[c]);
    free(expected);free(actual);free(small_rgb);
}

int main(void)
{
    setenv("CB1_REFERENCE_TRACE","1",1);
    struct reference_gpu gpu=reference_gpu_create();
    pl_log_update(gpu.log,pl_log_params(.log_cb=ingress_log,.log_level=PL_LOG_ERR));
    struct cb1_hdr10_ingress *ctx=cb1_hdr10_ingress_create(gpu.gl->gpu);assert(ctx);
    for (int depth=10; depth<=12; depth+=2) {
        for(unsigned small=0;small<2;++small){
            check(&gpu,ctx,256,144,depth,false,false,small,0);
            check(&gpu,ctx,256,144,depth,true,false,small,0);
            check(&gpu,ctx,256,144,depth,true,true,small,0);
            check(&gpu,ctx,256,144,depth,true,true,small,8);
            check(&gpu,ctx,256,144,depth,false,false,small,8);
        }
        check(&gpu,ctx,1920,1080,depth,true,true,true,0);
        check(&gpu,ctx,3840,2160,depth,true,true,true,0);
        check(&gpu,ctx,3840,2160,depth,true,true,true,8);
        check(&gpu,ctx,4096,2160,depth,false,false,true,0);
    }
    cb1_hdr10_ingress_destroy(&ctx);reference_gpu_destroy(&gpu);
    puts("GPU analysis RGB48 ingress matches pinned swscale");
}
