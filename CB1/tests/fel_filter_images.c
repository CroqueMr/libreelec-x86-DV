/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include "dvbridge_gl_frame.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>

static pl_tex render_mode(struct dvbridge_renderer *r,const struct pl_frame *source,
    AVDOVIMetadata *metadata,size_t bytes,struct dvbridge_geometry geometry,int mode)
{
    if(!mode){
        assert(dvbridge_render_rgb(r,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }
    struct dvbridge_policy p=reference_policy();
    p.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity id={1,1,1};
    p.mode=mode==1?DVBRIDGE_MODE_HDR10_BASIC:mode==2?DVBRIDGE_MODE_HDR10_EXPERT:DVBRIDGE_MODE_ENHANCED_DV;
    if(mode==1){
        struct dvbridge_hdr10_session session={.target={.primaries=PL_COLOR_PRIM_BT_2020,
            .transfer=PL_COLOR_TRC_LINEAR,.hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000}}};
        assert(dvbridge_render_hdr10_rgb(r,&session,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }
    if(mode==2){
        assert(dvbridge_render_hdr10_policy_rgb(r,&p,&id,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }

    enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_prepare(r,&p,&id,
        source,metadata,bytes,1,1,geometry);
    for(int i=0;i<10 && status==DVBRIDGE_DV_PENDING;i++)
        status=dvbridge_render_dv_policy_wait(r,1000000000);
    if(status!=DVBRIDGE_DV_READY)fprintf(stderr,"Adaptive fixture mode=%d status=%d\n",mode,status);
    assert(status==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
    assert(out && out->value.fel_reconstructed==(source->enhancement_layer!=NULL));
    return out->intermediate;
}

static void qualify_imported_base_rows(struct reference_gpu *g,int w,int h,int modes,int filter)
{
    pl_gpu gpu=g->gl->gpu;
    pl_tex textures[4]={0};
    struct dvbridge_gl_frame imported[2]={0};
    for(int layer=0;layer<2;layer++){
        struct dvbridge_gl_plane handles[3]={0};
        for(int p=0;p<2;p++){
            int pw=w>>(layer+p),ph=h>>(layer+p),components=p?2:1;
            uint16_t *data=malloc((size_t)pw*ph*components*sizeof(*data));assert(data);
            for(int y=0;y<ph;y++)for(int x=0;x<pw;x++)for(int c=0;c<components;c++)
                data[(y*pw+x)*components+c]=(layer || p?512:256+(y&1)*128)<<6;
            pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
            pl_tex tex=textures[layer*2+p]=pl_tex_create(gpu,pl_tex_params(.w=pw,.h=ph,
                .format=fmt,.sampleable=true,.initial_data=data));assert(tex);
            free(data);
            handles[p]=(struct dvbridge_gl_plane){pl_opengl_unwrap(gpu,tex,NULL,NULL,NULL),pw,ph};
        }
        assert(dvbridge_gl_frame_import(&imported[layer],gpu,DVBRIDGE_P010,w>>layer,h>>layer,handles));
        dvbridge_gl_frame_set_chroma(&imported[layer],PL_CHROMA_TOP_LEFT);
    }
    /* Independent raw-texel oracle: bypass plane wrapping, siting and renderer
     * addressing, and check its samples against the CPU fixture before use. */
    pl_tex packed=reference_texture(gpu,w,h,NULL);
    struct pl_shader_desc descriptors[2]={
        {.desc={.name="base_y",.type=PL_DESC_SAMPLED_TEX},.binding={.object=textures[0]}},
        {.desc={.name="base_uv",.type=PL_DESC_SAMPLED_TEX},.binding={.object=textures[1]}},
    };
    pl_dispatch dispatch=pl_dispatch_create(NULL,gpu);assert(dispatch);
    pl_shader sh=pl_dispatch_begin(dispatch);
    assert(pl_shader_custom(sh,&(struct pl_custom_shader){
        .input=PL_SHADER_SIG_NONE,.output=PL_SHADER_SIG_COLOR,.output_w=w,.output_h=h,
        .descriptors=descriptors,.num_descriptors=2,
        .body="ivec2 p=ivec2(gl_FragCoord.xy);color=vec4(texelFetch(base_y,p,0).r,texelFetch(base_uv,p/2,0).rg,1.0);"}));
    assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&sh,.target=packed)));
    const size_t frame_bytes=(size_t)w*h*4*sizeof(float);
    float *raw=malloc(frame_bytes),*actual=malloc(frame_bytes),
        *expected=malloc(frame_bytes),*without_el=malloc(frame_bytes);
    assert(raw && actual && expected && without_el);
    reference_read(gpu,packed,0,0,w,h,raw);
    for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<4;c++){
        float want=c==3?1.f:(float)((c?512:256+(y&1)*128)<<6)/65535.f;
        assert(fabsf(raw[(y*w+x)*4+c]-want)<1e-7f);
    }
    struct pl_frame oracle=reference_frame(packed,w,h);
    oracle.planes[0].components=3;
    oracle.repr.bits=imported[0].frame.repr.bits;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1500}};
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
    mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++){
        mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;
        mapping->nlq[c].vdr_in_max=1023*4096;
    }
    struct dvbridge_geometry geometry={w,h,0,0,w,h};
    struct dvbridge_retirement_owner *owners[2]={dvbridge_retirement_owner_create(gpu),dvbridge_retirement_owner_create(gpu)};
    assert(owners[0] && owners[1]);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owners[0]),*reference=dvbridge_renderer_create_with_owner(owners[1]);
    assert(r && reference);
    dvbridge_renderer_set_fel_filter(r,filter);dvbridge_renderer_set_fel_filter(reference,filter);
    for(int mode=0;mode<modes;mode++)for(int paired=0;paired<2;paired++){
        av_dovi_get_header(m)->disable_residual_flag=!paired;
        imported[0].frame.enhancement_layer=oracle.enhancement_layer=paired?&imported[1].frame:NULL;
        reference_read(gpu,render_mode(r,&imported[0].frame,m,bytes,geometry,mode),0,0,w,h,actual);
        reference_read(gpu,render_mode(reference,&oracle,m,bytes,geometry,mode),0,0,w,h,expected);
        float maximum=0,neutral_error=0,min_row=1;
        for(int i=0;i<w*h*4;i++){
            assert(isfinite(actual[i]) && isfinite(expected[i]));
            maximum=fmaxf(maximum,fabsf(actual[i]-expected[i]));
            if(paired)neutral_error=fmaxf(neutral_error,fabsf(actual[i]-without_el[i]));
        }
        for(int y=0;y<h;y+=2){
            float difference=0;
            for(int c=0;c<3;c++)difference=fmaxf(difference,
                fabsf(actual[4*(y*w+w/2)+c]-actual[4*((y+1)*w+w/2)+c]));
            min_row=fminf(min_row,difference);
        }
        fprintf(stderr,"P010 BL rows mode=%d EL=%d oracle_max=%.9g neutral_max=%.9g row_min=%.9g\n",
            mode,paired,maximum,neutral_error,min_row);
        assert(maximum<3e-5f && neutral_error<3e-5f && min_row>1e-4f);
        if(!paired)memcpy(without_el,actual,frame_bytes);
        if(mode==3){
            dvbridge_render_dv_policy_cancel(r);dvbridge_render_dv_policy_cancel(reference);glFinish();
            assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
            assert(dvbridge_render_dv_policy_poll(reference)==DVBRIDGE_DV_IDLE);
        }
    }
    dvbridge_renderer_destroy(r);dvbridge_renderer_destroy(reference);av_free(m);
    glFinish();
    for(int i=0;i<2;i++){dvbridge_retirement_owner_poll(owners[i]);assert(dvbridge_retirement_owner_destroy(&owners[i]));}
    for(int i=0;i<2;i++)dvbridge_gl_frame_release(&imported[i]);
    for(int i=0;i<4;i++)pl_tex_destroy(gpu,&textures[i]);
    pl_tex_destroy(gpu,&packed);pl_dispatch_destroy(&dispatch);
    free(raw);free(actual);free(expected);free(without_el);
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    for(int filter=1;filter<=2;filter++)qualify_imported_base_rows(&g,64,48,4,filter);
    qualify_imported_base_rows(&g,3840,2160,1,1);
    reference_gpu_destroy(&g);
    puts("PASS FEL imported BL rows, Standard/HDR10 Basic/Expert/Adaptive and non-FEL identity");
}
