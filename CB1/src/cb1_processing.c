/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_processing.h"
#include "dvbridge_placebo.h"
#include "dvbridge_metadata.h"
#include <string.h>
#include <limits.h>
#include <math.h>
#include <assert.h>

static unsigned __int128 magnitude(int64_t v)
{
    return v<0 ? -( __int128)v : v;
}

bool cb1_mmr_certify(const struct pl_cb1_dovi_component *c, unsigned denominator)
{
    if (!c || c->num_pivots!=2 || c->method[0]!=AV_DOVI_MAPPING_MMR ||
        c->order[0]<1 || c->order[0]>3 || denominator<1 || denominator>32 ||
        c->pivots[0]>=c->pivots[1] || c->pivots[1]>1023) return false;
    unsigned __int128 bound=magnitude(c->constant[0])*1048576;
    if (bound>INT64_MAX) return false;
    for (unsigned o=0;o<c->order[0];o++) {
        for (int t=0;t<7;t++) {
            int64_t coef=c->mmr[0][o][t];
            if (coef<INT32_MIN || coef>INT32_MAX) return false;
            bound+=magnitude(coef)*1048576;
            if (bound>INT64_MAX) return false;
        }
    }
    return true;
}

int64_t cb1_mmr_term(const int64_t coefficients[3], unsigned order, unsigned sample)
{
    /* Certified signed products; Q20 feature powers use unsigned floor. */
    assert(order<=3 && sample<=1023);
    for (unsigned o=0;o<order;o++) assert(coefficients[o]>=INT32_MIN && coefficients[o]<=INT32_MAX);
    uint64_t first=(uint64_t)sample*1048576/1023, feature=first;
    int64_t result=0;
    for (unsigned o=0;o<order;o++) {
        result+=coefficients[o]*(int64_t)feature;
        feature=(feature*first)>>20;
    }
    return result;
}

static bool same_mmr_key(const struct cb1_processing *a, const struct cb1_processing *b)
{
    return a->cached_contract.bit_depth==b->view.bit_depth &&
        a->cached_contract.denominator==b->view.denominator &&
        a->cached_contract.narrow_components==b->narrow_components &&
        a->cached_contract.poly_components==b->view.poly_components &&
        !memcmp(a->cached_contract.components,b->view.components,sizeof(b->view.components)) &&
        !memcmp(&a->cached_layout,&b->layout,sizeof(b->layout));
}

static bool bounded_mmr_table(const struct pl_cb1_dovi_component *c, unsigned denominator)
{
    /* Bound Q20/float lookup error; high-cancellation mappings stay general. */
    unsigned __int128 sum=magnitude(c->constant[0]);
    for (unsigned o=0;o<c->order[0];o++) for (int t=0;t<7;t++) sum+=magnitude(c->mmr[0][o][t]);
    return sum<=((unsigned __int128)64<<denominator);
}

static bool prepare_mmr(struct cb1_processing *next, pl_gpu gpu)
{
    float table[9*1024]={0};
    for (int c=0;c<3;c++) {
        if (next->view.poly_components&(1u<<c)) {
            const int64_t *poly=next->view.components[c].poly[0];
            for (unsigned s=0;s<1024;s++) {
                double x=s/1023.0;
                table[c*3*1024+s]=ldexp((poly[2]*x+poly[1])*x+poly[0],-(int)next->view.denominator);
            }
        }
        if (!(next->narrow_components & (1u<<c))) continue;
        const struct pl_cb1_dovi_component *comp=&next->view.components[c];
        for (int input=0;input<3;input++) {
            int64_t coefficients[3];
            for (int o=0;o<3;o++) coefficients[o]=comp->mmr[0][o][input];
            for (unsigned s=0;s<1024;s++)
                table[(c*3+input)*1024+s]=ldexp((double)cb1_mmr_term(coefficients,comp->order[0],s),
                    -(int)next->view.denominator-20);
        }
    }
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
    pl_tex texture=pl_tex_create(gpu,pl_tex_params(.w=1024,.h=9,.format=fmt,
        .sampleable=true,.host_writable=true));
    if (!texture) return false;
    if (!pl_tex_upload(gpu,pl_tex_transfer_params(.tex=texture,.ptr=table))) {
        pl_tex_destroy(gpu,&texture);
        return false;
    }
    /* Immutable replacement: queued reads retain the old GL object. */
    pl_tex_destroy(gpu,&next->mmr_texture);
    next->mmr_texture=texture;
    next->cached_contract=next->view;
    next->cached_contract.narrow_components=next->narrow_components;
    next->cached_layout=next->layout;
    next->cache_generation++;
    return true;
}

