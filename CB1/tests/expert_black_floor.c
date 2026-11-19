/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_placebo.h"
#include "dvbridge_render.h"
#include <libplacebo/opengl.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static double st2084(double luminance)
{
    double v=pow(luminance/10000,2610.0/16384);
    return pow((3424.0/4096+(2413.0/128)*v)/(1+(2392.0/128)*v),2523.0/32);
}

int main(void)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint size[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLConfig config;EGLint count;
    assert(eglChooseConfig(display,attributes,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(display,config,size);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=display,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(gl->gpu);assert(renderer);
    const double nits[]={0,.0001,.001,.005,.01,.025,.05,.1,.25,.5,1,2,5,10,100,1000};
    float pixels[64];
    for(unsigned i=0;i<16;i++)for(unsigned c=0;c<4;c++)pixels[4*i+c]=c==3?1:st2084(nits[i]);
    pl_fmt format=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(format);
    pl_tex texture=pl_tex_create(gl->gpu,pl_tex_params(.w=16,.h=1,.format=format,
        .sampleable=true,.renderable=true,.initial_data=pixels));assert(texture);
    struct pl_frame frame={.num_planes=1,.planes={{.texture=texture,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,16,1}};
    size_t bytes;AVDOVIMetadata *metadata=av_dovi_metadata_alloc(&bytes);assert(metadata);
    AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    header->disable_residual_flag=1;header->bl_bit_depth=header->el_bit_depth=10;header->coef_log2_denom=12;
    AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    color->signal_eotf=65535;color->source_min_pq=7;color->source_max_pq=3079;
    for(unsigned row=0;row<3;row++){
        color->ycc_to_rgb_offset[row]=(AVRational){0,1};
        for(unsigned col=0;col<3;col++)color->ycc_to_rgb_matrix[3*row+col]=
            color->rgb_to_lms_matrix[3*row+col]=(AVRational){row==col,1};
        AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(metadata)->curves[row];
        curve->num_pivots=2;curve->pivots[1]=1023;curve->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0]=1;curve->poly_coef[0][1]=4096;
    }
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3079,.avg_pq=1500}};
    *av_dovi_get_ext(metadata,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={2500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    unsigned minima[]={0,1,100,1000};
    for(unsigned trims=0;trims<2;trims++)for(unsigned i=0;i<4;i++){
        metadata->num_ext_blocks=2+trims;
        *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=6,
            .l6={.max_luminance=1000,.min_luminance=minima[i]}};
        void *saved=av_memdup(metadata,bytes);assert(saved);
        struct dvbridge_identity identity={1,1+4*trims+i,1};
        assert(dvbridge_render_hdr10_policy_rgb(renderer,&policy,&identity,&frame,metadata,bytes,0,0,
            (struct dvbridge_geometry){16,1,0,0,16,1}));
        GLuint output=pl_opengl_unwrap(gl->gpu,dvbridge_render_texture(renderer),NULL,NULL,NULL),fbo;
        assert(output);glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,output,0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
        float actual[64];glReadPixels(0,0,16,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        for(unsigned sample=0;sample<16;sample++)for(unsigned channel=0;channel<3;channel++){
            double expected=sample?st2084(nits[sample]):0;
            if(fabs(actual[4*sample+channel]-expected)>5e-5)
                fprintf(stderr,"Expert black floor: mastering_min=%u trims=%u input_nits=%g expectedPQ=%.9f got=%.9f\n",
                    minima[i],trims,nits[sample],expected,actual[4*sample+channel]);
            assert(fabs(actual[4*sample+channel]-expected)<=5e-5);
        }
        assert(!memcmp(saved,metadata,bytes));av_free(saved);
        struct dvbridge_policy other=policy;other.mode=DVBRIDGE_MODE_ENHANCED_DV;
        struct dvbridge_color mapped;struct pl_color_space target;struct dvbridge_hdr10_metadata signal;
        assert(dvbridge_reference_map(&mapped,&target,&signal,&other,metadata,bytes,false));
        assert(fabs(mapped.color.hdr.min_luma-minima[i]/10000.0)<1e-8);
    }
    const double peaks[]={50,600,1000,2000,10000},blacks[]={0,.0001,.005,.05,.5};
    unsigned cases=0;
    double maximum_reversal=0,maximum_identity=0;
    metadata->num_ext_blocks=1;
    for(unsigned pi=0;pi<5;pi++)for(unsigned bi=0;bi<5;bi++)
        for(int gamut=DVBRIDGE_GAMUT_BT709;gamut<=DVBRIDGE_GAMUT_BT2020;gamut++){
            policy.tv.peak_nits=peaks[pi];policy.expert_black_nits=blacks[bi];policy.tv.gamut=gamut;
            struct dvbridge_identity identity={2,++cases,policy.revision};
            assert(dvbridge_render_hdr10_policy_rgb(renderer,&policy,&identity,&frame,metadata,bytes,0,0,
                (struct dvbridge_geometry){16,1,0,0,16,1}));
            pl_tex result=dvbridge_render_texture(renderer);
            GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
                pl_opengl_unwrap(gl->gpu,result,NULL,NULL,NULL),0);
            float actual[64];glReadPixels(0,0,16,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
            glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
            for(unsigned c=0;c<3;c++){
                assert(fabs(actual[c]-(blacks[bi]?st2084(blacks[bi]):0))<2e-4);
                for(unsigned i=0;i<16;i++){
                    assert(isfinite(actual[4*i+c]) && actual[4*i+c]>=0);
                    assert(actual[4*i+c]<=st2084(peaks[pi])+1e-6);
                    if(i){
                        maximum_reversal=fmax(maximum_reversal,actual[4*(i-1)+c]-actual[4*i+c]);
                        assert(actual[4*i+c]+1.0/4095>=actual[4*(i-1)+c]);
                    }
                    if(peaks[pi]>1001){
                        double expected=st2084(fmax(nits[i],blacks[bi]));
                        maximum_identity=fmax(maximum_identity,fabs(actual[4*i+c]-expected));
                        if(fabs(actual[4*i+c]-expected)>=1.0/4095)
                            fprintf(stderr,"sourcefits P=%g B=%g G=%d input=%g actualPQ=%.9g expectedPQ=%.9g\n",
                                peaks[pi],blacks[bi],gamut,nits[i],actual[4*i+c],expected);
                        assert(fabs(actual[4*i+c]-expected)<1.0/4095);
                    }
                }
            }
            const struct dvbridge_hdr10_policy_output *output=dvbridge_render_policy_output(renderer);
            assert(output && output->hdr10.min_luminance==lround(blacks[bi]*10000));
            assert(output->hdr10.max_luminance==ceil(peaks[pi]) && !output->hdr10.max_cll && !output->hdr10.max_fall);
        }
    /* Signed creative controls must not introduce a shadow plateau or move
     * the black endpoint. This fails against the former linear RGB SOP. */
    metadata->num_ext_blocks=2;
    av_dovi_get_ext(metadata,0)->l1.max_pq=3078;
    policy.tv.peak_nits=2000;policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;policy.expert_black_nits=0;
    const unsigned signed_words[][3]={
        {2048,2048,2048},{2048,2045,2048},{2048,2062,2048},
        {0,0,0},{0,0,4095},{0,4095,0},{0,4095,4095},
        {4095,0,0},{4095,0,4095},{4095,4095,0},{4095,4095,4095},
        {2048,2048,2048},{0,0,0}};
    /* Independently calculated PQ values at100 nits for the public anchored
     * polynomial, P2000/B0. Also catches stale LUTs when only a trim changes. */
    const double expected_pq100[]={.508078421517,.508052147629,.508201032996,
        .505660541171,.417572026141,.541524398588,.453435883558,
        .562719778871,.474631263841,.598583636288,.510495121258,
        .508078421517,.505660541171};
    for(unsigned t=0;t<sizeof(signed_words)/sizeof(*signed_words);t++){
        *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3389,
            .trim_slope=signed_words[t][0],.trim_offset=signed_words[t][1],
            .trim_power=signed_words[t][2],.trim_chroma_weight=2048,
            .trim_saturation_gain=2048,.ms_weight=-1}};
        struct dvbridge_identity identity={3,t+1,1};
        assert(dvbridge_render_hdr10_policy_rgb(renderer,&policy,&identity,&frame,metadata,bytes,0,0,
            (struct dvbridge_geometry){16,1,0,0,16,1}));
        GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
            pl_opengl_unwrap(gl->gpu,dvbridge_render_texture(renderer),NULL,NULL,NULL),0);
        float actual[64];glReadPixels(0,0,16,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        for(unsigned c=0;c<3;c++){
            if(actual[c]!=0)fprintf(stderr,"Expert signed trim %u moves black to PQ %.9g\n",t,actual[c]);
            assert(actual[c]==0);
            if(fabs(actual[4*14+c]-expected_pq100[t])*4095>=1)
                fprintf(stderr,"Expert curve/cache trim=%u q100=%.9g expected=%.9g\n",t,actual[4*14+c],expected_pq100[t]);
            assert(fabs(actual[4*14+c]-expected_pq100[t])*4095<1);
            for(unsigned i=1;i<16;i++){
                if(actual[4*i+c]<=0)fprintf(stderr,"Expert signed trim %u loses shadow at %.9g nits\n",t,nits[i]);
                assert(isfinite(actual[4*i+c]) && actual[4*i+c]>0);
                assert(actual[4*i+c]+1.0/4095>=actual[4*(i-1)+c]);
                assert(actual[4*i+c]<=st2084(2000));
            }
        }
    }
    puts("PASS signed Expert curves keep black fixed and sampled shadows positive, bounded, monotone within1PQ12");
    printf("PASS %u runtime peak/physical-black/gamut plans; max rounding reversal %.9g PQ12, identity error %.9g PQ12; bounded\n",
        cases,maximum_reversal*4095,maximum_identity*4095);
    av_free(metadata);pl_tex_destroy(gl->gpu,&texture);dvbridge_renderer_destroy(renderer);pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
    puts("PASS Expert preserves absolute-PQ near-black independently of L6 mastering minimum");
}
