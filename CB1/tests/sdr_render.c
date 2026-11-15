/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_circuit.h"
#include "dvbridge_gl_frame.h"
enum { W=256,H=8,N=W*H*4 };
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

struct native_planes { GLuint textures[3];struct dvbridge_gl_plane planes[3]; };
static struct native_planes native_planes(enum dvbridge_gl_layout layout,bool residual)
{
    struct native_planes out={0};
    bool planar=layout==DVBRIDGE_YUV420P10||layout==DVBRIDGE_YUV444P10;
    bool packed=layout==DVBRIDGE_Y416,sub=layout!=DVBRIDGE_YUV444P10&&!packed;
    unsigned depth=layout==DVBRIDGE_NV12?8:layout==DVBRIDGE_P012?12:layout==DVBRIDGE_P016?16:10;
    unsigned shift=layout==DVBRIDGE_P010||packed?6:layout==DVBRIDGE_P012?4:0;
    unsigned count=packed?1:planar?3:2;glGenTextures(count,out.textures);
    for(unsigned plane=0;plane<count;plane++){
        int width=plane&&sub?W/2:W,height=plane&&sub?H/2:H;
        int components=packed?4:!planar&&plane?2:1;
        uint8_t u8[N];uint16_t u16[N];
        for(int y=0;y<height;y++)for(int x=0;x<width;x++)for(int c=0;c<components;c++){
            int channel=packed?(c==0?1:c==1?0:c):plane?(planar?plane:c+1):0;
            float v=channel==0?x/(float)(width-1):y==0?.5f:channel==1?.05f+.9f*x/(width-1):.95f-.9f*x/(width-1);
            if(channel==0&&y==4)v*=.02f;
            if(channel==0&&y==5)v=.5f+.5f*v;
            if(residual)v=.5f+(channel==0?.03f*(x/(float)(width-1)-.5f):channel==1?.005f:-.005f);
            unsigned code=lrintf(fminf(1,fmaxf(0,v))*((1u<<depth)-1));
            int i=(y*width+x)*components+c;u8[i]=code;u16[i]=packed&&c==3?65535:code<<shift;
        }
        glBindTexture(GL_TEXTURE_2D,out.textures[plane]);
        GLenum format=components==4?GL_RGBA:components==2?GL_RG:GL_RED;
        GLint internal=components==4?0x805B:depth==8?(components==2?GL_RG8:GL_R8):(components==2?0x822C:0x822A);
        glTexImage2D(GL_TEXTURE_2D,0,internal,width,height,0,format,depth==8?GL_UNSIGNED_BYTE:GL_UNSIGNED_SHORT,depth==8?(void*)u8:(void*)u16);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        out.planes[plane]=(struct dvbridge_gl_plane){out.textures[plane],width,height};
    }
    assert(glGetError()==GL_NO_ERROR);return out;
}


/* Current staged and direct owners have separate renderer instances. Fixed
 * gates are the archived Phase A gates; this test needs no Git history. */
