/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_ai.h"
#include <libavutil/dovi_meta.h>
#include <time.h>
static void retire(struct dvbridge_renderer *r)
{
    dvbridge_render_dv_policy_cancel(r);
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_IDLE)return;
        assert(status==DVBRIDGE_DV_BUSY || status==DVBRIDGE_DV_PENDING);
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"retirement timed out");
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    if(!pl_opengl_has_ext(g.gl,"GL_KHR_shader_subgroup")){reference_gpu_destroy(&g);return 77;}
    GLint size=0,stages=0,features=0;
    glGetIntegerv(0x9532,&size);glGetIntegerv(0x9533,&stages);glGetIntegerv(0x9534,&features);
    if(size<4 || !(stages&GL_FRAGMENT_SHADER_BIT) || (features&0x81)!=0x81){reference_gpu_destroy(&g);return 77;}
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    pl_fmt format=pl_find_fmt(gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_HOST_READABLE);assert(format);
    pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=format,.renderable=true,.host_readable=true));assert(target);
    unsigned fbo;assert(pl_opengl_unwrap(gpu,target,NULL,NULL,&fbo));
    const size_t bytes=(size_t)3840*2160*4;uint8_t *expected=malloc(bytes),*actual=malloc(bytes);assert(expected && actual);
    struct cb1_ai_result prediction={.id={1,1,1},.pts=0,.raw={.l1_min=0,.l1_max=3000,.l1_avg=1000,.l3_min=2048,.l3_max=2048,.l3_avg=2048}};
    const struct dvbridge_policy policy={.mode=DVBRIDGE_MODE_STANDARD,.revision=1};
    const struct dvbridge_geometry cases[]={{3840,1600,0,280,3840,1600},{3840,1920,0,120,3840,1920},{1440,1080,1200,540,1440,1080},{1920,800,0,280,3840,1600}};
    for(unsigned k=0;k<6;k++){
        const struct dvbridge_geometry geometry=cases[k<4?k:0];
        const size_t n=(size_t)geometry.source_width*geometry.source_height;
        float *pixels=malloc(n*4*sizeof(float));assert(pixels);
        for(size_t i=0;i<n;i++)for(unsigned c=0;c<4;c++)
            pixels[i*4+c]=c==3?1:(float)((i*31+c*97)%1024)/1023;
        if(k<3)for(int y=geometry.source_height/2-4;y<=geometry.source_height/2+4;y++)
            for(int x=geometry.source_width/2-4;x<=geometry.source_width/2+4;x++)
                memcpy(pixels+((size_t)y*geometry.source_width+x)*4,(float[]){.25f,.5f,.75f,1},4*sizeof(float));
        pl_tex input=reference_texture(gpu,geometry.source_width,geometry.source_height,pixels);free(pixels);
        struct pl_frame source=reference_frame(input,geometry.source_width,geometry.source_height);
        source.repr=pl_color_repr_rgb;source.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ};
        if(k>=4){
            pl_tex_destroy(gpu,&input);unsigned depth=k==4?10:12,shift=k==4?6:0;
            source.num_planes=2;
            source.repr=(struct pl_color_repr){.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
                .bits={.sample_depth=16,.color_depth=depth,.bit_shift=shift}};
            for(unsigned p=0;p<2;p++){
                int w=p?1920:3840,h=p?800:1600,c=p?2:1;
                uint16_t *words=malloc((size_t)w*h*c*2);assert(words);
                for(int i=0;i<w*h*c;i++)words[i]=((p?480+i%65:64+i%877)<<(depth-10))<<shift;
                pl_fmt format=pl_find_fmt(gpu,PL_FMT_UNORM,c,16,16,PL_FMT_CAP_SAMPLEABLE);assert(format);
                source.planes[p]=(struct pl_plane){.components=c,.component_mapping={p,p+1},
                    .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=format,.sampleable=true,.initial_data=words))};
                free(words);assert(source.planes[p].texture);
            }
        }
        for(unsigned flip=0;flip<2;flip++){
            assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
            assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
            assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=expected)));retire(r);
            if(k==3){
                assert(!dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,&source,&geometry,target,fbo,flip));
                assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=actual)));
                assert(!memcmp(expected,actual,bytes));
                continue;
            }
            dvbridge_renderer_set_optimized_dv(r,false);
            assert(!dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,&source,&geometry,target,fbo,flip));
            dvbridge_renderer_set_optimized_dv(r,true);
            assert(dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,&source,&geometry,target,fbo,flip) && "Letterboxed AI must use fused output");
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out && !out->intermediate);
            const AVDOVIDmData *l5=av_dovi_find_level(out->output_metadata,5);assert(l5);
            assert(l5->l5.left_offset==geometry.x && l5->l5.top_offset==geometry.y);
            assert(out->value.l1[1]==3000 && out->value.l1[2]==1000);
            assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=actual)));
            for(unsigned y=0;y<2160;y++)for(unsigned x=0;x<3840;x++){
                unsigned logical_y=flip?2159-y:y;
                if(x>=(unsigned)geometry.x && x<(unsigned)(geometry.x+geometry.width) &&
                   logical_y>=(unsigned)geometry.y && logical_y<(unsigned)(geometry.y+geometry.height))continue;
                const uint8_t *pixel=actual+((size_t)y*3840+x)*4;
                assert(((pixel[1]<<4)|(pixel[2]&15))==256);
                assert((((pixel[0]<<4)|(pixel[2]>>4))&~1)==2048 && pixel[3]==255);
            }
            unsigned cx=geometry.x+geometry.width/2,cy=geometry.y+geometry.height/2;
            if(flip)cy=2159-cy;
            const uint8_t *center=actual+((size_t)cy*3840+cx)*4;
            if(k<3){
                assert(((center[1]<<4)|(center[2]&15))==1830);
                assert(((center[0]<<4)|(center[2]>>4))==2621);
                assert(((center[4]<<4)|(center[6]>>4))==1564);
            }else assert(((center[1]<<4)|(center[2]&15))>256);
            unsigned max=0;size_t changed=0;
            for(size_t i=0;i<bytes;i++) {unsigned diff=abs((int)expected[i]-actual[i]);if(diff>max)max=diff;changed+=diff!=0;}
            unsigned max_y=0,max_c=0;size_t changed_y=0,changed_c=0;
            for(size_t i=0;i<bytes;i+=4){
                int y0=(expected[i+1]<<4)|(expected[i+2]&15),y1=(actual[i+1]<<4)|(actual[i+2]&15);
                int c0=(expected[i]<<4)|(expected[i+2]>>4),c1=(actual[i]<<4)|(actual[i+2]>>4);
                unsigned dy=abs(y0-y1),dc=abs(c0-c1);
                if(dy>max_y)max_y=dy;
                if(dc>max_c)max_c=dc;
                changed_y+=dy!=0;changed_c+=dc!=0;
            }
            printf("decoded luma_max=%u chroma_max=%u luma_changed=%zu chroma_changed=%zu\n",max_y,max_c,changed_y,changed_c);
            printf("case=%u flip=%u changed=%zu max_transport_byte=%u\n",k,flip,changed,max);
            if(changed){
                unsigned shown=0;
                for(size_t i=0;i<bytes && shown<8;i++)if(expected[i]!=actual[i]){
                    printf("pixel=%zu,%zu channel=%zu expected=%u actual=%u\n",(i/4)%3840,(i/4)/3840,i%4,expected[i],actual[i]);++shown;
                }
            }
            fflush(stdout);
            if(k<4)assert(!changed);
            else{
                /* Removing the FP32 store/load boundary can change a rounded video code by one. */
                assert(max_y<=1 && max_c<=1);
                for(unsigned y=0;y<2160;y++)if(y<280 || y>=1880)
                    assert(!memcmp(expected+(size_t)y*3840*4,actual+(size_t)y*3840*4,3840*4));
            }
            retire(r);
        }
        if(k>=4)for(unsigned p=0;p<2;p++)pl_tex_destroy(gpu,&source.planes[p].texture);
        else pl_tex_destroy(gpu,&input);
    }
    free(expected);free(actual);dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    pl_tex_destroy(gpu,&target);reference_gpu_destroy(&g);
}
