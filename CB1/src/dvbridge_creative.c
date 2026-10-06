/* SPDX-License-Identifier: GPL-3.0-only */
/* Open CM2.9 numerical references: DoViBaker and MPC Video Renderer.
 * See docs/CREATIVE-MAPPING.md for pinned revisions and qualified domains. */
#include "dvbridge_creative.h"
#include "dvbridge_metadata.h"
#include <libavutil/mem.h>
#include <stdlib.h>
#include <time.h>

static uint64_t source_hash(const void *data,size_t bytes)
{
    const uint8_t *p=data;uint64_t h=UINT64_C(14695981039346656037);
    for(size_t i=0;i<bytes;i++){h^=p[i];h*=UINT64_C(1099511628211);}return h;
}
static double pq(double nits)
{
    double v=pow(nits/10000.0,2610.0/16384.0);
    return 4095*pow((3424.0/4096.0+2413.0/128.0*v)/(1+2392.0/128.0*v),2523.0/32.0);
}
static void controls(double out[5],const AVDOVIDmData *e)
{
    out[0]=e->l2.trim_slope;out[1]=e->l2.trim_offset;out[2]=e->l2.trim_power;
    out[3]=e->l2.trim_chroma_weight;out[4]=e->l2.trim_saturation_gain;
}
static unsigned wire_word(const uint8_t *wire)
{
    return (unsigned)wire[0]<<8 | wire[1];
}

static bool cm4_controls(const AVDOVIDmData *e,struct dvbridge_cm4_controls *out)
{
    uint8_t wire[32];
    if(dvbridge_cm4_wire(8,e->dvbridge_original_bytes,e->dvbridge_original_length,wire)<0 ||
       e->l8.target_display_index!=wire[0])return false;
    const unsigned parsed[]={e->l8.trim_slope,e->l8.trim_offset,e->l8.trim_power,
        e->l8.trim_chroma_weight,e->l8.trim_saturation_gain,e->l8.ms_weight};
    *out=(struct dvbridge_cm4_controls){.present_fields=DVBRIDGE_CM4_PRIMARY};
    for(int i=0;i<6;i++){
        out->primary[i]=wire_word(wire+1+i*2);
        if(parsed[i]!=out->primary[i])return false;
    }
    unsigned length=e->dvbridge_original_length;
    if(length>=12){
        out->present_fields|=DVBRIDGE_CM4_MID_CONTRAST;
        out->mid_contrast=wire_word(wire+13);
        if(e->l8.target_mid_contrast!=out->mid_contrast)return false;
    }
    if(length>=13){
        out->present_fields|=DVBRIDGE_CM4_CLIP_TRIM;
        out->clip_trim=wire_word(wire+15);
        if(e->l8.clip_trim!=out->clip_trim)return false;
    }
    if(length>=19){
        out->present_fields|=DVBRIDGE_CM4_SATURATION;
        memcpy(out->saturation,wire+17,6);
        if(memcmp(out->saturation,e->l8.saturation_vector_field,6))return false;
    }
    if(length>=25){
        out->present_fields|=DVBRIDGE_CM4_HUE;
        memcpy(out->hue,wire+23,6);
        if(memcmp(out->hue,e->l8.hue_vector_field,6))return false;
    }
    return true;
}

/* Public target IDs describe peak, gamut and EOTF, not a measured black level.
 * Dolby professional-support target table, 2024-02-27; see CREATIVE-MAPPING.md. */
static bool cm4_preset(unsigned index,struct dvbridge_cm4_target *out)
{
    static const struct {unsigned index,nits;enum pl_color_primaries prim;
        enum pl_color_transfer trc;} targets[]={
        {1,100,PL_COLOR_PRIM_BT_709,PL_COLOR_TRC_BT_1886},
        {16,48,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_GAMMA26},
        {18,48,PL_COLOR_PRIM_DCI_P3,PL_COLOR_TRC_GAMMA26},
        {21,48,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_GAMMA26},
        {24,300,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_PQ},
        {25,300,PL_COLOR_PRIM_BT_2020,PL_COLOR_TRC_PQ},
        {27,600,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_PQ},
        {28,600,PL_COLOR_PRIM_BT_2020,PL_COLOR_TRC_PQ},
        {37,2000,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_PQ},
        {38,2000,PL_COLOR_PRIM_BT_2020,PL_COLOR_TRC_PQ},
        {42,108,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_PQ},
        {48,1000,PL_COLOR_PRIM_DISPLAY_P3,PL_COLOR_TRC_PQ},
        {49,1000,PL_COLOR_PRIM_BT_2020,PL_COLOR_TRC_PQ}
    };
    for(size_t i=0;i<sizeof(targets)/sizeof(targets[0]);i++)if(index==targets[i].index){
        *out=(struct dvbridge_cm4_target){.display_index=index,
            .max_pq=(uint16_t)floor(pq(targets[i].nits)+.5),
            .primaries=*pl_raw_primaries_get(targets[i].prim),
            .transfer=targets[i].trc,.origin=DVBRIDGE_CM4_PRESET};
        if(index==16)out->primaries.white=pl_raw_primaries_get(PL_COLOR_PRIM_ACES_AP0)->white;
        return true;
    }
    return false;
}

