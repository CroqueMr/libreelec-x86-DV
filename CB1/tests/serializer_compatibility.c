/* SPDX-License-Identifier: MIT */
#include "dvbridge_metadata.h"
#include <libavutil/mem.h>
#include <libavutil/crc.h>
#include <libavutil/bswap.h>
#include <assert.h>

static uint32_t random_state=0x7376bc12;
static uint32_t random_value(void)
{
    random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;
    return random_state;
}
static uint64_t digest=UINT64_C(14695981039346656037);
static bool capture;
static void record(const void *p,size_t n)
{
    const uint8_t *v=p;for(size_t i=0;i<n;i++)digest=(digest^v[i])*UINT64_C(1099511628211);
    if(capture)assert(fwrite(p,1,n,stdout)==n);
}
static void record_result(bool ok,const struct dvbridge_dv *state)
{
    record(&ok,sizeof(ok));
    if(!ok)return;
    record(&state->size,sizeof(state->size));
    record(&state->previous_size,sizeof(state->previous_size));
    record(&state->count,sizeof(state->count));
    record(state->payload,state->size);record(state->previous,state->previous_size);
    record(state->packets,sizeof(state->packets));record(&state->id,sizeof(state->id));
    record(&state->frames,sizeof(state->frames));record(&state->changes,sizeof(state->changes));
    record(&state->last_pts,sizeof(state->last_pts));
}
static void geometry_cases(void)
{
    const int dimensions[][2]={{1920,1080},{2560,1440},{3840,2160},{1920,800},
        {3840,1600},{2534,1030},{1280,720},{64,64}};
    for(unsigned i=0;i<10000;i++){
        struct dvbridge_dv state={0};
        int w=dimensions[i%8][0],h=dimensions[i%8][1];
        int dw=i%2?w:3840,dh=lround((double)h*dw/w);
        if(dh>2160){dh=2160;dw=(int)lround((double)w*dh/h)&~1;}
        int x=((3840-dw)/2)&~1,y=(2160-dh)/2;
        switch(i%13){
        case 0:x++;break;case 1:dw++;break;case 2:x=3840;break;
        case 3:y=2160;break;case 4:w=0;break;case 5:h=-1;break;
        case 6:dh+=10;break;case 7:dw=3842;break;default:break;
        }
        bool ok=dvbridge_dv_geometry(&state,w,h,x,y,dw,dh);
        record(&ok,sizeof(ok));
        if(!ok)continue;
        record(&state.source_w,sizeof(state.source_w));record(&state.source_h,sizeof(state.source_h));
        record(&state.dest_x,sizeof(state.dest_x));record(&state.dest_y,sizeof(state.dest_y));
        record(&state.dest_w,sizeof(state.dest_w));record(&state.dest_h,sizeof(state.dest_h));
        for(unsigned j=0;j<5;j++){
            unsigned out[4],left=j==0?(unsigned)w:(i+j)%31,right=j==1?(unsigned)w:0;
            unsigned top=j==2?(unsigned)h:(i+j)%53,bottom=j==3?(unsigned)h:0;
            bool area=dvbridge_dv_area(&state,left,right,top,bottom,out);
            record(&area,sizeof(area));if(area)record(out,sizeof(out));
        }
    }
}
static void capacity_cases(AVDOVIMetadata *m)
{
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    *h=(AVDOVIRpuDataHeader){.disable_residual_flag=1};
    *c=(AVDOVIColorMetadata){.signal_eotf=65535,.source_max_pq=3079};
    for(int i=0;i<AV_DOVI_MAX_EXT_BLOCKS;i++){
        AVDOVIDmData *e=av_dovi_get_ext(m,i);*e=(AVDOVIDmData){.level=i?2:1};
        if(!i){e->l1.max_pq=3079;e->l1.avg_pq=1800;continue;}
        e->l2.target_max_pq=2000+i;e->l2.trim_slope=e->l2.trim_offset=e->l2.trim_power=2048;
        e->l2.trim_chroma_weight=e->l2.trim_saturation_gain=2048;e->l2.ms_weight=-1;
    }
    const unsigned margins[4]={0};
    for(unsigned fixture=0;fixture<6;fixture++){
        struct dvbridge_dv state={0};
        m->num_ext_blocks=fixture==0?22:fixture<3?23:fixture==5?AV_DOVI_MAX_EXT_BLOCKS+1:AV_DOVI_MAX_EXT_BLOCKS;
        if(fixture==1 || fixture==2)*av_dovi_get_ext(m,22)=(AVDOVIDmData){
            .level=8,.dvbridge_raw_magic=0x41424456,.dvbridge_original_length=fixture==1?10:12};
        if(fixture==3)for(int i=1;i<AV_DOVI_MAX_EXT_BLOCKS;i++)av_dovi_get_ext(m,i)->level=6;
        if(fixture==4)for(int i=1;i<AV_DOVI_MAX_EXT_BLOCKS;i++)av_dovi_get_ext(m,i)->level=1;
        bool ok=dvbridge_dv_metadata_output(&state,m,0,margins,false);
        assert(ok==(fixture==0 || fixture==1 || fixture==3));
        if(fixture<2)assert(state.size==(fixture==0?494:512) && state.count==5);
        record_result(ok,&state);
    }
}

