/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_ai.h"
#include <libavutil/dovi_meta.h>
#include <time.h>
#include "../src/dvbridge_render.c"
static GLenum pending_fence(GLsync fence,GLbitfield flags,GLuint64 timeout)
{(void)fence;(void)flags;(void)timeout;return GL_TIMEOUT_EXPIRED;}
static unsigned signal_uv(unsigned x,unsigned y,unsigned c)
{return 512+(x*3+y*7+c*11)%65;}
static unsigned signal_chroma(unsigned x,unsigned y,unsigned c)
{
    int col=x/2,row=y/2,other=(y&1)?(row<1079?row+1:row):(row?row-1:row);
    unsigned sum=0;
    for(int offset=-1;offset<=1;offset++){
        int k=col+offset;k=k<0?0:k>1919?1919:k;
        sum+=(offset?1:6)*(3*signal_uv(k,row,c)+signal_uv(k,other,c));
    }
    return (sum*4+16)/32;
}
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
static void ordered_pair(pl_gpu gpu,const struct pl_frame *source,struct dvbridge_geometry geometry)
{
    const size_t size=3840u*2160u*4;
    uint8_t *expected[2]={malloc(size),malloc(size)},*actual=malloc(size);assert(expected[0] && expected[1] && actual);
    void *metadata[2]={0};size_t metadata_bytes[2]={0};
    pl_tex targets[2];unsigned fbos[2];
    for(unsigned i=0;i<2;i++){
        targets[i]=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=pl_find_named_fmt(gpu,"rgba8"),
            .renderable=true,.host_readable=true));assert(targets[i]);
        assert(pl_opengl_unwrap(gpu,targets[i],NULL,NULL,&fbos[i]));
    }
    for(unsigned ordered=0;ordered<2;ordered++){
        struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
        struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
        dvbridge_renderer_set_optimized_dv(r,true);dvbridge_renderer_set_fast_chroma(r,true);
        const struct dvbridge_policy policy={.mode=DVBRIDGE_MODE_STANDARD,.revision=1};
        for(unsigned i=0;i<2;i++){
            struct cb1_ai_result prediction={.id={7,1+i,1},.pts=i/60.,
                .raw={.l1_max=3000-i*100,.l1_avg=1000+i*200,.l3_min=2048,.l3_max=2048,.l3_avg=2048}};
            assert(dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,source,&geometry,targets[i],fbos[i],false));
            assert(!r->rgb && "Packed Reference AI must not allocate an unused 4K FP32 backing");
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
            if(!ordered){metadata_bytes[i]=out->bytes;metadata[i]=av_memdup(out->output_metadata,out->bytes);assert(metadata[i]);}
            else assert(out->bytes==metadata_bytes[i] && !memcmp(out->output_metadata,metadata[i],out->bytes));
            assert(dvbridge_render_dv_policy_resolve(r,targets[i],fbos[i],false));
            struct dvbridge_identity id={7,1+i,1};
            assert(dvbridge_render_dv_policy_commit(r,&id,targets[i],out->resolve_serial));
            if(!ordered)retire(r);
            else if(!i){
                PFNGLCLIENTWAITSYNCPROC genuine=r->dv.wait_sync;r->dv.wait_sync=pending_fence;
                assert(dvbridge_render_dv_policy_advance(r)==DVBRIDGE_DV_IDLE);
                assert(r->retired_packed.active && !r->dv.active);
                r->retired_packed.wait_sync=genuine;
            }else{
                PFNGLCLIENTWAITSYNCPROC genuine=r->retired_packed.wait_sync;r->retired_packed.wait_sync=pending_fence;
                assert(dvbridge_render_dv_policy_advance(r)==DVBRIDGE_DV_BUSY);
                r->retired_packed.wait_sync=genuine;
            }
        }
        glFinish();retire(r);
        for(unsigned i=0;i<2;i++){
            assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=targets[i],.ptr=ordered?actual:expected[i])));
            if(ordered)assert(!memcmp(actual,expected[i],size));
        }
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    }
    assert(memcmp(expected[0],expected[1],size));
    for(unsigned i=0;i<2;i++){free(expected[i]);av_free(metadata[i]);pl_tex_destroy(gpu,&targets[i]);}
    free(actual);puts("PASS AI ordered retirement: exact distinct carriers and metadata, one retired slot");
}
static void rgb_scanout(struct dvbridge_renderer *r,pl_gpu gpu,const struct pl_frame *source,
    const struct dvbridge_policy *policy,const struct cb1_ai_result *prediction,
    const struct dvbridge_geometry *geometry,pl_tex rgba,unsigned framebuffer)
{
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,3,8,8,PL_FMT_CAP_RENDERABLE);assert(fmt);
    pl_tex rgb=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(rgb);
    unsigned fbo;assert(pl_opengl_unwrap(gpu,rgb,NULL,NULL,&fbo));
    const size_t size=3840u*2160*4;uint8_t *control=malloc(size),*actual=malloc(size);assert(control && actual);
    assert(dvbridge_render_hdr10_ai_packed(r,policy,prediction,source,geometry,rgba,framebuffer,false));
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    size_t bytes=out->bytes;void *metadata=av_memdup(out->output_metadata,bytes);assert(metadata);
    assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=rgba,.ptr=control)));retire(r);
    assert(dvbridge_render_hdr10_ai_packed(r,policy,prediction,source,geometry,rgb,fbo,false) &&
        "Reference AI must admit the real RGB8 scanout without requiring unused alpha");
    out=dvbridge_render_dv_policy_output(r);assert(out && out->bytes==bytes && !memcmp(metadata,out->output_metadata,bytes));
    assert(dvbridge_render_dv_policy_resolve(r,rgb,fbo,false));
    glBindFramebuffer(GL_READ_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,actual);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
    assert(!memcmp(actual,control,size));retire(r);
    av_free(metadata);free(control);free(actual);pl_tex_destroy(gpu,&rgb);
    puts("PASS Reference AI RGB8: identical complete carrier and metadata to RGBA8");
}
/* Native HDR10 codes must survive Reference AI without a clipped RGB roundtrip. */
static void native_signal(struct dvbridge_renderer *r,pl_gpu gpu,pl_tex target,unsigned fbo)
{
    bool previous=r->fast_chroma;dvbridge_renderer_set_fast_chroma(r,true);
    const size_t bytes=3840u*2160u*4;
    uint8_t *pixels=malloc(bytes),*control=malloc(bytes);assert(pixels && control);
    float lut[4]={0,0,0,1};
    pl_tex degamma=reference_texture(gpu,1,1,lut),pq=reference_texture(gpu,1,1,lut);assert(degamma && pq);
    const struct dvbridge_policy policy={.mode=DVBRIDGE_MODE_STANDARD,.revision=1};
    const struct dvbridge_geometry geometry={3840,2160,0,0,3840,2160};
    for(unsigned trial=0;trial<8;trial++){
        unsigned fixture=trial/2;bool flip=trial&1;
        unsigned depth=fixture&1?12:10,shift=fixture<2?16-depth:0;
        bool packed=fixture<3;
        struct pl_frame source={.num_planes=packed?2:3,.crop={0,0,3840,2160},
            .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
                .bits={16,depth,shift}},
            .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ}};
        for(unsigned p=0;p<source.num_planes;p++){
            unsigned w=p?1920:3840,h=p?1080:2160,c=p && packed?2:1;
            uint16_t *words=malloc((size_t)w*h*c*2);assert(words);
            for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned k=0;k<c;k++){
                unsigned q=p?signal_uv(x,y,packed?k:p-1):64+(x*13+y*7)%877;
                words[((size_t)y*w+x)*c+k]=(q<<(depth-10))<<shift;
            }
            pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,c,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
            source.planes[p]=(struct pl_plane){.components=c,.component_mapping={p,p+1},
                .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.format=fmt,.sampleable=true,.initial_data=words))};
            free(words);assert(source.planes[p].texture);
        }
        struct cb1_ai_result prediction={.id={18,trial+1,1},.pts=trial/60.,
            .raw={.l1_max=3000,.l1_avg=1000,.l3_min=2048,.l3_max=2048,.l3_avg=2048}};
        assert(dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,&source,&geometry,target,fbo,flip));
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));glFinish();
        const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
        assert(out && out->value.l1[1]==3000 && out->value.l1[2]==1000);
        assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=pixels)));
        unsigned max_y=0,max_c=0;
        /* Exclude transport metadata rows in either orientation. */
        for(unsigned y=8;y<2152;y++)for(unsigned x=0;x<3840;x++){
            unsigned row=flip?2159-y:y;
            const uint8_t *v=pixels+((size_t)y*3840+x)*4;
            unsigned dy=abs(((v[1]<<4)|(v[2]&15))-(int)(4*(64+(x*13+row*7)%877)));
            unsigned dc=abs(((v[0]<<4)|(v[2]>>4))-(int)signal_chroma(x,row,x&1));
            max_y=dy>max_y?dy:max_y;max_c=dc>max_c?dc:max_c;
        }
        printf("native HDR10 fixture=%u flip=%u maxY=%u maxC=%u\n",fixture,flip,max_y,max_c);fflush(stdout);
        assert(!max_y && max_c<=1);memcpy(control,pixels,bytes);retire(r);
        const struct dvbridge_native_overlay empty={.texture=source.planes[0].texture,.degamma=degamma,.pq=pq};
        assert(dvbridge_render_hdr10_ai_packed_overlay(r,&policy,&prediction,&source,&geometry,target,fbo,flip,&empty));
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
        assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=pixels)));
        assert(!memcmp(pixels,control,bytes) && "Empty GUI must preserve native HDR10 carrier and metadata");
        retire(r);
        struct dvbridge_policy identity=policy;
        identity.mode=DVBRIDGE_MODE_ENHANCED_DV;
        identity.tv=(struct dvbridge_tv_profile){2500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020};
        assert(dvbridge_render_hdr10_ai_packed(r,&identity,&prediction,&source,&geometry,target,fbo,flip) &&
            "An identity Adaptive plan must reuse Reference transport, without framebuffer fetch");
        assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
        out=dvbridge_render_dv_policy_output(r);assert(out);
        assert(out->value.policy.mode==DVBRIDGE_MODE_ENHANCED_DV &&
            out->value.expansion_reason==CB1_DVE_NO_HEADROOM && !out->value.measured && !out->intermediate);
        assert(pl_tex_download(gpu,pl_tex_transfer_params(.tex=target,.ptr=pixels)));
        assert(!memcmp(pixels,control,bytes) && "Identity Adaptive must preserve the complete Reference carrier and metadata");
        retire(r);
        for(unsigned p=0;p<source.num_planes;p++)pl_tex_destroy(gpu,&source.planes[p].texture);
    }
    pl_tex_destroy(gpu,&degamma);pl_tex_destroy(gpu,&pq);
    free(pixels);free(control);dvbridge_renderer_set_fast_chroma(r,previous);
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
        if(!k){ordered_pair(gpu,&source,geometry);rgb_scanout(r,gpu,&source,&policy,&prediction,&geometry,target,fbo);}
        if(k>=4)for(unsigned p=0;p<2;p++)pl_tex_destroy(gpu,&source.planes[p].texture);
        else pl_tex_destroy(gpu,&input);
    }
    native_signal(r,gpu,target,fbo);
    free(expected);free(actual);dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    pl_tex_destroy(gpu,&target);reference_gpu_destroy(&g);
}