/* -1 malformed, 0 unknown primary index, 1 target bounds/gamut resolved. */
static int cm4_custom_target(const AVDOVIDmData *e,struct dvbridge_cm4_target *out)
{
    uint8_t wire[32];struct dvbridge_cm4_target preset;
    if(dvbridge_cm4_wire(10,e->dvbridge_original_bytes,e->dvbridge_original_length,wire)<0)
        return -1;
    unsigned index=wire[0],maximum=wire_word(wire+1),minimum=wire_word(wire+3),primary=wire[5];
    if(index!=e->l10.target_display_index || maximum!=e->l10.target_max_pq ||
       minimum!=e->l10.target_min_pq || primary!=e->l10.target_primary_index ||
       maximum<=minimum || cm4_preset(index,&preset))return -1;
    *out=(struct dvbridge_cm4_target){.display_index=index,.min_pq=minimum,.max_pq=maximum,
        .transfer=PL_COLOR_TRC_UNKNOWN,.origin=DVBRIDGE_CM4_CUSTOM,.min_pq_present=true};
    if(primary<3){
        static const enum pl_color_primaries prim[]={PL_COLOR_PRIM_DISPLAY_P3,
            PL_COLOR_PRIM_BT_709,PL_COLOR_PRIM_BT_2020};
        out->primaries=*pl_raw_primaries_get(prim[primary]);
    }else if(primary==255){
        const AVColorPrimariesDesc *parsed=&e->l10.target_display_primaries;
        const AVCIExy *xy[]={&parsed->prim.r,&parsed->prim.g,&parsed->prim.b,&parsed->wp};
        struct pl_cie_xy *dest[]={&out->primaries.red,&out->primaries.green,
            &out->primaries.blue,&out->primaries.white};
        for(int i=0;i<4;i++){
            unsigned ux=wire_word(wire+6+i*4),uy=wire_word(wire+8+i*4);
            int x=ux>=32768?(int)ux-65536:(int)ux,y=uy>=32768?(int)uy-65536:(int)uy;
            if(xy[i]->x.den<=0 || xy[i]->y.den<=0 ||
               (int64_t)xy[i]->x.num*32767!=(int64_t)x*xy[i]->x.den ||
               (int64_t)xy[i]->y.num*32767!=(int64_t)y*xy[i]->y.den)return -1;
            dest[i]->x=x/32767.0;dest[i]->y=y/32767.0;
        }
        if(!pl_primaries_valid(&out->primaries))return -1;
    }else return 0;
    return 1;
}

static bool cm4_same_gamut(const struct pl_raw_primaries *a,const struct pl_raw_primaries *b)
{
    const struct pl_cie_xy *left[]={&a->red,&a->green,&a->blue,&a->white};
    const struct pl_cie_xy *right[]={&b->red,&b->green,&b->blue,&b->white};
    for(int i=0;i<4;i++)if(lround(left[i]->x*32767)!=lround(right[i]->x*32767) ||
        lround(left[i]->y*32767)!=lround(right[i]->y*32767))return false;
    return true;
}

static bool cm4_targets(const AVDOVIMetadata *m,struct dvbridge_creative_plan *p)
{
    bool seen8[256]={0},seen10[256]={0},unknown=false,has_controls=false;
    bool lower_ambiguous=false,upper_ambiguous=false;
    static const enum pl_color_primaries output_prim[]={
        [DVBRIDGE_GAMUT_BT709]=PL_COLOR_PRIM_BT_709,
        [DVBRIDGE_GAMUT_P3_D65]=PL_COLOR_PRIM_DISPLAY_P3,
        [DVBRIDGE_GAMUT_BT2020]=PL_COLOR_PRIM_BT_2020};
    p->cm4_output=(struct dvbridge_cm4_target){.max_pq=(uint16_t)floor(p->target_pq+.5),
        .primaries=*pl_raw_primaries_get(output_prim[p->policy.tv.gamut]),
        .transfer=PL_COLOR_TRC_PQ,.origin=DVBRIDGE_CM4_MANUAL};
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *e=av_dovi_get_ext(m,i);
        if(e->level!=10)continue;
        struct dvbridge_cm4_target target;
        if(cm4_custom_target(e,&target)<0 || seen10[e->l10.target_display_index])return false;
        seen10[e->l10.target_display_index]=true;
    }
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *e=av_dovi_get_ext(m,i);
        if(e->level!=8)continue;
        struct dvbridge_cm4_anchor a={.present=true};has_controls=true;
        if(!cm4_controls(e,&a.controls) || seen8[e->l8.target_display_index])return false;
        seen8[e->l8.target_display_index]=true;
        bool resolved=cm4_preset(e->l8.target_display_index,&a.target);
        if(!resolved)for(int j=0;j<m->num_ext_blocks;j++){
            const AVDOVIDmData *t=av_dovi_get_ext(m,j);
            if(t->level==10 && t->l10.target_display_index==e->l8.target_display_index)
                resolved=cm4_custom_target(t,&a.target)==1;
        }
        if(!resolved){unknown=true;continue;}
        if((a.target.transfer!=PL_COLOR_TRC_UNKNOWN && a.target.transfer!=p->cm4_output.transfer) ||
           !cm4_same_gamut(&a.target.primaries,&p->cm4_output.primaries))continue;
        if(a.target.max_pq<=p->cm4_output.max_pq){
            if(!p->cm4_lower.present || a.target.max_pq>p->cm4_lower.target.max_pq){
                p->cm4_lower=a;lower_ambiguous=false;
            }else if(a.target.max_pq==p->cm4_lower.target.max_pq)lower_ambiguous=true;
        }
        if(a.target.max_pq>=p->cm4_output.max_pq){
            if(!p->cm4_upper.present || a.target.max_pq<p->cm4_upper.target.max_pq){
                p->cm4_upper=a;upper_ambiguous=false;
            }else if(a.target.max_pq==p->cm4_upper.target.max_pq)upper_ambiguous=true;
        }
    }
    p->cm4_targets=!has_controls?DVBRIDGE_CM4_NO_CONTROLS:unknown?DVBRIDGE_CM4_UNKNOWN_TARGET:
        lower_ambiguous || upper_ambiguous || (!p->cm4_lower.present && !p->cm4_upper.present)?
        DVBRIDGE_CM4_INCOMPATIBLE_TARGETS:DVBRIDGE_CM4_TARGETS_RESOLVED;
    if(p->cm4_targets!=DVBRIDGE_CM4_TARGETS_RESOLVED){
        p->cm4_lower=p->cm4_upper=(struct dvbridge_cm4_anchor){0};
    }else if(p->cm4_lower.present && p->cm4_upper.present &&
             p->cm4_upper.target.max_pq>p->cm4_lower.target.max_pq){
        p->cm4_weight=(double)(p->cm4_output.max_pq-p->cm4_lower.target.max_pq)/
            (p->cm4_upper.target.max_pq-p->cm4_lower.target.max_pq);
    }
    return true;
}