static unsigned comparisons;
static float last_expected[N];
static void paired(struct reference_gpu *gpu,struct dvbridge_renderer *staged,
    struct dvbridge_renderer *direct,const struct pl_frame *frame,const void *dv,size_t bytes,
    const struct dvbridge_sdr_profile *profile,bool unorm,unsigned bits,bool limited,bool flip)
{
    const struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR,.sdr=*profile};
    const struct dvbridge_identity id={1,comparisons+1,3};
    pl_tex a=target(gpu->gl->gpu,unorm,bits),b=target(gpu->gl->gpu,unorm,bits);assert(a&&b);
    assert(draw(staged,false,&p,&id,frame,dv,bytes,a,flip,limited,bits));
    assert(draw(direct,true,&p,&id,frame,dv,bytes,b,flip,limited,bits));
    float expected[N],actual[N];read_target(gpu->gl->gpu,a,unorm,expected);read_target(gpu->gl->gpu,b,unorm,actual);
    double maximum=0,bias=0;unsigned failed=0,endpoints=0;
    for(unsigned i=0;i<N;i++)if(i%4!=3){
        double delta=unorm?round(actual[i]*((1u<<bits)-1))-round(expected[i]*((1u<<bits)-1)):
            (double)actual[i]-expected[i];
        double limit=unorm?1:fmax(1e-7,2e-6*fabs(expected[i]));
        maximum=fmax(maximum,fabs(delta));bias+=delta;
        if(!isfinite(actual[i])||!isfinite(expected[i])||fabs(delta)>limit)failed++;
        if(!unorm&&(expected[i]==0||expected[i]==1)&&actual[i]!=expected[i])endpoints++;
    }
    bias/=W*H*3;
    memcpy(last_expected,expected,sizeof(expected));
    printf("PAIR %u max=%.12g bias=%.12g failed=%u endpoints=%u\n",++comparisons,maximum,bias,failed,endpoints);
    assert(!failed&&!endpoints&&(!unorm||fabs(bias)<=.1));
    if(unorm){
        float repeated[N];
        assert(draw(staged,false,&p,&id,frame,dv,bytes,a,flip,limited,bits));
        read_target(gpu->gl->gpu,a,true,repeated);assert(!memcmp(expected,repeated,sizeof(expected)));
        assert(draw(direct,true,&p,&id,frame,dv,bytes,b,flip,limited,bits));
        read_target(gpu->gl->gpu,b,true,repeated);assert(!memcmp(actual,repeated,sizeof(actual)));
    }
    pl_tex_destroy(gpu->gl->gpu,&a);pl_tex_destroy(gpu->gl->gpu,&b);
}
static void native_pair(struct reference_gpu *gpu,struct dvbridge_renderer *staged,
    struct dvbridge_renderer *direct,enum dvbridge_gl_layout layout,bool full,unsigned chroma,
    const struct dvbridge_sdr_profile *profile,bool unorm,unsigned bits,bool limited,bool flip,
    const void *dv,size_t bytes,bool fel)
{
    struct native_planes planes=native_planes(layout,false),residual={0};
    struct dvbridge_gl_frame frame={0},el={0};
    assert(dvbridge_gl_frame_import(&frame,gpu->gl->gpu,layout,W,H,planes.planes));
    dvbridge_gl_frame_set_chroma(&frame,chroma);
    frame.frame.repr.sys=PL_COLOR_SYSTEM_BT_2020_NC;
    frame.frame.repr.levels=full?PL_COLOR_LEVELS_FULL:PL_COLOR_LEVELS_LIMITED;
    frame.frame.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.min_luma=.01,.max_luma=1000}};
    if(fel){
        residual=native_planes(layout,true);
        assert(dvbridge_gl_frame_import(&el,gpu->gl->gpu,layout,W,H,residual.planes));
        dvbridge_gl_frame_set_chroma(&el,chroma);frame.frame.enhancement_layer=&el.frame;
    }
    assert(frame.frame.repr.alpha==PL_ALPHA_UNKNOWN&&(!fel||el.frame.repr.alpha==PL_ALPHA_UNKNOWN));
    paired(gpu,staged,direct,&frame.frame,dv,bytes,profile,unorm,bits,limited,flip);
    dvbridge_gl_frame_release(&el);dvbridge_gl_frame_release(&frame);
    glDeleteTextures(3,residual.textures);glDeleteTextures(3,planes.textures);
}
static void hlg_native_sdr(struct reference_gpu *gpu,struct dvbridge_renderer *r)
{
    struct native_planes planes=native_planes(DVBRIDGE_P010,false);
    struct dvbridge_gl_frame imported={0};
    assert(dvbridge_gl_frame_import(&imported,gpu->gl->gpu,DVBRIDGE_P010,W,H,planes.planes));
    dvbridge_gl_frame_set_chroma(&imported,PL_CHROMA_LEFT);
    struct pl_frame *frame=&imported.frame;
    frame->repr.sys=PL_COLOR_SYSTEM_BT_2020_NC;
    frame->repr.levels=PL_COLOR_LEVELS_LIMITED;
    frame->color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_HLG};
    struct dvbridge_policy policy={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    const struct dvbridge_identity id={1,1,3};
    pl_tex out=target(gpu->gl->gpu,true,10);assert(out);
    float reference[N],actual[N];
    for(unsigned preset=0;preset<3;preset++){
        policy.sdr=(struct dvbridge_sdr_profile){preset,120,2.35,.02};
        assert(!draw(r,true,&policy,&id,frame,NULL,0,out,false,true,10));
        assert(draw(r,false,&policy,&id,frame,NULL,0,out,false,true,10));
        read_target(gpu->gl->gpu,out,true,reference);
        // An HLG decoder may carry static or dynamic mastering data. HLG
        // luminance is defined by the reference system, independently of it.
        frame->color.hdr=(struct pl_hdr_metadata){.max_luma=4000,.scene_max={800,500,400}};
        assert(draw(r,false,&policy,&id,frame,NULL,0,out,false,true,10));
        read_target(gpu->gl->gpu,out,true,actual);
        assert(!memcmp(actual,reference,sizeof(actual)));
        memset(&frame->color.hdr,0,sizeof(frame->color.hdr));
        for(unsigned i=0;i<N;i++)if(i%4!=3)
            assert(isfinite(actual[i]) && actual[i]>=0 && actual[i]<=1);
        assert(actual[0]>=63.f/1023 && actual[4*(W-1)]<=941.f/1023);
        assert(actual[W]<actual[2*W] && actual[2*W]<actual[3*W]);
        assert(fabsf(actual[3*W]-actual[3*W+1])<2.f/1023);
        assert(fabsf(actual[3*W]-actual[3*W+2])<2.f/1023);
    }
    pl_tex_destroy(gpu->gl->gpu,&out);
    dvbridge_gl_frame_release(&imported);
    glDeleteTextures(3,planes.textures);
}