static bool single_layout(const struct cb1_processing *p)
{
    if (p->layout.bits.color_depth && p->layout.bits.color_depth!=10) return false;
    if (p->layout.levels<PL_COLOR_LEVELS_UNKNOWN || p->layout.levels>PL_COLOR_LEVELS_FULL) return false;
    unsigned channels=0;
    for (int plane=0;plane<p->layout.planes;plane++) {
        if (p->layout.plane[plane].type!=PL_FMT_FLOAT && p->layout.plane[plane].type!=PL_FMT_UNORM) return false;
        for (int c=0;c<p->layout.plane[plane].components;c++) {
            int mapping=p->layout.plane[plane].mapping[c];
            if (mapping<0 || mapping>2) continue;
            if (p->layout.plane[plane].depth[c]<10) return false;
            channels|=1u<<mapping;
        }
    }
    return channels==7;
}

static bool single_mapping(const struct cb1_processing *p)
{
    if (p->enhancement_active || !single_layout(p)) return false;
    for (int c=0;c<3;c++) {
        const struct pl_cb1_dovi_component *m=&p->view.components[c];
        if (m->num_pivots!=2 || m->pivots[0]!=0 || m->pivots[1]!=1023 ||
            (m->method[0]==AV_DOVI_MAPPING_MMR ? m->order[0]!=2 : m->order[0]>2)) return false;
    }
    return true;
}

static bool luma_lookup(const struct pl_cb1_dovi_processing *p)
{
    const struct pl_cb1_dovi_component *c=&p->components[0];
    if (c->method[0]!=AV_DOVI_MAPPING_POLYNOMIAL || c->order[0]!=2 || !c->poly[0][2]) return false;
    unsigned __int128 bound=0;
    for (int i=0;i<3;i++) bound+=magnitude(c->poly[0][i]);
    return bound<=((unsigned __int128)64<<p->denominator);
}

static bool fel_layout(const struct pl_frame *source)
{
    const struct pl_frame *el=source->enhancement_layer;
    if (!el || el->num_planes<1 || el->num_planes>3 || el->rotation ||
        el->enhancement_layer || el->repr.bits.color_depth!=10) return false;
    unsigned channels=0;
    for (int p=0;p<el->num_planes;p++) {
        const struct pl_plane *plane=&el->planes[p];
        if (!plane->texture || !isfinite(plane->shift_x) || !isfinite(plane->shift_y) ||
            (plane->texture->params.format->type!=PL_FMT_UNORM &&
             plane->texture->params.format->type!=PL_FMT_FLOAT)) return false;
        for (int c=0;c<plane->components;c++) {
            int m=plane->component_mapping[c];
            if (m<0 || m>2) continue;
            if (plane->texture->params.format->component_depth[c]<10) return false;
            channels|=1u<<m;
        }
    }
    return channels==7;
}

static double pq_sample(double x, bool encode)
{
    const double m1=2610.0/16384,m2=2523.0/32,c1=3424.0/4096,c2=2413.0/128,c3=2392.0/128;
    if (encode) {
        double p=pow(fmax(x,0),m1);
        return pow((c1+c2*p)/(1+c3*p),m2);
    }
    double p=pow(fmax(x,0),1/m2);
    return pow(fmax(p-c1,0)/(c2-c3*p),1/m1);
}

static bool prepare_colour(struct cb1_processing *next, pl_gpu gpu)
{
    if (next->pq_texture[0] && next->pq_texture[1]) return true;
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
    pl_tex textures[2]={0};float table[4096];
    for (int encode=0;encode<2;encode++) {
        for (int i=0;i<4096;i++) {
            double x=i/4095.0;
            /* Fourth-root encode coordinates retain near-black resolution. */
            table[i]=pq_sample(encode?x*x*x*x:x,encode);
        }
        textures[encode]=pl_tex_create(gpu,pl_tex_params(.w=4096,.h=1,.format=fmt,
            .sampleable=true,.host_writable=true));
        if (!textures[encode] || !pl_tex_upload(gpu,pl_tex_transfer_params(
                .tex=textures[encode],.ptr=table))) {
            pl_tex_destroy(gpu,&textures[0]);pl_tex_destroy(gpu,&textures[1]);return false;
        }
    }
    next->pq_texture[0]=textures[0];next->pq_texture[1]=textures[1];
    return true;
}

pl_tex cb1_processing_pq_encoder(struct cb1_processing *state, pl_gpu gpu)
{
    if (!state || !gpu) return NULL;
    if (state->pq_texture[1]) return state->pq_texture[1];
    if (gpu->limits.max_tex_2d_dim<4096 || !pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,
            PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR)) return NULL;
    return prepare_colour(state,gpu) ? state->pq_texture[1] : NULL;
}

