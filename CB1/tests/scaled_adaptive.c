/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
#include "../src/dvbridge_render.c"
#include <time.h>

static void finish(struct dvbridge_renderer *r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s==DVBRIDGE_DV_READY)return;
        assert(s==DVBRIDGE_DV_PENDING || s==DVBRIDGE_DV_BUSY);
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Adaptive completion timed out");
}

static void retire(struct dvbridge_renderer *r)
{
    dvbridge_render_dv_policy_cancel(r);glFinish();
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
}

static void read_carrier(unsigned fbo,unsigned char *out)
{
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,out);
    assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
}

static void reject_expansion(struct dvbridge_renderer *r)
{
    glFinish();uint32_t record[16];memcpy(record,r->dv.mapped,sizeof(record));
    record[11]=1;assert(dve_derive(r,record));r->dv.ready=r->ready=true;
    assert(r->dv.output.value.expansion_reason==CB1_DVE_SOURCE_BOUND);
}

int main(int argc,char **argv)
{
    bool gui_only=argc>1 && !strcmp(argv[1],"gui");
    bool domain_only=argc>1 && !strcmp(argv[1],"domain");
    bool area_only=argc>1 && !strcmp(argv[1],"area");
    bool placed_only=argc>1 && !strcmp(argv[1],"placed");
    bool warm_placed=argc>1 && !strcmp(argv[1],"warmplaced");
    bool benchmark=argc>1 && !strcmp(argv[1],"bench");
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    /* This witness checks admission/metadata only, never executes a quad pack. */
    if(area_only)r->fragment_quad=true;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3079;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_identity id={1,1,1};
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(r->gpu,"rgba8"),.renderable=true));assert(target);
    unsigned fbo=0;pl_opengl_unwrap(r->gpu,target,NULL,NULL,&fbo);assert(fbo);
    pl_tex gui=reference_texture(r->gpu,3840,2160,NULL);
    pl_tex lut=reference_texture(r->gpu,1,1,(float[4]){.1,.1,.1,1});
    pl_tex pq=reference_texture(r->gpu,1,1,(float[4]){.2,.2,.2,1});
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=lut,.pq=pq,
        .rect={0,0,3840,2160},.input_pq=true};
    pl_tex_clear(r->gpu,gui,(float[4]){.1,.05,.025,.5});
    const size_t packed_bytes=3840u*2160u*4;
    unsigned char *control=malloc(packed_bytes),*actual=malloc(packed_bytes);assert(control && actual);
    const struct dvbridge_geometry cases[]={
        {1920,1080,0,0,3840,2160},{2560,1440,0,0,3840,2160},
        {1280,720,0,0,3840,2160},{2048,1152,0,0,3840,2160},
        {1920,800,0,280,3840,1600},{3840,2160,0,0,3840,2160}};
    for(unsigned preset=DVBRIDGE_ADAPTIVE_B_FP32;preset<=DVBRIDGE_ADAPTIVE_B_FP16;preset++)
    for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);c++){
        policy.adaptive=preset;
        if(benchmark && preset!=DVBRIDGE_ADAPTIVE_B_FP16)continue;
        if(gui_only && c!=5)continue;
        if(placed_only && c!=4)continue;
        if(warm_placed && c!=3 && c!=4)continue;
        struct dvbridge_geometry geometry=cases[c];
        size_t count=(size_t)geometry.source_width*geometry.source_height;
        float *pixels=malloc(count*4*sizeof(float));assert(pixels);
        for(size_t i=0;i<count;i++)for(unsigned j=0;j<4;j++)
            pixels[i*4+j]=j==3?1:dv_ideal_pq(60+(i%251)*(j+1)*.25);
        pl_tex input=reference_texture(r->gpu,geometry.source_width,geometry.source_height,pixels);free(pixels);
        struct pl_frame frame=reference_frame(input,geometry.source_width,geometry.source_height);
        if(c==4 && preset==DVBRIDGE_ADAPTIVE_B_FP16){
            pl_fmt fp16=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,16,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(fp16);
            assert(pl_tex_recreate(r->gpu,&r->enhanced_input,pl_tex_params(.w=3840,.h=2160,
                .format=fp16,.renderable=true,.sampleable=true,.blit_dst=true)));
            pl_tex_clear(r->gpu,r->enhanced_input,(float[4]){.006,.005,.004,1});
        }
        if(benchmark){
            for(unsigned visible=0;visible<2;visible++)for(unsigned i=0;i<24;i++){
                struct timespec a,b;glFinish();clock_gettime(CLOCK_MONOTONIC,&a);
                dvbridge_renderer_set_overlay_visible(r,visible);
                assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,m,bytes,
                    1,1,geometry,target,false,visible?&overlay:NULL)==DVBRIDGE_DV_PENDING);
                finish(r);assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));glFinish();
                clock_gettime(CLOCK_MONOTONIC,&b);
                if(i>=8)printf("BENCH,%u,%u,%u,%u,%.6f\n",geometry.source_width,
                    geometry.source_height,visible,i-8,(b.tv_sec-a.tv_sec)*1000.+(b.tv_nsec-a.tv_nsec)/1e6);
                retire(r);id.picture++;
            }
            goto next_geometry;
        }
        for(unsigned flip=0;flip<2;flip++)for(unsigned gui_state=0;gui_state<6;gui_state++){
            void *expected_metadata=NULL;size_t expected_bytes=0;
            for(unsigned optimized=0;optimized<2;optimized++){
                dvbridge_renderer_set_overlay_visible(r,gui_state==3);
                enum dvbridge_dv_policy_status status=optimized?
                    dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,m,bytes,
                        1,1,geometry,target,flip,gui_state==3?&overlay:NULL):
                    dvbridge_render_dv_policy_prepare(r,&policy,&id,&frame,m,bytes,1,1,geometry);
                assert(status==DVBRIDGE_DV_PENDING);
                if(domain_only){
                    assert(r->enhanced_linear && "Scaled Adaptive must not add a PQ round trip");
                    assert((preset!=DVBRIDGE_ADAPTIVE_B_FP16 ||
                        (r->enhanced_input && r->enhanced_input->params.format->component_depth[0]==16)) &&
                        "Scaled Adaptive must retain the FP16 reconstruction path");
                    assert((preset!=DVBRIDGE_ADAPTIVE_B_FP16 || r->enhanced_input->params.blit_dst) &&
                        "Adaptive storage must support clearing reused letterbox borders");
                    if(preset==DVBRIDGE_ADAPTIVE_B_FP16 && !geometry.x && !geometry.y &&
                       geometry.width==3840 && geometry.height==2160)
                        assert(r->enhanced_input->params.w==(r->fragment_quad?(int)geometry.source_width:3840) &&
                            r->enhanced_input->params.h==(r->fragment_quad?(int)geometry.source_height:2160) &&
                            "Use native expansion only with a supported final scaler/packer");
                    finish(r);retire(r);goto next_geometry;
                }
                if(area_only){
                    reject_expansion(r);finish(r);
                    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
                    unsigned active[4];assert(dvbridge_active_area(out->candidate,active));
                    assert(!memcmp(active,out->value.margins,sizeof(active)) &&
                        "Native-grid rejection must retain output-raster L5 geometry");
                    retire(r);goto next_geometry;
                }
                if(optimized && !gui_state){
                    bool native=r->enhanced_input && (r->enhanced_input->params.w!=3840 ||
                        r->enhanced_input->params.h!=2160);
                    assert((native || (r->enhanced_prepack && r->enhanced_skip_aux)) &&
                        "Use native-grid expansion or fused output, not the old scaled PQ path");
                }
                if(gui_state==2)finish(r);
                if(gui_state==4)reject_expansion(r);
                if(gui_state){
                    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true) &&
                        "A late GUI redraw must preserve the pending picture");
                    GLsync fence=r->dv.fence;
                    for(unsigned redraw=0;redraw<5;redraw++){
                        overlay.rect[1]=redraw*7;overlay.input_pq=redraw&1;
                        assert(dvbridge_render_dv_policy_update_overlay(r,redraw==2?NULL:&overlay,redraw!=2));
                        assert(r->dv.fence==fence && "GUI redraw must not resubmit video analysis");
                    }
                }
                if(gui_state==5)reject_expansion(r);
                finish(r);
                const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
                assert(out->value.identity.picture==id.picture && out->value.measured==(gui_state<4));
                if(!optimized){expected_bytes=out->bytes;expected_metadata=av_memdup(out->output_metadata,out->bytes);assert(expected_metadata);}
                else assert(out->bytes==expected_bytes && !memcmp(out->output_metadata,expected_metadata,expected_bytes));
                assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
                read_carrier(fbo,optimized?actual:control);
                if(c==4 && !gui_state && !flip){
                    unsigned char *image=optimized?actual:control;
                    assert(image[0]==128 && image[1]==16 && "Placed Adaptive must clear reused borders to transport black");
                }
                retire(r);
            }
            if(memcmp(actual,control,packed_bytes)){
                size_t first=0,changed=0;while(first<packed_bytes && actual[first]==control[first])first++;
                for(size_t i=first;i<packed_bytes;i++)changed+=actual[i]!=control[i];
                fprintf(stderr,"carrier mismatch preset=%u geometry=%u flip=%u gui=%u first=%zu (%u vs %u) bytes=%zu\n",
                    preset,c,flip,gui_state,first,actual[first],control[first],changed);
                assert(!"Fusion/late overlays changed carrier bytes");
            }
            av_free(expected_metadata);id.picture++;
        }
next_geometry:
        fprintf(stderr,"PASS geometry %ux%u placement %u,%u %ux%u\n",geometry.source_width,
            geometry.source_height,geometry.x,geometry.y,geometry.width,geometry.height);
        pl_tex_destroy(r->gpu,&input);
    }
    free(control);free(actual);pl_tex_destroy(r->gpu,&gui);pl_tex_destroy(r->gpu,&lut);
    pl_tex_destroy(r->gpu,&pq);pl_tex_destroy(r->gpu,&target);av_free(m);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&g);
    puts("PASS scaled Adaptive: exact carrier/metadata and pending/ready GUI updates");
}