static void raster_regression(struct reference_gpu *gpu,struct dvbridge_renderer *r)
{
    struct native_planes planes=native_planes(DVBRIDGE_P010,false);
    struct dvbridge_gl_frame imported={0};
    assert(dvbridge_gl_frame_import(&imported,gpu->gl->gpu,DVBRIDGE_P010,W,H,planes.planes));
    imported.frame.repr.sys=PL_COLOR_SYSTEM_BT_2020_NC;
    imported.frame.repr.levels=PL_COLOR_LEVELS_LIMITED;
    imported.frame.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,
        .transfer=PL_COLOR_TRC_PQ,.hdr={.min_luma=.01,.max_luma=1000}};
    assert(imported.frame.repr.alpha==PL_ALPHA_UNKNOWN);
    size_t bytes;AVDOVIMetadata *dv=task3_fixture(&bytes);
    const struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    const struct dvbridge_geometry g={W,H,0,0,W,H,W,H};
    const int sizes[][2]={{W/2,H},{W*2,H},{W,H/2},{W,H*2}};unsigned cases=0;
    for(unsigned origin=0;origin<2;origin++){
        const void *metadata=origin?dv:NULL;size_t n=origin?bytes:0;
        struct dvbridge_identity id={9,1,3};pl_tex matched=reference_texture(gpu->gl->gpu,W,H,NULL);
        assert(dvbridge_render_sdr_policy_direct_eligible(r,&p,&id,&imported.frame,metadata,n,1,1,g,matched,8));
        assert(dvbridge_render_hdr10_policy_direct(r,&p,&id,&imported.frame,metadata,n,1,1,g,matched,false,false,8));
        assert(dvbridge_render_policy_commit(r,&id,matched));
        struct dvbridge_hdr10_policy_output accepted;assert(dvbridge_render_policy_committed(r,&accepted));
        ++id.picture;
        for(unsigned size=0;size<4;size++){
            pl_tex invalid=reference_texture(gpu->gl->gpu,sizes[size][0],sizes[size][1],NULL);
            struct pl_frame saved=imported.frame;
            assert(!dvbridge_render_sdr_policy_direct_eligible(r,&p,&id,&imported.frame,metadata,n,1,1,g,invalid,8));
            assert(!memcmp(&saved,&imported.frame,sizeof(saved)));
            assert(!dvbridge_render_hdr10_policy_direct(r,&p,&id,&imported.frame,metadata,n,1,1,g,invalid,false,false,8));
            assert(!dvbridge_render_policy_output(r));
            struct dvbridge_hdr10_policy_output after;assert(dvbridge_render_policy_committed(r,&after));
            assert(dvbridge_identity_equal(&accepted.identity,&after.identity)&&after.final_target==matched);
            printf("RASTER NORMAL %s %dx%d rejected retained\n",origin?"DV":"raw",sizes[size][0],sizes[size][1]);
            ++cases;pl_tex_destroy(gpu->gl->gpu,&invalid);
        }
        pl_tex_destroy(gpu->gl->gpu,&matched);
    }
    assert(cases==8);printf("COMPLETE %u registered raster rejections\n",cases);
    av_free(dv);dvbridge_gl_frame_release(&imported);glDeleteTextures(3,planes.textures);
}
static void direct_regression(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *staged=dvbridge_renderer_create(gpu.gl->gpu),*direct=dvbridge_renderer_create(gpu.gl->gpu);assert(staged&&direct);
    const struct dvbridge_sdr_profile profiles[]={{DVBRIDGE_SDR_REFERENCE},{DVBRIDGE_SDR_BRIGHT},
        {DVBRIDGE_SDR_CUSTOM,20,1.8,0},{DVBRIDGE_SDR_CUSTOM,500,2.8,5},{DVBRIDGE_SDR_CUSTOM,100,2.3,.02}};
    const unsigned chromas[]={PL_CHROMA_LEFT,PL_CHROMA_TOP_LEFT,PL_CHROMA_CENTER};
    for(unsigned layout=0;layout<7;layout++)for(unsigned full=0;full<2;full++)
    for(unsigned c=0;c<3;c++)for(unsigned processing=0;processing<2;processing++)for(unsigned p=0;p<5;p++){
        dvbridge_renderer_set_processing_optimizations(staged,processing);dvbridge_renderer_set_processing_optimizations(direct,processing);
        native_pair(&gpu,staged,direct,layout,full,chromas[c],&profiles[p],false,16,false,false,NULL,0,false);
    }
    dvbridge_renderer_set_processing_optimizations(staged,false);dvbridge_renderer_set_processing_optimizations(direct,false);
    const unsigned depths[]={8,10,12,16};
    for(unsigned d=0;d<4;d++)for(unsigned limited=0;limited<2;limited++)
    for(unsigned flip=0;flip<2;flip++)for(unsigned p=0;p<5;p++)
        native_pair(&gpu,staged,direct,DVBRIDGE_P010,false,PL_CHROMA_LEFT,&profiles[p],true,depths[d],limited,flip,NULL,0,false);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    /* Original clamp boundary, with saturated/negative reconstructed channels. */
    float boundary[N];
    for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
        unsigned i=4*(y*W+x);float v=x/255.f;
        boundary[i]=v;boundary[i+1]=y%4==0?v:y%4==1?.25f:y%4==2?.5f:.75f;
        boundary[i+2]=y%4==0?v:1-v;boundary[i+3]=1;
    }
    pl_tex input=reference_texture(gpu.gl->gpu,W,H,boundary);struct pl_frame frame=reference_frame(input,W,H);frame.repr.alpha=PL_ALPHA_NONE;
    for(unsigned p=0;p<5;p++)paired(&gpu,staged,direct,&frame,m,bytes,&profiles[p],false,16,false,false);
    pl_tex_destroy(gpu.gl->gpu,&input);
    av_dovi_get_header(m)->vdr_bit_depth=12;
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    static float controls[3][2][5][N];
    for(unsigned variant=0;variant<5;variant++)for(unsigned processing=0;processing<2;processing++)for(unsigned p=0;p<5;p++){
        bool fel=variant>=3,mmr=variant==2||variant==4;av_dovi_get_header(m)->disable_residual_flag=!fel;
        for(unsigned c=0;c<3;c++){
            AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[c];memset(curve,0,sizeof(*curve));curve->num_pivots=2;curve->pivots[1]=1023;
            curve->mapping_idc[0]=mmr?AV_DOVI_MAPPING_MMR:AV_DOVI_MAPPING_POLYNOMIAL;
            curve->poly_order[0]=variant?2:1;curve->poly_coef[0][1]=variant?3500:4096;curve->poly_coef[0][2]=variant?512:0;
            if(mmr){curve->mmr_order[0]=2;curve->mmr_constant[0]=128;
                for(int order=0;order<2;order++)for(int axis=0;axis<7;axis++)curve->mmr_coef[0][order][axis]=(axis&1?-1:1)*(25+axis*7+order*13);
                curve->mmr_coef[0][0][c]+=3000;}
            av_dovi_get_mapping(m)->nlq[c].nlq_offset=512;av_dovi_get_mapping(m)->nlq[c].linear_deadzone_slope=4;av_dovi_get_mapping(m)->nlq[c].vdr_in_max=4096;
        }
        dvbridge_renderer_set_processing_optimizations(staged,processing);dvbridge_renderer_set_processing_optimizations(direct,processing);
        native_pair(&gpu,staged,direct,DVBRIDGE_P010,false,PL_CHROMA_LEFT,&profiles[p],false,16,false,false,m,bytes,fel);
        if(variant){
            unsigned changed=0;const float *control=controls[variant>=3?variant-2:0][processing][p];
            for(unsigned i=0;i<N;i++)if(i%4!=3&&last_expected[i]>0&&last_expected[i]<1&&
                fabsf(last_expected[i]-control[i])>2e-6f)changed++;
            assert(changed>100); /* Reshape and FEL must change interior pixels. */
        }
        if(variant<3)memcpy(controls[variant][processing][p],last_expected,sizeof(last_expected));
    }
    av_free(m);assert(comparisons==555);printf("COMPLETE %u staged/direct SDR comparisons\n",comparisons);
    raster_regression(&gpu,direct);
    dvbridge_renderer_destroy(staged);dvbridge_renderer_destroy(direct);reference_gpu_destroy(&gpu);
}