static double bound(double v) {return fmax(0,fmin(1,v));}
static void matrix_rgb(const double matrix[9],const double in[3],double out[3])
{
    double v[3];
    for(int i=0;i<3;i++)v[i]=matrix[i*3]*in[0]+matrix[i*3+1]*in[1]+matrix[i*3+2]*in[2];
    memcpy(out,v,sizeof(v));
}
static double cm4_eotf(double q)
{
    double v=pow(bound(q),32.0/2523);
    return 10000*pow(fmax(v-3424.0/4096,0)/(2413.0/128-2392.0/128*v),16384.0/2610);
}
/* Public IPTPQc4 matrices from pinned libplacebo colorspace.c. */
static const double cm4_ipt[9]={.4,.4,.2,4.455,-4.851,.396,.8056,.3572,-1.1628};
static const double cm4_ipt_inverse[9]={1,.0975689,.205226,1,-.113876,.133217,1,.0326151,-.676887};
static void cm4_to_ipt(const struct dvbridge_cm4_coefficients *c,const double rgb[3],double ipt[3])
{
    double lms[3];matrix_rgb(c->rgb_to_lms,rgb,lms);
    for(int i=0;i<3;i++)lms[i]=pq(fmax(0,lms[i]))/4095;
    matrix_rgb(cm4_ipt,lms,ipt);
}
static void cm4_from_ipt(const struct dvbridge_cm4_coefficients *c,const double ipt[3],double rgb[3])
{
    double lms[3];matrix_rgb(cm4_ipt_inverse,ipt,lms);
    for(int i=0;i<3;i++)lms[i]=cm4_eotf(lms[i]);
    matrix_rgb(c->lms_to_rgb,lms,rgb);
}
static bool cm4_decode(struct dvbridge_cm4_coefficients *c,const struct dvbridge_cm4_controls *raw)
{
    *c=(struct dvbridge_cm4_coefficients){.sop={1,0,1},.chroma_base=1,
        .saturation_gain=1,.mid_exponent=1};
    for(int i=0;i<6;i++)c->secondary_gain[i]=1;
    if(raw->present_fields&~31u)return false;
    if(raw->present_fields&DVBRIDGE_CM4_PRIMARY){
        for(int i=0;i<6;i++)if(raw->primary[i]>4095)return false;
        c->sop[0]=raw->primary[0]/4096.0+.5;
        c->sop[1]=raw->primary[1]/4096.0-.5;c->sop[2]=raw->primary[2]/4096.0+.5;
        c->chroma_base=exp2(((double)raw->primary[3]-2048)/4096);
        c->saturation_gain=exp2(((double)raw->primary[4]-2048)/4096);
        c->detail_mix=.30*((double)raw->primary[5]-2048)/2048;c->present=63;
    }
    if(raw->present_fields&DVBRIDGE_CM4_MID_CONTRAST){
        if(raw->mid_contrast>4095)return false;
        c->mid_exponent=exp2(((double)raw->mid_contrast-2048)/2048);c->present|=1u<<6;
    }
    if(raw->present_fields&DVBRIDGE_CM4_CLIP_TRIM){
        if(raw->clip_trim>4095)return false;
        c->clip_strength=.25*((double)raw->clip_trim-2048)/2048;c->present|=1u<<7;
    }
    for(int i=0;i<6;i++){
        if(raw->present_fields&DVBRIDGE_CM4_SATURATION){
            c->secondary_gain[i]=exp2(((double)raw->saturation[i]-128)/256);c->present|=1u<<8;
        }
        if(raw->present_fields&DVBRIDGE_CM4_HUE){
            c->secondary_rotation[i]=(3.14159265358979323846/12)*((double)raw->hue[i]-128)/128;
            c->present|=1u<<9;
        }
    }
    return true;
}
bool dvbridge_creative_cm4_coefficients(struct dvbridge_cm4_coefficients *out,
    const struct dvbridge_creative_plan *p)
{
    if(!out || !p || p->status==DVBRIDGE_CREATIVE_INVALID || !p->cm4 ||
       p->cm4_targets!=DVBRIDGE_CM4_TARGETS_RESOLVED ||
       !isfinite(p->policy.tv.peak_nits) || p->policy.tv.peak_nits<=0 ||
       p->policy.tv.peak_nits>10000 || !isfinite(p->cm4_weight) ||
       p->cm4_weight<0 || p->cm4_weight>1)return false;
    const struct dvbridge_cm4_anchor *a=p->cm4_lower.present?&p->cm4_lower:&p->cm4_upper;
    const struct dvbridge_cm4_anchor *b=p->cm4_upper.present?&p->cm4_upper:a;
    if(!a->present || !b->present)return false;
    const struct pl_raw_primaries *prim=&p->cm4_output.primaries;
    const struct pl_cie_xy *xy[]={&prim->red,&prim->green,&prim->blue,&prim->white,
        &a->target.primaries.red,&a->target.primaries.green,&a->target.primaries.blue,&a->target.primaries.white,
        &b->target.primaries.red,&b->target.primaries.green,&b->target.primaries.blue,&b->target.primaries.white};
    for(int i=0;i<12;i++)if(!isfinite(xy[i]->x) || !isfinite(xy[i]->y))return false;
    if(!pl_primaries_valid(prim) || !cm4_same_gamut(prim,&a->target.primaries) ||
       !cm4_same_gamut(prim,&b->target.primaries) ||
       (a->target.transfer!=PL_COLOR_TRC_UNKNOWN && a->target.transfer!=PL_COLOR_TRC_PQ) ||
       (b->target.transfer!=PL_COLOR_TRC_UNKNOWN && b->target.transfer!=PL_COLOR_TRC_PQ))return false;
    struct dvbridge_cm4_coefficients c,d;
    if(!cm4_decode(&c,&a->controls) || !cm4_decode(&d,&b->controls))return false;
    double w=p->cm4_lower.present && p->cm4_upper.present?p->cm4_weight:0;
#define BLEND(field) c.field+=(d.field-c.field)*w
    for(int i=0;i<3;i++)BLEND(sop[i]);
    BLEND(chroma_base);BLEND(saturation_gain);BLEND(mid_exponent);BLEND(clip_strength);BLEND(detail_mix);
    for(int i=0;i<6;i++){BLEND(secondary_gain[i]);BLEND(secondary_rotation[i]);}
#undef BLEND
    c.one_anchor=c.present^d.present;c.present|=d.present;c.peak_nits=p->policy.tv.peak_nits;
    pl_matrix3x3 forward=pl_ipt_rgb2lms(prim),inverse=pl_ipt_lms2rgb(prim),xyz=pl_get_rgb2xyz_matrix(prim);
    double sum=(double)xyz.m[1][0]+xyz.m[1][1]+xyz.m[1][2];
    if(!isfinite(sum) || sum<=0)return false;
    for(int i=0;i<3;i++){
        c.luma[i]=xyz.m[1][i]/sum;
        for(int j=0;j<3;j++){
            c.rgb_to_lms[i*3+j]=forward.m[i][j];c.lms_to_rgb[i*3+j]=inverse.m[i][j];
            if(!isfinite(c.rgb_to_lms[i*3+j]) || !isfinite(c.lms_to_rgb[i*3+j]))return false;
        }
    }
    const double vertices[6][3]={{1,0,0},{1,1,0},{0,1,0},{0,1,1},{0,0,1},{1,0,1}};
    for(int i=0;i<6;i++){
        double rgb[3],ipt[3];for(int j=0;j<3;j++)rgb[j]=vertices[i][j]*c.peak_nits/4;
        cm4_to_ipt(&c,rgb,ipt);c.hue_centres[i]=atan2(ipt[2],ipt[1]);
    }
    *out=c;return true;
}
static bool cm4_trim(const struct dvbridge_cm4_coefficients *c,const double input[3],double out[3])
{
    double rgb[3],y=0,peak=c->peak_nits;bool gray;
    for(int i=0;i<3;i++){
        if(!isfinite(input[i]))return false;
        rgb[i]=c->sop[0]==1 && c->sop[1]==0 && c->sop[2]==1?input[i]:
            peak*pow(bound(input[i]/peak*c->sop[0]+c->sop[1]),c->sop[2]);
        y+=rgb[i]*c->luma[i];
    }
    gray=rgb[0]==rgb[1] && rgb[1]==rgb[2];
    if(gray)y=rgb[0];
    if(y>0 && c->mid_exponent!=1){
        double x=bound(y/peak),a=pow(x,c->mid_exponent),b=pow(1-x,c->mid_exponent),mapped=peak*a/(a+b);
        for(int i=0;i<3;i++)rgb[i]=gray?mapped:rgb[i]*mapped/y;
    }
    y=0;for(int i=0;i<3;i++)y+=rgb[i]*c->luma[i];if(gray)y=rgb[0];
    if(y>0 && c->clip_strength!=0){
        double x=bound(y/peak),t=bound((x-.5)/.5),mapped=peak*bound(x+c->clip_strength*x*t*t*(3-2*t));
        for(int i=0;i<3;i++)rgb[i]=gray?mapped:rgb[i]*mapped/y;
    }
    bool colour=c->chroma_base!=1 || c->saturation_gain!=1;
    for(int i=0;i<6;i++)colour|=c->secondary_gain[i]!=1 || c->secondary_rotation[i]!=0;
    if(colour && fmax(fmax(rgb[0],rgb[1]),rgb[2])-fmin(fmin(rgb[0],rgb[1]),rgb[2])>1e-12){
        double ipt[3];cm4_to_ipt(c,rgb,ipt);
        if(hypot(ipt[1],ipt[2])>=1e-7){
            double z=bound(ipt[0]/(pq(peak)/4095));
            double gain=c->saturation_gain*pow(c->chroma_base,2*z-1);
            ipt[1]*=gain;ipt[2]*=gain;
            double hue=atan2(ipt[2],ipt[1]),weights[6],sum=0,log_gain=0,turn=0;
            for(int i=0;i<6;i++){weights[i]=exp(4*(cos(hue-c->hue_centres[i])-1));sum+=weights[i];}
            for(int i=0;i<6;i++){log_gain+=weights[i]/sum*log(c->secondary_gain[i]);turn+=weights[i]/sum*c->secondary_rotation[i];}
            double ct=ipt[1],cp=ipt[2];gain=exp(log_gain);
            ipt[1]=gain*(cos(turn)*ct-sin(turn)*cp);ipt[2]=gain*(sin(turn)*ct+cos(turn)*cp);
            cm4_from_ipt(c,ipt,rgb);
        }
    }
    for(int i=0;i<3;i++)if(!isfinite(rgb[i]))return false;
    memcpy(out,rgb,sizeof(rgb));return true;
}
bool dvbridge_creative_cm4_trim_rgb(const struct dvbridge_creative_plan *p,const double input[3],double out[3])
{
    struct dvbridge_cm4_coefficients c;
    return input && out && dvbridge_creative_cm4_coefficients(&c,p) && cm4_trim(&c,input,out);
}
struct trim_fit {
    struct dvbridge_cm4_coefficients c;
    struct dvbridge_creative_plan l2;
    unsigned source[5];
    double scene;
    bool cm4, signature;
    double gray_input[257], gray_source[257], gray_goal[257];
    double colour_input[18][3], colour_goal[18][3];
};