bool cb1_processing_prepare(struct cb1_processing *state, pl_gpu gpu,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    bool paired, uint32_t requested)
{
    if (!state || !source || source->num_planes<1 || source->num_planes>4)
        return false;
    struct cb1_processing next={.mmr_texture=state->mmr_texture,
        .cached_contract=state->cached_contract,.cached_layout=state->cached_layout,
        .cache_generation=state->cache_generation};
    memcpy(next.pq_texture,state->pq_texture,sizeof(next.pq_texture));
    if (metadata) {
        struct dvbridge_color mapped;
        if (!dvbridge_map_color(&mapped,metadata,bytes,paired)) return false;
        const AVDOVIMetadata *m=metadata;
        const AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
        const AVDOVIDataMapping *map=av_dovi_get_mapping(m);
        next.metadata_present=true;
        next.enhancement_active=mapped.dovi.nlq_active;
        next.view.bit_depth=h->bl_bit_depth;
        next.view.denominator=h->coef_log2_denom;
        for (int c=0;c<3;c++) {
            struct pl_cb1_dovi_component *out=&next.view.components[c];
            const AVDOVIReshapingCurve *in=&map->curves[c];
            out->num_pivots=in->num_pivots;
            memcpy(out->pivots,in->pivots,in->num_pivots*sizeof(*in->pivots));
            for (int s=0;s+1<in->num_pivots;s++) {
                out->method[s]=in->mapping_idc[s];
                if (in->mapping_idc[s]==AV_DOVI_MAPPING_POLYNOMIAL) {
                    out->order[s]=in->poly_order[s];
                    memcpy(out->poly[s],in->poly_coef[s],sizeof(out->poly[s]));
                } else {
                    out->order[s]=in->mmr_order[s];
                    out->constant[s]=in->mmr_constant[s];
                    memcpy(out->mmr[s],in->mmr_coef[s],sizeof(out->mmr[s]));
                }
            }
        }
    } else if (bytes) return false;
    next.layout.crop=source->crop;
    next.layout.bits=source->repr.bits;
    next.layout.levels=source->repr.levels;
    next.layout.planes=source->num_planes;
    for (int p=0;p<source->num_planes;p++) {
        const struct pl_plane *in=&source->planes[p];
        if (!in->texture) return false;
        next.layout.plane[p].width=in->texture->params.w;
        next.layout.plane[p].height=in->texture->params.h;
        next.layout.plane[p].type=in->texture->params.format->type;
        next.layout.plane[p].components=in->components;
        memcpy(next.layout.plane[p].mapping,in->component_mapping,sizeof(in->component_mapping));
        for (int c=0;c<4;c++) next.layout.plane[p].depth[c]=in->texture->params.format->component_depth[c];
        next.layout.plane[p].shift_x=in->shift_x;
        next.layout.plane[p].shift_y=in->shift_y;
        next.layout.plane[p].flipped=in->flipped;
    }
    next.lookup_supported=gpu && gpu->glsl.version>=300 &&
        pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
    next.compute_supported=gpu && gpu->glsl.compute;
    next.requested_groups=requested;
    next.rejected_groups=requested;
    if ((requested&CB1_PROCESSING_COLOUR) && next.metadata_present && gpu &&
        gpu->glsl.version>=300 && gpu->limits.max_tex_2d_dim>=4096 &&
        pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR) && prepare_colour(&next,gpu)) {
        next.selected_groups|=CB1_PROCESSING_COLOUR;
        next.rejected_groups&=~CB1_PROCESSING_COLOUR;
        memcpy(next.view.pq_texture,next.pq_texture,sizeof(next.view.pq_texture));
    }
    if ((requested&CB1_PROCESSING_FEL) && paired && next.enhancement_active &&
        next.view.bit_depth==10 && gpu && gpu->glsl.version>=300 && fel_layout(source) &&
        pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE)) {
        next.selected_groups|=CB1_PROCESSING_FEL;
        next.rejected_groups&=~CB1_PROCESSING_FEL;
    }
    if ((requested&(CB1_PROCESSING_MMR|CB1_PROCESSING_SINGLE)) && next.metadata_present &&
        next.lookup_supported && next.view.bit_depth==10) {
        bool single=(requested&CB1_PROCESSING_SINGLE) && single_mapping(&next);
        if (single && luma_lookup(&next.view)) next.view.poly_components=1;
        for (int c=0;c<3;c++)
            if (((requested&CB1_PROCESSING_MMR) || single) &&
                cb1_mmr_certify(&next.view.components[c],next.view.denominator) &&
                bounded_mmr_table(&next.view.components[c],next.view.denominator))
                next.narrow_components|=1u<<c;
        if ((next.narrow_components || next.view.poly_components) &&
            ((next.mmr_texture && same_mmr_key(state,&next)) ||
                                      prepare_mmr(&next,gpu))) {
            if (next.narrow_components && (requested&CB1_PROCESSING_MMR)) next.selected_groups|=CB1_PROCESSING_MMR;
            if (single) next.selected_groups|=CB1_PROCESSING_SINGLE;
            next.rejected_groups&=~next.selected_groups;
            next.view.narrow_components=next.narrow_components;
            next.view.mmr_texture=next.mmr_texture;
        }
    }
    next.view.groups=next.selected_groups;
    *state=next;
    return true;
}

void cb1_processing_reset(struct cb1_processing *state, pl_gpu gpu)
{
    if (state) {
        if (state->mmr_texture) pl_tex_destroy(gpu,&state->mmr_texture);
        for (int i=0;i<2;i++) pl_tex_destroy(gpu,&state->pq_texture[i]);
        *state=(struct cb1_processing){0};
    }
}
