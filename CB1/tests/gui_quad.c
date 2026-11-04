/* SPDX-License-Identifier: MIT */
/* Execute the real Master GUI pack hook; film and metadata must stay exact. */
#include "reference_test.h"
#include "dvbridge_render.c"
#include <time.h>

static double clock_ms(void)
{
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    return 1000.0*t.tv_sec+t.tv_nsec/1000000.0;
}

int main(int argc,char **argv)
{
    bool stress=argc>1 && !strcmp(argv[1],"stress");
    bool black=argc>1 && !strcmp(argv[1],"black");
    bool full=argc>1 && !stress;
    bool standard=argc>2 && !strcmp(argv[2],"standard");
    bool rgb=argc>2 && !strcmp(argv[2],"rgb");
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(g.gl->gpu);assert(renderer);
    bool quad=renderer->fragment_quad;dvbridge_renderer_destroy(renderer);
    if(!quad){
        reference_gpu_destroy(&g);return 77;
    }
    const int w=full?3840:128,h=full?2160:64;
    size_t pixels=(size_t)w*h,bytes=pixels*4;
    float *data=malloc(pixels*4*sizeof(float));assert(data);
    for(size_t i=0;i<pixels;i++)for(unsigned c=0;c<4;c++)
        data[4*i+c]=c==3?1:(float)((i*(17+c*13)+c*971)%65536)/65535;
    pl_tex input=reference_texture(g.gl->gpu,w,h,data);
    for(size_t i=0;i<pixels;i++){
        float a=i/w<(unsigned)h/4 || i/w>(unsigned)h*3/4 ? (float)((stress?i:i/2)%5)/4 : 0;
        data[4*i]=.24f*a;data[4*i+1]=.36f*a;data[4*i+2]=.12f*a;data[4*i+3]=a;
        if(stress)for(unsigned c=0;c<3;c++)data[4*i+c]=a*(float)((i*(17+c*13)+c*971)%256)/255;
        if(black)data[4*i]=data[4*i+1]=data[4*i+2]=0;
    }
    pl_tex gui=reference_texture(g.gl->gpu,w,h,data);free(data);
    float table[256*4];
    for(unsigned i=0;i<256;i++)for(unsigned c=0;c<4;c++){
        float x=(float)i/255;
        table[4*i+c]=c==3?1:x<=.04045f?x/12.92f:powf((x+.055f)/1.055f,2.4f);
    }
    pl_tex degamma=reference_texture(g.gl->gpu,256,1,table);
    for(unsigned i=0;i<256;i++)for(unsigned c=0;c<4;c++)table[4*i+c]=c==3?1:dv_ideal_pq(203.0*i/255);
    pl_tex pq=reference_texture(g.gl->gpu,256,1,table);
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=w,.h=h,
        .format=pl_find_named_fmt(g.gl->gpu,"rgba8"),.renderable=true));assert(output);
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=degamma,.pq=pq,.rect={0,0,w,h}};
    uint32_t words[128];for(unsigned i=0;i<128;i++)words[i]=(i*173+71)&255;
    pl_dispatch dispatch=pl_dispatch_create(g.log,g.gl->gpu);
    unsigned char *baseline=malloc(bytes),*result=malloc(bytes);assert(baseline && result);
    for(unsigned variant=0;variant<2;variant++){
        double started=0;
        for(unsigned run=0;run<(full?22u:2u);run++){
            if(run==2)started=clock_ms();
            struct active_mask mask={.source_domain=!rgb,.reference_transport=!standard && !rgb,
                .source_overlay=!rgb,.straight_overlay=rgb,.gui_quad=variant!=0,.overlay=&overlay,
                .rect={0,0,w,h},.raster={w,h},.packets=words,.count=1};
            if(stress){mask.flip=1;memcpy(overlay.rect,(float[4]){2,7,w-4,h-9},sizeof(overlay.rect));}
            for(unsigned i=0;i<3;i++){
                mask.nonlinear[4*i]=.95f;mask.linear[4*i]=.9f;mask.offset[i]=.001f*(i+1);
            }
            pl_shader shader=pl_dispatch_begin(dispatch);
            assert(pl_shader_sample_direct(shader,pl_sample_src(.tex=input)));
            struct pl_hook_params params={.stage=PL_HOOK_OUTPUT,.sh=shader};
            assert(!pack_active_area(&mask,&params).failed);
            assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=output)));
            glFinish();
        }
        if(full)fprintf(stderr,"GUI %s: %.4f ms/frame\n",variant?"quad":"legacy",(clock_ms()-started)/20);
        GLuint fbo;pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,&fbo);assert(fbo);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,variant?result:baseline);
        assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
    }
    unsigned changed=0,outside=0,max_y=0,max_c=0,transparent_y=0;
    for(size_t i=0;i<pixels;i++){
        size_t j=(stress?i/w:(size_t)h-1-i/w)*w+i%w;
        bool band=j/w<(unsigned)h/4 || j/w>(unsigned)h*3/4;
        bool own=band && ((stress?j:j/2)%5);
        bool covered=own || (band && ((stress?(j^1):(j^1)/2)%5));
        size_t packed=(stress?(size_t)h-1-i/w:i/w)*w+i%w;
        if(stress){
            bool inside=i%w>=2 && i%w<(unsigned)w-4 && packed/w>=7 && packed/w<(unsigned)h-9;
            own=own && inside;covered=covered && inside;
        }
        for(unsigned k=0;k<4;k++)if(baseline[4*i+k]!=result[4*i+k]){
            ++changed;if(!covered)++outside;
        }
        unsigned y[2],c[2];
        for(unsigned v=0;v<2;v++){
            const unsigned char *p=(v?result:baseline)+4*i;
            y[v]=(p[1]<<4)|(p[2]&15);c[v]=(p[0]<<4)|(p[2]>>4);
            assert(p[3]==255);
            if(packed<3072){
                unsigned parity=(unsigned)__builtin_popcount((c[v]>>1)^y[v])&1;
                unsigned bit=(words[(packed%1024)/8]>>(7-packed%8))&1;
                assert(((c[v]&1)^parity)==bit);
            }
        }
        unsigned dy=abs((int)y[1]-(int)y[0]),dc=abs((int)c[1]-(int)c[0]);
        if(!own && dy)++transparent_y;
        if(dy>max_y)max_y=dy;if(dc>max_c)max_c=dc;
    }
    fprintf(stderr,"GUI quad: %zu carrier bytes, %u changed, %u outside GUI; max 12-bit GUI Y/C %u/%u\n",
        bytes,changed,outside,max_y,max_c);
    assert(!outside && !transparent_y && max_y<=1 && max_c<=2);
    free(baseline);free(result);pl_dispatch_destroy(&dispatch);
    pl_tex_destroy(g.gl->gpu,&output);pl_tex_destroy(g.gl->gpu,&gui);
    pl_tex_destroy(g.gl->gpu,&degamma);pl_tex_destroy(g.gl->gpu,&pq);pl_tex_destroy(g.gl->gpu,&input);
    reference_gpu_destroy(&g);
    return 0;
}