static double enhanced_nits(double value,double peak,double headroom,double scene,bool signature)
{
    double x=bound(value/peak),gate=bound(value);
    gate=gate*gate*(3-2*gate);
    double highlight=bound((x-.25)/.75);highlight=highlight*highlight*(3-2*highlight);
    double gain=scene*gate*(signature?.04:.04*fmax(0,headroom)*highlight);
    return value+gain*fmax(0,value)*(1-x);
}

static bool control_response(const struct trim_fit *f,const double words[5],
                         const double input[3],double out[3])
{
    if(!f->cm4){
        struct dvbridge_creative_plan p=f->l2;
        for(int i=0;i<5;i++)p.codes[i]=words[i];
        return dvbridge_creative_trim_rgb(&p,input,out);
    }
    struct dvbridge_cm4_coefficients c=f->c;
    c.sop[0]=words[0]/4096.0+.5;c.sop[1]=words[1]/4096.0-.5;c.sop[2]=words[2]/4096.0+.5;
    c.chroma_base=exp2(((double)words[3]-2048)/4096);
    c.saturation_gain=exp2(((double)words[4]-2048)/4096);
    return cm4_trim(&c,input,out);
}

static bool fit_response(const struct trim_fit *f,const unsigned words[5],
                         const double input[3],double out[3])
{
    double decoded[5];for(int i=0;i<5;i++)decoded[i]=words[i];
    return control_response(f,decoded,input,out);
}