int main(int argc,char **argv)
{
    capture=argc==2 && strcmp(argv[1],"--capture")==0;
    static const uint8_t crc_input[]="123456789";
    assert(dvbridge_dv_crc(crc_input,9)==0x0376e6e7);
    assert(av_bswap32(av_crc(av_crc_get_table(AV_CRC_32_IEEE),UINT32_MAX,crc_input,9))==0x0376e6e7);
    size_t size;
    AVDOVIMetadata *m=av_dovi_metadata_alloc(&size);
    void *copy=av_malloc(size);assert(m && copy);
    geometry_cases();capacity_cases(m);
    struct dvbridge_dv state={0};
    unsigned accepted=0,rejected=0;
    const unsigned levels[]={3,4,8,9,10,11,254,6};
    const unsigned lengths[]={5,3,10,1,5,4,2,0};
    for(unsigned iteration=0;iteration<50000;iteration++){
        if(iteration%64==0)state=(struct dvbridge_dv){0};
        AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
        AVDOVIColorMetadata *c=av_dovi_get_color(m);
        AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
        memset(h,0,sizeof(*h));memset(c,0,sizeof(*c));memset(mapping,0,sizeof(*mapping));
        h->disable_residual_flag=1;h->vdr_bit_depth=12;
        c->signal_eotf=65535;c->signal_bit_depth=12;c->signal_full_range_flag=1;
        c->source_max_pq=2048+random_value()%2048;c->source_min_pq=random_value()%20;
        c->source_diagonal=random_value()%200;c->scene_refresh_flag=random_value()%2;
        for(int i=0;i<9;i++){
            c->ycc_to_rgb_matrix[i]=(AVRational){dvbridge_output_ycc[i],8192};
            c->rgb_to_lms_matrix[i]=(AVRational){dvbridge_output_lms[i],16384};
        }
        for(int i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
        state.source_transport=(iteration%3)==0;state.fel_verified=(iteration%5)==0;
        m->num_ext_blocks=1+random_value()%12;
        for(int i=0;i<m->num_ext_blocks;i++){
            AVDOVIDmData *e=av_dovi_get_ext(m,i);memset(e,0,sizeof(*e));
            e->level=i?2:1;
            if(!i){e->l1.max_pq=3000;e->l1.avg_pq=random_value()%3001;continue;}
            unsigned kind=random_value()%12;
            if(kind<8){
                e->level=levels[kind];e->dvbridge_raw_magic=0x41424456;
                e->dvbridge_original_length=lengths[kind];
                if(e->level==8){const unsigned lengths8[]={10,12,13,19,25};e->dvbridge_original_length=lengths8[random_value()%5];}
                if(e->level==9 && random_value()%2){e->dvbridge_original_bytes[0]=255;e->dvbridge_original_length=17;}
                if(e->level==10 && random_value()%2){e->dvbridge_original_bytes[4]=255;e->dvbridge_original_length=21;}
                if(e->level==3 || e->level==4 || e->level==8){
                    for(unsigned j=0;j<e->dvbridge_original_length;j++)e->dvbridge_original_bytes[j]=random_value();
                    if(e->level==3)e->dvbridge_original_bytes[4]&=0xf0;
                    if(e->level==8 && e->dvbridge_original_length==12)e->dvbridge_original_bytes[11]&=0xf0;
                }
            }else{
                e->l2.target_max_pq=1000+i*51;e->l2.trim_slope=random_value()%4096;
                e->l2.trim_offset=random_value()%4096;e->l2.trim_power=random_value()%4096;
                e->l2.trim_chroma_weight=random_value()%4096;e->l2.trim_saturation_gain=random_value()%4096;
                e->l2.ms_weight=random_value()%2?(int)(random_value()%4096):-1;
            }
        }
        unsigned margins[4]={0,0,random_value()%300,random_value()%300};
        if(iteration%7==0){AVDOVIDmData *e=av_dovi_get_ext(m,m->num_ext_blocks++);memset(e,0,sizeof(*e));e->level=5;}
        switch(iteration%31){
        case 0:h->disable_residual_flag=0;break;
        case 1:c->signal_color_space=2;break;
        case 2:c->signal_eotf=1;break;
        case 3:c->source_min_pq=c->source_max_pq+1;break;
        case 4:av_dovi_get_ext(m,0)->l1.max_pq=4096;break;
        case 5:c->ycc_to_rgb_matrix[0].den=0;break;
        case 6:av_dovi_get_ext(m,0)->level=19;break;
        case 7:if(m->num_ext_blocks>1)av_dovi_get_ext(m,1)->level=1;break;
        case 8:if(m->num_ext_blocks>1)av_dovi_get_ext(m,1)->dvbridge_original_length=31;break;
        case 9:c->signal_eotf_param1=1;break;
        case 10:if(m->num_ext_blocks>1)av_dovi_get_ext(m,1)->level=5;break;
        case 11:c->ycc_to_rgb_offset[0].num=2;break;
        default:break;
        }
        if(iteration%2 && m->num_ext_blocks>1){
            AVDOVIDmData temporary=*av_dovi_get_ext(m,0);
            *av_dovi_get_ext(m,0)=*av_dovi_get_ext(m,m->num_ext_blocks-1);
            *av_dovi_get_ext(m,m->num_ext_blocks-1)=temporary;
        }
        memcpy(copy,m,size);
        bool eligibility=dvbridge_dv_source_transport(m),canonical=dvbridge_dv_source_matches_output(m);
        record(&eligibility,sizeof(eligibility));record(&canonical,sizeof(canonical));
        double pts=iteration%13==0?state.last_pts:iteration%17==0?state.last_pts-1:state.last_pts+1./30;
        bool ok=dvbridge_dv_metadata_output(&state,m,pts,margins,iteration%11==0);
        assert(!memcmp(copy,m,size));
        if(!ok){record_result(ok,&state);rejected++;continue;}
        accepted++;
#ifdef MUTATE_OUTPUT
        state.payload[2]^=1;
#endif
        record_result(ok,&state);
    }
    assert(accepted==36477 && rejected==13523);
    if(!capture)printf("{\"accepted\":%u,\"rejected\":%u,\"digest\":\"%016llx\"}\n",accepted,rejected,(unsigned long long)digest);
    av_free(copy);av_free(m);return 0;
}
