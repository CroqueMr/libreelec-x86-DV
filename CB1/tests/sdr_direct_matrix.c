/* SPDX-License-Identifier: MIT */
/* Private Phase A. Separately link the same fixture to archived staged C and
 * prototype C; compare native outputs, not a replacement color calculation. */
#include "reference_test.h"
#include <stdio.h>

enum { W=256,H=8,N=W*H*4 };
static void pixels(float *p,bool residual)
{
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){
        float v=x/255.f;int i=4*(y*W+x);
        p[i]=residual?.5f+.15f*v:y==4?.02f*v:y==5?.5f+.5f*v:y==6?1.5f*v-.25f:v;
        p[i+1]=residual?.52f:y==0?p[i]:y==4?.01f:y==5?.7f:y==6?-.1f:y*.125f;
        p[i+2]=residual?.48f:y==0?p[i]:y==4?.005f:y==5?.8f:y==6?1.1f:1-v;
        p[i+3]=1;
    }
}

static pl_tex target(pl_gpu gpu,bool unorm,unsigned bits)
{
    if(!unorm)return reference_texture(gpu,W,H,NULL);
    pl_fmt f=NULL;
    for(int i=0;i<gpu->num_formats;i++){
        pl_fmt candidate=gpu->formats[i];
        if(candidate->type!=PL_FMT_UNORM || candidate->num_components<3 ||
           !(candidate->caps&PL_FMT_CAP_RENDERABLE))continue;
        if(candidate->component_depth[0]<(int)bits || candidate->component_depth[1]<(int)bits ||
           candidate->component_depth[2]<(int)bits)continue;
        if(!f || candidate->component_depth[0]<f->component_depth[0] ||
           (candidate->component_depth[0]==f->component_depth[0]&&candidate->texel_size<f->texel_size))f=candidate;
    }
    if(!f){printf("UNAVAILABLE UNORM %u\n",bits);return NULL;}
    printf("TARGET requested=%u format=%s depths=%d/%d/%d\n",bits,f->name,
        f->component_depth[0],f->component_depth[1],f->component_depth[2]);
    return pl_tex_create(gpu,pl_tex_params(.w=W,.h=H,.format=f,.renderable=true));
}

static void read_target(pl_gpu gpu,pl_tex tex,bool unorm,float *out)
{
    if(!unorm){reference_read(gpu,tex,0,0,W,H,out);return;}
    GLuint fbo,id=pl_opengl_unwrap(gpu,tex,NULL,NULL,NULL);assert(id);
    glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,id,0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    GLint format,type;glGetIntegerv(GL_IMPLEMENTATION_COLOR_READ_FORMAT,&format);
    glGetIntegerv(GL_IMPLEMENTATION_COLOR_READ_TYPE,&type);
    assert(format==GL_RGBA);assert(glGetError()==GL_NO_ERROR);
    union { uint8_t u8[N];uint16_t u16[N];uint32_t u32[N]; } data;
    glReadPixels(0,0,W,H,format,type,&data);assert(glGetError()==GL_NO_ERROR);
    for(int i=0;i<N;i++){
        if(type==GL_UNSIGNED_BYTE)out[i]=data.u8[i]/255.f;
        else if(type==GL_UNSIGNED_SHORT)out[i]=data.u16[i]/65535.f;
        else if(type==GL_UNSIGNED_INT_2_10_10_10_REV){
            unsigned shift=(i%4)*10,mask=i%4==3?3:1023;
            out[i]=((data.u32[i/4]>>shift)&mask)/(float)mask;
        }else{fprintf(stderr,"unavailable native read type %x\n",type);abort();}
    }
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
}

static bool compare(const char *root,const char *name,bool direct,pl_gpu gpu,pl_tex output,
                    bool unorm,unsigned bits)
{
    float a[N],b[N];read_target(gpu,output,unorm,a);
    char file[1024];snprintf(file,sizeof(file),"%s/%s.bin",root,name);
    FILE *f=fopen(file,direct?"rb":"wb");assert(f);
    if(!direct){assert(fwrite(a,sizeof(float),N,f)==N);fclose(f);return true;}
    assert(fread(b,sizeof(float),N,f)==N);fclose(f);
    double maximum=0,bias=0;unsigned failed=0,endpoints=0;
    for(int i=0;i<N;i++)if(i%4!=3){
        double delta=unorm?round(a[i]*((1u<<bits)-1))-round(b[i]*((1u<<bits)-1)):
            (double)a[i]-b[i];
        double limit=unorm?1:fmax(1e-7,2e-6*fabs(b[i]));
        maximum=fmax(maximum,fabs(delta));bias+=delta;
        if(!isfinite(a[i])||!isfinite(b[i])||fabs(delta)>limit)failed++;
        if(!unorm&&(b[i]==0||b[i]==1)&&a[i]!=b[i])endpoints++;
    }
    bias/=W*H*3;
    bool ok=!failed&&!endpoints&&(!unorm||fabs(bias)<=.1);
    printf("%s %s max=%.12g bias=%.12g failed=%u endpoints=%u\n",
        ok?"PASS":"FAIL",name,maximum,bias,failed,endpoints);fflush(stdout);
    return ok;
}