static bool fit_samples(struct trim_fit *f,double headroom,double scene)
{
    f->scene=scene;
    double q=pq(f->c.peak_nits)/4095;
    for(int i=0;i<257;i++){
        double in=cm4_eotf(q*i/256),rgb[3];f->gray_input[i]=in;
        if(!fit_response(f,f->source,(double[3]){in,in,in},rgb))return false;
        f->gray_source[i]=pq(fmax(0,rgb[0]))/4095;
        f->gray_goal[i]=pq(enhanced_nits(rgb[0],f->c.peak_nits,headroom,scene,f->signature))/4095;
    }
    static const double vertices[6][3]={{1,0,0},{1,1,0},{0,1,0},{0,1,1},{0,0,1},{1,0,1}};
    for(int i=0;i<18;i++){
        double value=cm4_eotf(q*(.1+.4*(i%3))),rgb[3],goal[3],y=0;
        for(int j=0;j<3;j++)f->colour_input[i][j]=value*vertices[i/3][j];
        if(!fit_response(f,f->source,f->colour_input[i],rgb))return false;
        for(int j=0;j<3;j++)y+=rgb[j]*f->c.luma[j];
        double mapped=enhanced_nits(y,f->c.peak_nits,headroom,scene,f->signature);
        double maximum=fmax(fmax(rgb[0],rgb[1]),rgb[2]);
        double room=bound((f->c.peak_nits-maximum)/fmax(1e-6,f->c.peak_nits-y));
        mapped=y+(mapped-y)*room;
        for(int j=0;j<3;j++)goal[j]=y>0?rgb[j]*mapped/y:rgb[j];
        cm4_to_ipt(&f->c,goal,f->colour_goal[i]);
        double gain=exp2(scene*(f->signature?64:32*fmax(0,headroom))*bound(1-maximum/f->c.peak_nits)/4096);
        f->colour_goal[i][1]*=gain;f->colour_goal[i][2]*=gain;
    }
    return true;
}

static bool validate_words(const struct trim_fit *f,const unsigned words[5],
                           struct dvbridge_creative_edit_report *report)
{
    report->candidate_evaluations++;
    double last=0;
    for(int i=0;i<257;i++){
        double in=f->gray_input[i],rgb[3];
        if(!fit_response(f,words,(double[3]){in,in,in},rgb))return false;
        double q=pq(fmax(0,rgb[0]))/4095;
        if(i==0){
            bool source_lift=f->gray_source[0]>pq(0)/4095+1e-12;
            if(source_lift!=(q>pq(0)/4095+1e-12))return false;
            if(fabs(q-f->gray_source[0])>2e-5)return false;
        }else{
            if(q<last-1e-12)return false;
            if(fabs(f->gray_source[i]-f->gray_source[i-1])<=1e-12 && fabs(q-last)>2e-5)return false;
            if(f->gray_source[i]-f->gray_source[i-1]>2e-5 && q-last<=1e-12)return false;
        }
        if(in<=1 && fabs(q-f->gray_source[i])>2.0/1024)return false;
        if(f->signature && q<f->gray_source[i]-2e-5)return false;
        if(!f->signature && in<=f->c.peak_nits/4 && fabs(q-f->gray_source[i])>2.0/1024)return false;
        last=q;double err=fabs(q-f->gray_goal[i]);
        report->maximum_pq_error=fmax(report->maximum_pq_error,err);
        /* Exact gray remains achromatic; matrix residuals are not creative chroma. */
        if(fmax(fmax(rgb[0],rgb[1]),rgb[2])-fmin(fmin(rgb[0],rgb[1]),rgb[2])>1e-12){
            double ipt[3];cm4_to_ipt(&f->c,rgb,ipt);
            if(hypot(ipt[1],ipt[2])>1e-7)return false;
        }
    }
    for(int i=0;i<18;i++){
        double rgb[3],ipt[3];if(!fit_response(f,words,f->colour_input[i],rgb))return false;
        cm4_to_ipt(&f->c,rgb,ipt);
        report->maximum_pq_error=fmax(report->maximum_pq_error,fabs(ipt[0]-f->colour_goal[i][0]));
        double a=hypot(ipt[1],ipt[2]),b=hypot(f->colour_goal[i][1],f->colour_goal[i][2]);
        if(b<=1e-7){if(a>1e-7)return false;continue;}
        report->maximum_relative_chroma_error=fmax(report->maximum_relative_chroma_error,fabs(a-b)/b);
        double angle=fabs(remainder(atan2(ipt[2],ipt[1])-atan2(f->colour_goal[i][2],f->colour_goal[i][1]),2*3.14159265358979323846));
        report->maximum_hue_error=fmax(report->maximum_hue_error,angle*180/3.14159265358979323846);
    }
    return true;
}

static double fit_error(const struct trim_fit *f,const unsigned words[5])
{
    double error=0,last=0;
    for(int i=0;i<257;i+=4){
        double in=f->gray_input[i],rgb[3];
        if(!fit_response(f,words,(double[3]){in,in,in},rgb))return INFINITY;
        double q=pq(fmax(0,rgb[0]))/4095,d=(q-f->gray_goal[i])*1024/2;
        if((i==0 && (fabs(q-f->gray_source[i])>2e-5 ||
            (f->gray_source[0]>pq(0)/4095+1e-12)!=(q>pq(0)/4095+1e-12))) ||
           (in<=1 && fabs(q-f->gray_source[i])>2.0/1024) ||
           (!f->signature && in<=f->c.peak_nits/4 && fabs(q-f->gray_source[i])>2.0/1024) ||
           (f->signature && q<f->gray_source[i]-2e-5) ||
           (i && (q<last-1e-12 ||
            (fabs(f->gray_source[i]-f->gray_source[i-4])<=1e-12 && fabs(q-last)>2e-5) ||
            (f->gray_source[i]-f->gray_source[i-4]>2e-5 && q-last<=1e-12))))return INFINITY;
        last=q;
        error=fmax(error,d*d);
    }
    for(int i=0;i<18;i++){
        double rgb[3],ipt[3];if(!fit_response(f,words,f->colour_input[i],rgb))return INFINITY;
        cm4_to_ipt(&f->c,rgb,ipt);
        double chroma=hypot(f->colour_goal[i][1],f->colour_goal[i][2]);
        for(int j=0;j<3;j++){
            double scale=j?fmax(1e-7,chroma)*.02:2.0/1024;
            double d=(ipt[j]-f->colour_goal[i][j])/scale;error=fmax(error,d*d);
        }
    }
    return error;
}