#ifndef DVBRIDGE_SDR_POLICY_API
extern bool dvbridge_render_sdr_policy_rgb(struct dvbridge_renderer *,const struct dvbridge_policy *,
 const struct dvbridge_identity *,const struct pl_frame *,const void *,size_t,double,double,
 struct dvbridge_geometry) __attribute__((weak));
#endif
int main(void)
{
    /* Missing implementation must fail as behavior, not a compiler error. */
    assert(dvbridge_render_sdr_policy_rgb);
#ifdef DVBRIDGE_SDR_POLICY_API
    struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    double peak,gamma,black;
    assert(dvbridge_sdr_target(&p.sdr,&peak,&gamma,&black) && peak==100 && gamma==2.4 && black==0);
    p.sdr.preset=DVBRIDGE_SDR_BRIGHT;
    assert(dvbridge_sdr_target(&p.sdr,&peak,&gamma,&black) && peak==200 && gamma==2.2);
    p.sdr=(struct dvbridge_sdr_profile){DVBRIDGE_SDR_CUSTOM,80,2.6,.02};
    assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_VALID);
    p.sdr.gamma=NAN;assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_INVALID_VALUE);
    p.sdr.gamma=2.6;p.sdr.black_nits=INFINITY;
    assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_INVALID_VALUE);
    p.sdr=(struct dvbridge_sdr_profile){0};
    assert(CB1_DV_SDR==14 && CB1_HDR10_SDR==15 && CB1_HLG_DV_REFERENCE==16);
    assert(cb1_circuit_version(CB1_DV_SDR));
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    const float pixels[]={.5,.5,.5,1, .75,.75,.75,1, .1,.1,.1,1, .9,.2,.1,1};
    pl_tex input=reference_texture(gpu.gl->gpu,2,2,pixels);
    pl_tex output=reference_texture(gpu.gl->gpu,2,2,NULL);
    struct pl_frame frame=reference_frame(input,2,2);
    frame.repr=pl_color_repr_rgb;
    frame.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.max_luma=1000}};
    const struct dvbridge_identity id={1,1,3};
    const struct dvbridge_geometry g={2,2,0,0,2,2,2,2};
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    const struct dvbridge_hdr10_policy_output *o=dvbridge_render_policy_output(r);assert(o);
    assert(o->container.primaries==PL_COLOR_PRIM_BT_709 && o->container.transfer==PL_COLOR_TRC_GAMMA24);
    assert(o->container.hdr.min_luma==PL_COLOR_HDR_BLACK); /* Zero means unknown to libplacebo. */
    assert(!o->hdr10.max_luminance && !o->resolved);
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));
    struct dvbridge_identity wrong=id;wrong.picture++;
    assert(!dvbridge_render_policy_commit(r,&wrong,output));
    assert(dvbridge_render_policy_commit(r,&id,output));
    float actual[16];reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    for(unsigned i=0;i<16;i++)assert(isfinite(actual[i]) && actual[i]>=0 && actual[i]<=1.001);
    assert(actual[0]>.1 && actual[0]<actual[4]);
    float static_hdr10[16];memcpy(static_hdr10,actual,sizeof(actual));
    frame.color.hdr.scene_max[0]=frame.color.hdr.scene_max[1]=frame.color.hdr.scene_max[2]=400;
    frame.color.hdr.scene_avg=100;
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));
    reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    float dynamic_effect=0;
    for(unsigned i=0;i<16;i++)dynamic_effect=fmaxf(dynamic_effect,fabs(actual[i]-static_hdr10[i]));
    assert(dynamic_effect>.005); /* Accepted HDR10+ MaxSCL/average guide SDR. */
    memset(frame.color.hdr.scene_max,0,sizeof(frame.color.hdr.scene_max));frame.color.hdr.scene_avg=0;
    /* Custom gamma transforms the signal inside its legal video range. */
    p.sdr=(struct dvbridge_sdr_profile){DVBRIDGE_SDR_CUSTOM,100,2.4,0};
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,true,10));
    float gamma24[16];reference_read(gpu.gl->gpu,output,0,0,2,2,gamma24);
    p.sdr.gamma=2.3;
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,true,10));
    reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    for(unsigned i=0;i<16;i++)if(i%4!=3){
        double offset=64./1023,span=876./1023;
        double want=offset+span*pow(fmax(0,(gamma24[i]-offset)/span),2.4/2.3);
        assert(fabs(actual[i]-want)<.002);
    }
    p.sdr=(struct dvbridge_sdr_profile){0};
    struct pl_frame hlg=frame;
    hlg.color.transfer=PL_COLOR_TRC_HLG;
    hlg.color.hdr=(struct pl_hdr_metadata){0};
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&hlg,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,10));
    assert(dvbridge_render_policy_commit(r,&id,output));
    reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    assert(actual[8]<actual[0] && actual[0]<actual[4]);
    for(unsigned i=0;i<3;i++){
        assert(fabsf(actual[i]-actual[0])<.002f);
        assert(fabsf(actual[4+i]-actual[4])<.002f);
    }
    assert(actual[12]>actual[13] && actual[13]>actual[14]);
    hlg_native_sdr(&gpu,r);
    /* Independently reconstructed DV must map exactly like its complete RGB
     * image. Exercise a real non-neutral FEL and HLG-base DV source tags. */
    size_t dvbytes;AVDOVIMetadata *dv=task3_fixture(&dvbytes);
    pl_renderer oracle=pl_renderer_create(NULL,gpu.gl->gpu);assert(oracle);
    const float residual[]={.6,.6,.6,1,.7,.7,.7,1,.55,.55,.55,1,.6,.6,.6,1};
    pl_tex et=reference_texture(gpu.gl->gpu,2,2,residual);
    struct pl_frame enhancement=reference_frame(et,2,2),dvframe=frame;
    dvframe.repr=(struct pl_color_repr){0};dvframe.color.transfer=PL_COLOR_TRC_HLG;
    float without_fel[16];
    for(unsigned fel=0;fel<2;fel++){
        av_dovi_get_header(dv)->disable_residual_flag=!fel;
        dvframe.enhancement_layer=fel?&enhancement:NULL;
        AVDOVIDataMapping *mapping=av_dovi_get_mapping(dv);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(unsigned c=0;c<3;c++){
            mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;
            mapping->nlq[c].vdr_in_max=1023*4096;
        }
        struct dvbridge_color mapped;assert(dvbridge_map_color(&mapped,dv,dvbytes,fel));
        pl_tex reconstructed_tex=reference_texture(gpu.gl->gpu,2,2,NULL);
        struct pl_frame oracle_source=dvframe;oracle_source.repr=mapped.repr;oracle_source.color=mapped.color;
        struct pl_frame oracle_target=reference_frame(reconstructed_tex,2,2);
        oracle_target.repr=pl_color_repr_rgb;oracle_target.color=mapped.color;
        struct pl_render_params params=pl_render_default_params;params.min_fbo_precision=32;
        params.peak_detect_params=NULL;params.dither_params=NULL;
        assert(pl_render_image(oracle,&oracle_source,&oracle_target,&params));
        struct pl_frame plain=reference_frame(reconstructed_tex,2,2);plain.repr=pl_color_repr_rgb;plain.color=mapped.color;
        assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&plain,NULL,0,1,1,g));
        assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,10));
        float expected[16];reference_read(gpu.gl->gpu,output,0,0,2,2,expected);
        assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&dvframe,dv,dvbytes,1,1,g));
        assert(dvbridge_render_policy_output(r)->fel_reconstructed==!!fel);
        assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,10));
        reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
        float fel_effect=0;
        for(unsigned i=0;i<16;i++){
            assert(fabs(actual[i]-expected[i])<.002);
            if(fel)fel_effect=fmaxf(fel_effect,fabs(actual[i]-without_fel[i]));
        }
        if(fel)assert(fel_effect>.002);else memcpy(without_fel,actual,sizeof(actual));
        pl_tex_destroy(gpu.gl->gpu,&reconstructed_tex);
    }
    pl_renderer_destroy(&oracle);pl_tex_destroy(gpu.gl->gpu,&et);av_free(dv);
    /* A mismatched FEL must reject the whole picture and clear pending output. */
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    struct pl_frame el=frame;frame.enhancement_layer=&el;
    av_dovi_get_header(m)->disable_residual_flag=0;
    assert(!dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,m,bytes,1,2,g));
    assert(!dvbridge_render_policy_output(r));av_free(m);
    frame.enhancement_layer=NULL;frame.color.hdr.max_luma=NAN;
    assert(!dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,1,1,g));
    assert(!dvbridge_render_policy_output(r));
    dvbridge_renderer_destroy(r);
    pl_tex_destroy(gpu.gl->gpu,&input);pl_tex_destroy(gpu.gl->gpu,&output);reference_gpu_destroy(&gpu);
#endif
    direct_regression();
    return 0;
}