static bool draw(struct dvbridge_renderer *r,bool direct,const struct dvbridge_policy *p,
    const struct dvbridge_identity *id,const struct pl_frame *frame,const void *m,size_t bytes,
    pl_tex out,bool flip,bool limited,unsigned bits)
{
    const struct dvbridge_geometry g={W,H,0,0,W,H,W,H};
    bool ok=direct?dvbridge_render_hdr10_policy_direct(r,p,id,frame,m,bytes,1,1,g,out,flip,limited,bits):
        (dvbridge_render_sdr_policy_rgb(r,p,id,frame,m,bytes,1,1,g)&&
         dvbridge_render_sdr_policy_resolve(r,out,flip,limited,bits));
    if(!ok)return false;
    const struct dvbridge_hdr10_policy_output *pending=dvbridge_render_policy_output(r);
    assert(pending&&pending->resolved&&pending->final_target==out);
    assert(pending->fel_reconstructed==(frame->enhancement_layer!=NULL));
    struct dvbridge_identity wrong=*id;wrong.picture++;
    assert(!dvbridge_render_policy_commit(r,&wrong,out));
    return dvbridge_render_policy_commit(r,id,out);
}

int main(int argc,char **argv)
{
    assert(argc==3);bool direct=!strcmp(argv[1],"direct");
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    float p[N],residual[N];pixels(p,false);pixels(residual,true);
    pl_tex input=reference_texture(gpu.gl->gpu,W,H,p),eltex=reference_texture(gpu.gl->gpu,W,H,residual);
    struct pl_frame frame=reference_frame(input,W,H),el=reference_frame(eltex,W,H);
    frame.repr.alpha=el.repr.alpha=PL_ALPHA_NONE;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    struct dvbridge_identity id={10,1,3};
    struct dvbridge_policy policy={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    const struct dvbridge_sdr_profile profiles[]={
        {DVBRIDGE_SDR_REFERENCE},{DVBRIDGE_SDR_BRIGHT},
        {DVBRIDGE_SDR_CUSTOM,20,1.8,0},{DVBRIDGE_SDR_CUSTOM,500,2.8,5},
        {DVBRIDGE_SDR_CUSTOM,100,2.3,.02}};
    unsigned cases=0;
    /* Full-depth encoded FP32, including defaults, custom extrema, negative
     * pre-RPU components, non-neutral residual and processing lookups. */
    for(unsigned variant=0;variant<8;variant++)for(unsigned profile=0;profile<5;profile++){
        bool fel=variant==1;
        av_dovi_get_header(m)->disable_residual_flag=!fel;
        frame.enhancement_layer=fel?&el:NULL;
        frame.color.transfer=variant==2?PL_COLOR_TRC_HLG:PL_COLOR_TRC_PQ;
        av_dovi_get_color(m)->signal_color_space=variant==3?2:0;
        av_dovi_get_color(m)->source_max_pq=variant==4?3079:4095;
        av_dovi_get_color(m)->source_min_pq=variant==4?7:0;
        m->num_ext_blocks=variant>=6?1:0;
        if(variant>=6)*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,
            .l1={0,3079,variant==6?1500:0}};
        for(unsigned c=0;c<3;c++){
            av_dovi_get_mapping(m)->nlq[c].nlq_offset=512;
            av_dovi_get_mapping(m)->nlq[c].linear_deadzone_slope=4096;
            av_dovi_get_mapping(m)->nlq[c].vdr_in_max=1023*4096;
        }
        av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        dvbridge_renderer_set_processing_optimizations(r,variant==5);
        policy.sdr=profiles[profile];pl_tex out=target(gpu.gl->gpu,false,16);assert(out);
        char name[80];snprintf(name,sizeof(name),"float-v%u-p%u",variant,profile);
        if(!draw(r,direct,&policy,&id,&frame,m,bytes,out,false,false,16))return 2;
        if(!compare(argv[2],name,direct,gpu.gl->gpu,out,false,16))return 1;
        pl_tex_destroy(gpu.gl->gpu,&out);id.picture++;cases++;
    }
    av_dovi_get_header(m)->disable_residual_flag=1;frame.enhancement_layer=NULL;
    m->num_ext_blocks=0;
    av_dovi_get_color(m)->signal_color_space=0;av_dovi_get_color(m)->source_min_pq=0;
    av_dovi_get_color(m)->source_max_pq=4095;dvbridge_renderer_set_processing_optimizations(r,false);
    /* Actual separate sampled planes and chroma siting, not RGB vectors named
     * after a decoder/container. Native codec/RPU captures remain separate. */
    for(unsigned subsample=0;subsample<3;subsample++)for(unsigned depth=0;depth<4;depth++){
        const unsigned input_bits[]={8,10,12,16};unsigned bits=input_bits[depth];
        av_dovi_get_header(m)->bl_bit_depth=bits;
        for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->curves[c].pivots[1]=(1u<<bits)-1;
        struct pl_frame planar={.num_planes=3,.crop={0,0,W,H},
            .repr={.alpha=PL_ALPHA_NONE,.bits={.sample_depth=bits,.color_depth=bits}}};
        pl_tex plane[3];
        for(unsigned c=0;c<3;c++){
            int sx=c&&subsample?2:1,sy=c&&subsample==2?2:1,pw=W/sx,ph=H/sy;
            float data[N];
            for(int y=0;y<ph;y++)for(int x=0;x<pw;x++){
                int i=4*(y*pw+x);data[i]=p[4*(y*sy*W+x*sx)+c];
                data[i+1]=data[i+2]=0;data[i+3]=1;
            }
            plane[c]=reference_texture(gpu.gl->gpu,pw,ph,data);
            planar.planes[c]=(struct pl_plane){.texture=plane[c],.components=1,
                .component_mapping={(int)c},.shift_x=sx==2?.5:0,.shift_y=sy==2?.5:0};
        }
        policy.sdr=profiles[0];pl_tex out=target(gpu.gl->gpu,false,16);assert(out);
        char name[80];snprintf(name,sizeof(name),"planar-s%u-depth%u",subsample,bits);
        if(!draw(r,direct,&policy,&id,&planar,m,bytes,out,false,false,16))return 2;
        if(!compare(argv[2],name,direct,gpu.gl->gpu,out,false,16))return 1;
        for(unsigned c=0;c<3;c++)pl_tex_destroy(gpu.gl->gpu,&plane[c]);
        pl_tex_destroy(gpu.gl->gpu,&out);id.picture++;cases++;
    }
    av_dovi_get_header(m)->bl_bit_depth=10;
    for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->curves[c].pivots[1]=1023;
    const unsigned depths[]={8,10,12,16};
    for(unsigned d=0;d<4;d++)for(unsigned limited=0;limited<2;limited++)
    for(unsigned flip=0;flip<2;flip++)for(unsigned profile=0;profile<5;profile++){
        unsigned bits=depths[d];policy.sdr=profiles[profile];
        pl_tex out=target(gpu.gl->gpu,true,bits);if(!out)continue;
        char name[80];snprintf(name,sizeof(name),"unorm-b%u-l%u-f%u-p%u",bits,limited,flip,profile);
        if(!draw(r,direct,&policy,&id,&frame,m,bytes,out,flip,limited,bits))return 2;
        if(!compare(argv[2],name,direct,gpu.gl->gpu,out,true,bits))return 1;
        /* Default non-temporal dithering must repeat, not merely happen to
         * average to the reference in one frame. */
        float first[N],again[N];read_target(gpu.gl->gpu,out,true,first);
        if(!draw(r,direct,&policy,&id,&frame,m,bytes,out,flip,limited,bits))return 2;
        read_target(gpu.gl->gpu,out,true,again);assert(!memcmp(first,again,sizeof(first)));
        pl_tex_destroy(gpu.gl->gpu,&out);id.picture++;cases++;
    }
    printf("COMPLETE %u cases\n",cases);
    av_free(m);pl_tex_destroy(gpu.gl->gpu,&input);pl_tex_destroy(gpu.gl->gpu,&eltex);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&gpu);return 0;
}