static bool fit_words(struct trim_fit *f,unsigned words[5],struct dvbridge_creative_edit_report *report)
{
    memcpy(words,f->source,sizeof(f->source));
    double best=fit_error(f,words);unsigned evaluations=1;
    if(f->signature){
        unsigned seed[5];memcpy(seed,words,sizeof(seed));
        seed[0]=fmin(4095,seed[0]+floor(96*f->scene+.5));
        seed[4]=fmin(4095,seed[4]+floor(64*f->scene+.5));
        double error=fit_error(f,seed);evaluations++;
        if(error<best){best=error;memcpy(words,seed,sizeof(seed));}
    }
    /* Fixed work budget; no image readback or additional rendering pass. */
    for(unsigned pass=0;pass<2;pass++)for(unsigned step=256;step;step/=2)for(int j=0;j<5;j++){
        unsigned selected=words[j],trial[5];
        for(int direction=-1;direction<=1;direction+=2){
            int value=(int)words[j]+direction*(int)step;
            if(value<0 || value>4095 || abs(value-(int)f->source[j])>512)continue;
            memcpy(trial,words,sizeof(trial));trial[j]=value;
            double error=fit_error(f,trial);evaluations++;
            if(error<best){best=error;selected=value;}
        }
        words[j]=selected;
    }
    report->candidate_evaluations+=evaluations;
    return validate_words(f,words,report) && report->maximum_pq_error<=2.0/1024 &&
        report->maximum_relative_chroma_error<=.02 && report->maximum_hue_error<=.5;
}

static void write_l8_words(AVDOVIDmData *e,const unsigned words[5])
{
    e->l8.trim_slope=words[0];e->l8.trim_offset=words[1];e->l8.trim_power=words[2];
    e->l8.trim_chroma_weight=words[3];e->l8.trim_saturation_gain=words[4];
    for(int i=0;i<5;i++)for(unsigned bit=0;bit<12;bit++){
        unsigned pos=8+12*i+bit;uint8_t mask=1u<<(7-pos%8);
        e->dvbridge_original_bytes[pos/8]=(e->dvbridge_original_bytes[pos/8]&~mask) |
            (((words[i]>>(11-bit))&1)?mask:0);
    }
}

static bool fit_anchor(struct trim_fit *f,const struct dvbridge_creative_plan *p,
                       const AVDOVIMetadata *m,const AVDOVIDmData *e)
{
    struct dvbridge_creative_plan basis=*p;struct dvbridge_cm4_anchor a={.present=true};
    f->cm4=e->level==8;f->signature=p->policy.enhancement==DVBRIDGE_ENHANCEMENT_SIGNATURE;
    if(f->cm4){
        if(!cm4_controls(e,&a.controls))return false;
        bool resolved=cm4_preset(e->l8.target_display_index,&a.target);
        if(!resolved)for(int i=0;i<m->num_ext_blocks;i++){
            const AVDOVIDmData *t=av_dovi_get_ext(m,i);
            if(t->level==10 && t->l10.target_display_index==e->l8.target_display_index)
                resolved=cm4_custom_target(t,&a.target)==1;
        }
        /* L10 resolves absolute bounds/gamut, not a display EOTF. */
        if(!resolved || (a.target.transfer!=PL_COLOR_TRC_PQ &&
                         a.target.transfer!=PL_COLOR_TRC_UNKNOWN))return false;
        for(int i=0;i<5;i++)f->source[i]=a.controls.primary[i];
    }else{
        a.target=(struct dvbridge_cm4_target){.max_pq=e->l2.target_max_pq,
            .primaries=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),.transfer=PL_COLOR_TRC_PQ};
        a.controls.present_fields=DVBRIDGE_CM4_PRIMARY;
        for(int i=0;i<6;i++)a.controls.primary[i]=2048;
        double raw[5];controls(raw,e);for(int i=0;i<5;i++)f->source[i]=raw[i];
    }
    basis.cm4=true;basis.cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED;basis.cm4_output=a.target;
    basis.cm4_lower=a;basis.cm4_upper=(struct dvbridge_cm4_anchor){0};basis.cm4_weight=0;
    basis.policy.tv.peak_nits=cm4_eotf(a.target.max_pq/4095.0);
    f->l2=*p;f->l2.policy.tv.peak_nits=basis.policy.tv.peak_nits;
    return dvbridge_creative_cm4_coefficients(&f->c,&basis);
}

