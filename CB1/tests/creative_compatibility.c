/* SPDX-License-Identifier: MIT */
#include "dvbridge_creative.h"
#include "cb1_dv_enhanced.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum dvbridge_creative_status beta5_resolve(struct dvbridge_creative_plan *,const void *,size_t,const struct dvbridge_policy *);
double beta5_scene(const struct dvbridge_creative_plan *);
bool beta5_trim(const struct dvbridge_creative_plan *,const double *,double *);
bool beta5_coefficients(struct dvbridge_cm4_coefficients *,const struct dvbridge_creative_plan *);
bool beta5_apply(const struct dvbridge_cm4_coefficients *,const double *,double *);
bool beta5_source(struct cb1_dv_enhanced_source *,const void *,size_t,const struct dvbridge_policy *);
bool beta5_source_b(struct cb1_dv_enhanced_source *,const void *,size_t,const struct dvbridge_policy *);
enum dvbridge_creative_status beta5_edit(void **,size_t *,const void *,size_t,const struct dvbridge_creative_plan *,struct dvbridge_creative_edit_report *);

static uint32_t random_state=0x320c014a;
static unsigned step;
static uint64_t bytes_compared;
static uint32_t next(void){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void same(const void *a,const void *b,size_t size,const char *field)
{
    if(memcmp(a,b,size)){fprintf(stderr,"Creative mismatch step=%u field=%s\n",step,field);abort();}
    bytes_compared+=size;
}
#define EQ(field) same(&a->field,&b->field,sizeof(a->field),#field)
static void target(const struct dvbridge_cm4_target *a,const struct dvbridge_cm4_target *b)
{EQ(display_index);EQ(min_pq);EQ(max_pq);EQ(primaries);EQ(transfer);EQ(origin);EQ(min_pq_present);}
static void anchor(const struct dvbridge_cm4_anchor *a,const struct dvbridge_cm4_anchor *b)
{
    EQ(present);target(&a->target,&b->target);
    EQ(controls.primary);EQ(controls.mid_contrast);EQ(controls.clip_trim);
    EQ(controls.saturation);EQ(controls.hue);EQ(controls.present_fields);
}
static void coverage(const struct dvbridge_creative_coverage *a,const struct dvbridge_creative_coverage *b)
{EQ(present);EQ(applied);EQ(preserved);EQ(edited);EQ(one_anchor);}
static void plan(const struct dvbridge_creative_plan *a,const struct dvbridge_creative_plan *b)
{
    EQ(status);EQ(backend);EQ(reason);EQ(policy.revision);EQ(policy.mode);EQ(policy.tv.peak_nits);
    EQ(policy.tv.panel);EQ(policy.tv.gamut);EQ(policy.adaptive);EQ(analysis);EQ(target_pq);EQ(master_pq);EQ(codes);
    EQ(mastering_primaries);EQ(applied_levels);EQ(preserved_levels);EQ(source_hash);EQ(source_bytes);
    EQ(cm4);EQ(l1_present);EQ(l3_present);EQ(anchor_present);EQ(mastering_primaries_present);
    anchor(&a->cm4_lower,&b->cm4_lower);anchor(&a->cm4_upper,&b->cm4_upper);
    target(&a->cm4_output,&b->cm4_output);EQ(cm4_targets);EQ(cm4_weight);
    coverage(&a->l2_coverage,&b->l2_coverage);coverage(&a->l8_coverage,&b->l8_coverage);
    EQ(l2_detail.state);EQ(l2_detail.level);EQ(l2_detail.num_anchors);EQ(l2_detail.codes);EQ(l2_detail.target_pq);
    EQ(l2_detail.upper_weight);EQ(l2_detail.code);EQ(l2_detail.executed);
}
static void coefficients(const struct dvbridge_cm4_coefficients *a,const struct dvbridge_cm4_coefficients *b)
{
    EQ(peak_nits);EQ(sop);EQ(chroma_base);EQ(saturation_gain);EQ(mid_exponent);EQ(clip_strength);EQ(detail_mix);
    EQ(secondary_gain);EQ(secondary_rotation);EQ(luma);EQ(hue_centres);EQ(rgb_to_lms);EQ(lms_to_rgb);EQ(present);EQ(one_anchor);
}
static void source(const struct cb1_dv_enhanced_source *a,const struct cb1_dv_enhanced_source *b)
{
    EQ(master);EQ(analysis);EQ(l1_present);EQ(family);EQ(count);EQ(weights);
    anchor(&a->anchors[0],&b->anchors[0]);anchor(&a->anchors[1],&b->anchors[1]);
}
static void report(const struct dvbridge_creative_edit_report *a,const struct dvbridge_creative_edit_report *b)
{
    EQ(status);EQ(reason);coverage(&a->l2_coverage,&b->l2_coverage);coverage(&a->l8_coverage,&b->l8_coverage);
    EQ(maximum_pq_error);EQ(maximum_relative_chroma_error);EQ(maximum_hue_error);
    EQ(reference_error_before);EQ(reference_error_after);EQ(candidate_evaluations);EQ(cache_hit);
}
#undef EQ

static void put(uint8_t *bytes,unsigned position,unsigned width,unsigned value)
{
    for(unsigned bit=0;bit<width;bit++){
        unsigned index=position+bit;uint8_t mask=1u<<(7-index%8);
        bytes[index/8]=(bytes[index/8]&~mask)|((value>>(width-bit-1)&1)?mask:0);
    }
}
static AVDOVIDmData cm4(unsigned index,unsigned length)
{
    AVDOVIDmData e={.level=8,.dvbridge_raw_magic=0x41424456,.dvbridge_original_length=length};
    e.l8.target_display_index=index;e.dvbridge_original_bytes[0]=index;
    unsigned words[6];for(unsigned i=0;i<6;i++){words[i]=next()%4096;put(e.dvbridge_original_bytes,8+12*i,12,words[i]);}
    e.l8.trim_slope=words[0];e.l8.trim_offset=words[1];e.l8.trim_power=words[2];
    e.l8.trim_chroma_weight=words[3];e.l8.trim_saturation_gain=words[4];e.l8.ms_weight=words[5];
    if(length>=12){e.l8.target_mid_contrast=next()%4096;put(e.dvbridge_original_bytes,80,12,e.l8.target_mid_contrast);}
    if(length>=13){e.l8.clip_trim=next()%4096;put(e.dvbridge_original_bytes,92,12,e.l8.clip_trim);}
    for(unsigned i=0;i<6;i++){
        if(length>=19){e.l8.saturation_vector_field[i]=next();e.dvbridge_original_bytes[13+i]=e.l8.saturation_vector_field[i];}
        if(length>=25){e.l8.hue_vector_field[i]=next();e.dvbridge_original_bytes[19+i]=e.l8.hue_vector_field[i];}
    }
    return e;
}
int main(void)
{
    unsigned rgb_ok=0,plans_ok=0,cm4_ok=0,guidance_ok=0;
    for(step=0;step<50000;step++){
        struct dvbridge_creative_plan p={.status=DVBRIDGE_CREATIVE_READY,.policy.tv.peak_nits=50+next()%9951};
        for(unsigned i=0;i<5;i++)p.codes[i]=(next()%16381)/4.0;
        double input[3],old[3],current[3];for(unsigned i=0;i<3;i++)input[i]=(int)(next()%13001)-500;
        if(step%997==0)input[step%3]=NAN;
        if(step%31==0)for(unsigned i=0;i<5;i++)p.codes[i]=2048;
        bool a=beta5_trim(&p,input,old),b=dvbridge_creative_trim_rgb(&p,input,current);
        same(&a,&b,sizeof(a),"trim-admission");
        if(a){
#ifdef MUTATE_CREATIVE
            current[0]=nextafter(current[0],INFINITY);
#endif
            same(old,current,sizeof(old),"trim-rgb");rgb_ok++;
        }
    }
    size_t bytes;AVDOVIMetadata *m=av_dovi_metadata_alloc(&bytes);assert(m);
    void *copy=av_malloc(bytes);assert(copy);
    for(step=0;step<6000;step++){
        AVDOVIColorMetadata *color=av_dovi_get_color(m);*color=(AVDOVIColorMetadata){.source_max_pq=3500};
        m->num_ext_blocks=1;
        *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3000,.avg_pq=1000}};
        unsigned anchors=step%6;
        for(unsigned i=0;i<anchors;i++){
            AVDOVIDmData *e=av_dovi_get_ext(m,m->num_ext_blocks++);
            *e=(AVDOVIDmData){.level=2};e->l2.target_max_pq=1700+400*i;
            e->l2.trim_slope=next()%4096;e->l2.trim_offset=next()%4096;e->l2.trim_power=next()%4096;
            e->l2.trim_chroma_weight=next()%4096;e->l2.trim_saturation_gain=next()%4096;
            e->l2.ms_weight=step%3?-1:(int)(next()%4096);
        }
        if(step%3==0){
            const unsigned lengths[]={10,12,13,19,25};
            for(unsigned i=0;i<2;i++){
                *av_dovi_get_ext(m,m->num_ext_blocks++)=cm4(50+i,lengths[(step+i)%5]);
                AVDOVIDmData *e=av_dovi_get_ext(m,m->num_ext_blocks++);
                *e=(AVDOVIDmData){.level=10,.l10={.target_display_index=50+i,.target_max_pq=2400+800*i,.target_primary_index=2},
                    .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=5};
                e->dvbridge_original_bytes[0]=50+i;put(e->dvbridge_original_bytes,8,12,e->l10.target_max_pq);
                e->dvbridge_original_bytes[4]=2;
            }
        }
        struct dvbridge_policy policy={.revision=step+1,.mode=step%2?DVBRIDGE_MODE_ENHANCED_DV:DVBRIDGE_MODE_HDR10_EXPERT,
            .tv={.peak_nits=50+next()%9951,.panel=DVBRIDGE_PANEL_OLED,.gamut=DVBRIDGE_GAMUT_BT2020}};
        switch(step%23){
        case 0:m->num_ext_blocks=0;break;
        case 1:if(anchors)av_dovi_get_ext(m,1)->l2.trim_power=4096;break;
        case 2:if(anchors>1)av_dovi_get_ext(m,2)->l2.target_max_pq=av_dovi_get_ext(m,1)->l2.target_max_pq;break;
        case 3:av_dovi_get_ext(m,0)->l1.avg_pq=3500;break;
        case 4:policy.tv.peak_nits=NAN;break;
        case 5:color->source_max_pq=4096;break;
        case 6:if(anchors)av_dovi_get_ext(m,1)->l2.ms_weight=-2;break;
        case 7:policy.tv.gamut=DVBRIDGE_GAMUT_P3_D65;break;
        default:break;
        }
        memcpy(copy,m,bytes);
        struct dvbridge_creative_plan a,b;
        enum dvbridge_creative_status sa=beta5_resolve(&a,m,bytes,&policy),sb=dvbridge_creative_resolve(&b,m,bytes,&policy);
        same(&sa,&sb,sizeof(sa),"resolve-status");plan(&a,&b);
        if(sa!=DVBRIDGE_CREATIVE_INVALID){
            plans_ok++;double wa=beta5_scene(&a),wb=dvbridge_creative_scene_weight(&b);same(&wa,&wb,sizeof(wa),"scene-weight");
            struct dvbridge_cm4_coefficients ca,cb;
            bool ac=beta5_coefficients(&ca,&a),bc=dvbridge_creative_cm4_coefficients(&cb,&b);
            same(&ac,&bc,sizeof(ac),"CM4-admission");
            if(ac){
                cm4_ok++;coefficients(&ca,&cb);
                for(unsigned sample=0;sample<8;sample++){
                    double input[3],oa[3],ob[3];for(unsigned i=0;i<3;i++)input[i]=next()%10001;
                    bool av=beta5_apply(&ca,input,oa),bv=dvbridge_creative_cm4_apply(&cb,input,ob);
                    same(&av,&bv,sizeof(av),"CM4-pixel-admission");if(av)same(oa,ob,sizeof(oa),"CM4-rgb");
                }
            }
        }
        if(policy.mode==DVBRIDGE_MODE_ENHANCED_DV){
            struct cb1_dv_enhanced_source ga,gb;
            bool av=beta5_source(&ga,m,bytes,&policy),bv=dvbridge_creative_enhanced_source(&gb,m,bytes,&policy);
            same(&av,&bv,sizeof(av),"guidance-admission");if(av){source(&ga,&gb);guidance_ok++;}
            av=beta5_source_b(&ga,m,bytes,&policy);bv=dvbridge_creative_enhanced_source_b(&gb,m,bytes,&policy);
            same(&av,&bv,sizeof(av),"guidance-B-admission");if(av)source(&ga,&gb);
        }
        assert(!memcmp(copy,m,bytes));
    }
    assert(rgb_ok==49949 && plans_ok==4740 && cm4_ok==1479 && guidance_ok==2261);
    const double peaks[4]={300,1000,2500,10000};
    for(step=0;step<4;step++){
        m->num_ext_blocks=2;
        *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3000,.avg_pq=1000}};
        *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,.trim_slope=2048,
            .trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,.trim_saturation_gain=2048,.ms_weight=-1}};
        av_dovi_get_color(m)->source_max_pq=3500;
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
            .tv={.peak_nits=peaks[step],.gamut=DVBRIDGE_GAMUT_BT2020,.panel=DVBRIDGE_PANEL_OLED}};
        struct dvbridge_creative_plan a,b;assert(beta5_resolve(&a,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        assert(dvbridge_creative_resolve(&b,m,bytes,&policy)!=DVBRIDGE_CREATIVE_INVALID);
        void *oa=NULL,*ob=NULL;size_t na=0,nb=0;struct dvbridge_creative_edit_report ra,rb;
        enum dvbridge_creative_status sa=beta5_edit(&oa,&na,m,bytes,&a,&ra),sb=dvbridge_creative_edit(&ob,&nb,m,bytes,&b,&rb);
        same(&sa,&sb,sizeof(sa),"edit-status");same(&na,&nb,sizeof(na),"edit-size");report(&ra,&rb);
        assert((oa!=NULL)==(ob!=NULL));if(oa)same(oa,ob,na,"edited-metadata");av_free(oa);av_free(ob);
    }
    printf("{\"trim_cases\":50000,\"trim_accepted\":%u,\"metadata_cases\":6000,\"plans_accepted\":%u,\"CM4_accepted\":%u,\"guidance_accepted\":%u,\"edit_cases\":4,\"bytes_compared\":%llu,\"exact\":true}\n",
        rgb_ok,plans_ok,cm4_ok,guidance_ok,(unsigned long long)bytes_compared);
    av_free(copy);av_free(m);return 0;
}