enum dvbridge_creative_status dvbridge_creative_resolve(struct dvbridge_creative_plan *out,
    const void *metadata,size_t bytes,const struct dvbridge_policy *policy)
{
    if(!out)return DVBRIDGE_CREATIVE_INVALID;
    *out=(struct dvbridge_creative_plan){.status=DVBRIDGE_CREATIVE_INVALID};
    if(!metadata || (uintptr_t)metadata%_Alignof(AVDOVIMetadata) ||
       !dvbridge_metadata_bounds(metadata,bytes) ||
       dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID ||
       (policy->mode!=DVBRIDGE_MODE_HDR10_EXPERT && policy->mode!=DVBRIDGE_MODE_ENHANCED_DV))
        return out->status;
    struct dvbridge_creative_plan p={.policy=*policy,.source_bytes=bytes,
        .source_hash=source_hash(metadata,bytes),.target_pq=pq(policy->tv.peak_nits)};
    const AVDOVIMetadata *m=metadata;const AVDOVIColorMetadata *c=av_dovi_get_color(m);
    if(c->source_min_pq>=c->source_max_pq || c->source_max_pq>4095)return out->status;
    p.master_pq=c->source_max_pq;
    const AVDOVIDmData *l1=NULL,*l3=NULL,*l9=NULL,*lower=NULL,*upper=NULL;
    double low[5],high[5];bool spatial=false;
    for(int i=0;i<5;i++)p.codes[i]=2048;
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *e=av_dovi_get_ext(m,i);
        if(e->level<32)p.preserved_levels|=1u<<e->level;
        if(e->level==1){if(l1)return out->status;l1=e;}
        if(e->level==3){if(l3)return out->status;l3=e;}
        if(e->level==9){if(l9)return out->status;l9=e;}
        if(e->level==3 || (e->level>=8 && e->level<=11) || e->level==254)p.cm4=true;
        if(e->level==3 || (e->level>=8 && e->level<=11) || e->level==254){
            uint8_t wire[32];
            if(e->dvbridge_raw_magic!=0x41424456 ||
               dvbridge_cm4_wire(e->level,e->dvbridge_original_bytes,e->dvbridge_original_length,wire)<0)
                return out->status;
            if(e->level==3){
                unsigned values[3]={e->l3.min_pq_offset,e->l3.max_pq_offset,e->l3.avg_pq_offset};
                for(int j=0;j<3;j++)if(values[j]!=((unsigned)wire[j*2]<<8|wire[j*2+1]))return out->status;
            }
        }
        if(e->level!=2)continue;
        double codes[5];controls(codes,e);
        if(!e->l2.target_max_pq || e->l2.target_max_pq>4095 || e->l2.ms_weight < -1 || e->l2.ms_weight>4095)
            return out->status;
        for(int j=0;j<5;j++)if(codes[j]>4095)return out->status;
        for(int j=0;j<i;j++){
            const AVDOVIDmData *prior=av_dovi_get_ext(m,j);
            if(prior->level==2 && prior->l2.target_max_pq==e->l2.target_max_pq)return out->status;
        }
        spatial|=e->l2.ms_weight!=-1;
        if(e->l2.target_max_pq<=p.target_pq && (!lower || e->l2.target_max_pq>lower->l2.target_max_pq))lower=e;
        if(e->l2.target_max_pq>=p.target_pq && (!upper || e->l2.target_max_pq<upper->l2.target_max_pq))upper=e;
    }
    if(p.cm4 && !cm4_targets(m,&p))return out->status;
    if(l9){
        unsigned index=l9->dvbridge_original_bytes[0];
        if(index!=l9->l9.source_primary_index)return out->status;
        if(index<3){
            static const enum pl_color_primaries prim[]={PL_COLOR_PRIM_DISPLAY_P3,
                PL_COLOR_PRIM_BT_709,PL_COLOR_PRIM_BT_2020};
            p.mastering_primaries=*pl_raw_primaries_get(prim[index]);
            p.mastering_primaries_present=true;
        }else if(index==255){
            const AVColorPrimariesDesc *parsed=&l9->l9.source_display_primaries;
            const AVCIExy *source[]={&parsed->prim.r,&parsed->prim.g,&parsed->prim.b,&parsed->wp};
            struct pl_cie_xy *xy[]={&p.mastering_primaries.red,&p.mastering_primaries.green,
                &p.mastering_primaries.blue,&p.mastering_primaries.white};
            for(int i=0;i<4;i++){
                const uint8_t *raw=l9->dvbridge_original_bytes+1+i*4;
                unsigned x=(unsigned)raw[0]<<8|raw[1],y=(unsigned)raw[2]<<8|raw[3];
                int sx=x>=32768?(int)x-65536:(int)x,sy=y>=32768?(int)y-65536:(int)y;
                if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
                   (source[i]->x.den<=0 || source[i]->y.den<=0 ||
                    (int64_t)source[i]->x.num*32767!=(int64_t)sx*source[i]->x.den ||
                    (int64_t)source[i]->y.num*32767!=(int64_t)sy*source[i]->y.den)){
                    out->reason=DVBRIDGE_CREATIVE_MASTERING_INCONSISTENT;return out->status;
                }
                xy[i]->x=(x>=32768?(int)x-65536:(int)x)/32767.0;
                xy[i]->y=(y>=32768?(int)y-65536:(int)y)/32767.0;
            }
            if(!pl_primaries_valid(&p.mastering_primaries))return out->status;
            p.mastering_primaries_present=true;
        }else if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT){
            p.status=DVBRIDGE_CREATIVE_UNSUPPORTED;
            p.reason=DVBRIDGE_CREATIVE_MASTERING_UNSUPPORTED;
            *out=p;return p.status;
        }
    }
    if(l1){
        int effective[3]={l1->l1.min_pq,l1->l1.max_pq,l1->l1.avg_pq};
        if(l3){effective[0]+=(int)l3->l3.min_pq_offset-2048;
            effective[1]+=(int)l3->l3.max_pq_offset-2048;effective[2]+=(int)l3->l3.avg_pq_offset-2048;}
        if(effective[0]<0 || effective[0]>effective[2] || effective[2]>effective[1] || effective[1]>4095)
            return out->status;
        for(int j=0;j<3;j++)p.analysis[j]=effective[j];p.l1_present=true;p.l3_present=l3!=NULL;
    }
    p.anchor_present=lower || upper;
    if(lower || upper){
        if(!lower)lower=upper;
        controls(low,lower);
        double q1=lower->l2.target_max_pq,q2;
        if(upper){controls(high,upper);q2=upper->l2.target_max_pq;}
        else {for(int j=0;j<5;j++)high[j]=2048;q2=p.master_pq;}
        double w=q2<=q1?(p.target_pq>q1?1:0):fmax(0,fmin(1,(p.target_pq-q1)/(q2-q1)));
        for(int j=0;j<5;j++)p.codes[j]=low[j]+w*(high[j]-low[j]);
    }
    p.backend=p.anchor_present?(p.cm4?DVBRIDGE_CREATIVE_CM29_COMPATIBILITY:DVBRIDGE_CREATIVE_CM29):DVBRIDGE_CREATIVE_NONE;
    p.reason=!p.anchor_present?DVBRIDGE_CREATIVE_NO_ANCHOR:p.cm4?DVBRIDGE_CREATIVE_CM4_RENDER_PARTIAL:
        spatial?DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED:DVBRIDGE_CREATIVE_OK;
    p.status=p.anchor_present?DVBRIDGE_CREATIVE_READY:DVBRIDGE_CREATIVE_NEUTRAL;
    if(policy->mode==DVBRIDGE_MODE_ENHANCED_DV && p.cm4){
        p.backend=DVBRIDGE_CREATIVE_PRESERVE_CM4;p.reason=DVBRIDGE_CREATIVE_CM4_EDIT_UNQUALIFIED;
        p.status=DVBRIDGE_CREATIVE_UNSUPPORTED;
    }else if(p.anchor_present)p.applied_levels|=1u<<2;
    if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT){
        if(p.l1_present)p.applied_levels|=1u<<1;
        if(p.l3_present && p.l1_present)p.applied_levels|=1u<<3;
        if(p.mastering_primaries_present)p.applied_levels|=1u<<9;
    }
    p.l2_coverage.present=p.anchor_present?31u:0;
    if(p.applied_levels&(1u<<2))p.l2_coverage.applied=p.l2_coverage.present;
    p.l2_coverage.preserved=p.l2_coverage.present&~p.l2_coverage.applied;
    struct dvbridge_cm4_coefficients decoded;
    if(dvbridge_creative_cm4_coefficients(&decoded,&p)){
        p.l8_coverage.present=p.l8_coverage.preserved=decoded.present;
        p.l8_coverage.one_anchor=decoded.one_anchor;
    }
    *out=p;return p.status;
}

enum dvbridge_creative_status dvbridge_creative_edit(void **output,size_t *output_bytes,
    const void *metadata,size_t bytes,const struct dvbridge_creative_plan *p,
    struct dvbridge_creative_edit_report *report)
{
    struct dvbridge_creative_edit_report local={.status=DVBRIDGE_CREATIVE_INVALID};
    if(!report)report=&local;*report=local;
    if(!output || !output_bytes)return DVBRIDGE_CREATIVE_INVALID;
    *output=NULL;*output_bytes=0;
    if(!p || p->status==DVBRIDGE_CREATIVE_INVALID || p->policy.mode!=DVBRIDGE_MODE_ENHANCED_DV ||
       !metadata || (uintptr_t)metadata%_Alignof(AVDOVIMetadata) ||
       !dvbridge_metadata_bounds(metadata,bytes) || bytes!=p->source_bytes ||
       source_hash(metadata,bytes)!=p->source_hash ||
       dvbridge_policy_validate(&p->policy)!=DVBRIDGE_POLICY_VALID)return DVBRIDGE_CREATIVE_INVALID;
    AVDOVIMetadata *m=av_memdup(metadata,bytes);if(!m)return DVBRIDGE_CREATIVE_INVALID;
    struct timespec start,end;bool timed=clock_gettime(CLOCK_MONOTONIC,&start)==0;
    bool changed=false,rejected=false,unresolved=false;
    double reference_pq=floor(pq(fmax(1000,p->policy.tv.peak_nits))+.5);
    double headroom=fmax(-.5,fmin(.5,(reference_pq-p->master_pq)/fmax(p->master_pq,1e-6))),scene=1;
    if(p->l1_present){
        if(!p->analysis[1])scene=0;
        else {double t=bound((cm4_eotf(p->analysis[2]/4095.0)/cm4_eotf(p->analysis[1]/4095.0)-.1)/.4);
            scene=1-.5*t*t*(3-2*t);}
    }
    /* Resolve every family before mutation; compatibility cannot hide an unknown L8. */
    for(int i=0;i<m->num_ext_blocks;i++){
        AVDOVIDmData *e=av_dovi_get_ext(m,i);if(e->level!=2 && e->level!=8)continue;
        struct trim_fit f={0};
        struct dvbridge_creative_coverage *coverage=e->level==8?&report->l8_coverage:&report->l2_coverage;
        if(e->level==8){
            struct dvbridge_cm4_controls raw;struct dvbridge_cm4_coefficients decoded;
            if(!cm4_controls(e,&raw) || !cm4_decode(&decoded,&raw)){av_free(m);return report->status;}
            coverage->present|=decoded.present;
        }else coverage->present|=31;
        if(!fit_anchor(&f,p,m,e)){unresolved=true;continue;}
    }
    if(!unresolved && scene!=0)for(int i=0;i<m->num_ext_blocks;i++){
        AVDOVIDmData *e=av_dovi_get_ext(m,i);if(e->level!=2 && e->level!=8)continue;
        struct trim_fit f={0};unsigned words[5];
        if(!fit_anchor(&f,p,m,e) || !fit_samples(&f,headroom,scene) || !fit_words(&f,words,report)){
            rejected=true;break;
        }
        struct dvbridge_creative_coverage *coverage=e->level==8?&report->l8_coverage:&report->l2_coverage;
        for(int j=0;j<5;j++)if(words[j]!=f.source[j]){changed=true;coverage->edited|=1u<<j;}
        if(e->level==8){
            write_l8_words(e,words);struct dvbridge_cm4_controls check;
            if(!cm4_controls(e,&check)){av_free(m);return report->status;}
        }else{
            e->l2.trim_slope=words[0];e->l2.trim_offset=words[1];e->l2.trim_power=words[2];
            e->l2.trim_chroma_weight=words[3];e->l2.trim_saturation_gain=words[4];
        }
    }
    if(rejected || unresolved){
        memcpy(m,metadata,bytes);report->l2_coverage.edited=report->l8_coverage.edited=0;
        report->status=DVBRIDGE_CREATIVE_UNSUPPORTED;
        report->reason=unresolved?DVBRIDGE_CREATIVE_EDIT_TARGET_UNRESOLVED:DVBRIDGE_CREATIVE_EDIT_NOT_REPRESENTABLE;
    }else report->status=changed?DVBRIDGE_CREATIVE_READY:DVBRIDGE_CREATIVE_NEUTRAL;
    report->l2_coverage.preserved=report->l2_coverage.present&~report->l2_coverage.edited;
    report->l8_coverage.preserved=report->l8_coverage.present&~report->l8_coverage.edited;
    report->l8_coverage.one_anchor=p->l8_coverage.one_anchor;
    if(timed && clock_gettime(CLOCK_MONOTONIC,&end)==0)
        report->fit_ns=(uint64_t)(end.tv_sec-start.tv_sec)*1000000000+end.tv_nsec-start.tv_nsec;
    *output=m;*output_bytes=bytes;
    return report->status;
}

bool dvbridge_creative_trim_rgb(const struct dvbridge_creative_plan *p,const double input[3],double out[3])
{
    if(!p || !input || !out || p->status==DVBRIDGE_CREATIVE_INVALID || p->policy.tv.peak_nits<=0)return false;
    double s=p->codes[0]/4096+.5,o=p->codes[1]/4096-.5,power=p->codes[2]/4096+.5;
    double chroma=p->codes[3]/4096-.5,gain=p->codes[4]/4096-.5,peak=p->policy.tv.peak_nits;
    double v[3],y=0;const double weights[3]={.22897,.69174,.07929};
    for(int i=0;i<3;i++){
        if(!isfinite(input[i]))return false;
        v[i]=peak*pow(fmax(0,fmin(1,input[i]/peak*s+o)),power);y+=weights[i]*v[i];
    }
    for(int i=0;i<3;i++)out[i]=(gain && y>0 && v[i]>0)?v[i]*pow((1+chroma)*v[i]/y,gain):v[i];
    return isfinite(out[0]) && isfinite(out[1]) && isfinite(out[2]);
}
