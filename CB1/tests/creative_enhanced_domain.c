/* SPDX-License-Identifier: GPL-3.0-only */
#include "task3_fixture.h"
#include "../src/dvbridge_creative.c"
#include <assert.h>
#include <stdio.h>

static AVDOVIDmData trim(unsigned level,unsigned target)
{
    AVDOVIDmData e={.level=level};
    if(level==2){
        e.l2.target_max_pq=(unsigned)floor(pq(target)+.5);
        e.l2.trim_slope=e.l2.trim_offset=e.l2.trim_power=2048;
        e.l2.trim_chroma_weight=e.l2.trim_saturation_gain=2048;e.l2.ms_weight=-1;
    }else{
        e.l8.target_display_index=target==600?28:49;
        e.l8.trim_slope=e.l8.trim_offset=e.l8.trim_power=2048;
        e.l8.trim_chroma_weight=e.l8.trim_saturation_gain=e.l8.ms_weight=2048;
        e.dvbridge_raw_magic=0x41424456;e.dvbridge_original_length=10;
        const uint8_t raw[]={0,0x80,0x08,0x00,0x80,0x08,0x00,0x80,0x08,0x00};
        memcpy(e.dvbridge_original_bytes,raw,sizeof(raw));
        e.dvbridge_original_bytes[0]=e.l8.target_display_index;
    }
    return e;
}

int main(int argc,char **argv)
{
    assert(argc==2);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_creative_plan p;
    *av_dovi_get_ext(m,0)=trim(8,1000);
    av_dovi_get_color(m)->source_max_pq=(unsigned)floor(pq(1000)+.5);
    if(!strcmp(argv[1],"objective-json")){
        const unsigned masters[]={500,1000,4000},targets[]={600,1000,2300};
        const double samples[][3]={{100,100,100},{500,500,500},{500,250,100},
            {750,375,75},{0,0,0},{.01,.001,0}};
        puts("[");
        for(unsigned mi=0;mi<3;mi++)for(unsigned preset=1;preset<2;preset++)for(unsigned i=0;i<6;i++){
            struct trim_fit f={0};policy.tv.peak_nits=targets[mi];
            av_dovi_get_color(m)->source_max_pq=(unsigned)floor(pq(masters[mi])+.5);
            dvbridge_creative_resolve(&p,m,bytes,&policy);
            assert(fit_anchor(&f,&p,m,av_dovi_get_ext(m,0)));
            double y=0,out[3];for(unsigned j=0;j<3;j++)y+=samples[i][j]*f.c.luma[j];
            double goal=enhanced_nits(y,masters[mi],targets[mi]),maximum=fmax(samples[i][0],fmax(samples[i][1],samples[i][2]));
            if(maximum>0)goal=fmin(goal,y*fmax(1,targets[mi]/maximum));
            for(unsigned j=0;j<3;j++)out[j]=y>0?samples[i][j]*goal/y:samples[i][j];
            printf("%s{\"master\":%u,\"target\":%u,\"preset\":%u,\"input\":[%.17g,%.17g,%.17g],\"output\":[%.17g,%.17g,%.17g]}",
                mi || i?",\n":"",masters[mi],targets[mi],preset,
                samples[i][0],samples[i][1],samples[i][2],out[0],out[1],out[2]);
        }
        puts("\n]");av_free(m);return 0;
    }else if(!strcmp(argv[1],"matrix")){
        const unsigned masters[]={500,1000,4000},targets[]={400,600,1000,2000,2300,4000,10000};
        for(unsigned mi=0;mi<3;mi++)for(unsigned ti=0;ti<7;ti++)
        for(unsigned family=0;family<4;family++)for(unsigned authored=0;authored<2;authored++)
        for(unsigned scene=0;scene<2;scene++)for(unsigned preset=1;preset<2;preset++){
            m->num_ext_blocks=0;
            if(family&1)*av_dovi_get_ext(m,m->num_ext_blocks++)=trim(2,600);
            if(family&2)*av_dovi_get_ext(m,m->num_ext_blocks++)=trim(8,1000);
            av_dovi_get_color(m)->source_max_pq=(unsigned)floor(pq(masters[mi])+.5);
            for(int i=0;i<m->num_ext_blocks;i++){
                AVDOVIDmData *e=av_dovi_get_ext(m,i);
                if(authored){
                    if(e->level==2)e->l2.trim_power=2304;
                    else{unsigned words[5]={2048,2048,2304,2048,2048};write_l8_words(e,words);}
                }
            }
            *av_dovi_get_ext(m,m->num_ext_blocks++)=(AVDOVIDmData){.level=1,
                .l1={.max_pq=av_dovi_get_color(m)->source_max_pq,
                    .avg_pq=(unsigned)floor(pq(masters[mi]*(scene?.5:.05))+.5)}};
            policy.tv.peak_nits=targets[ti];
            dvbridge_creative_resolve(&p,m,bytes,&policy);
            void *before=av_memdup(m,bytes);assert(before);
            void *edited=NULL;size_t n=0;struct dvbridge_creative_edit_report report;
            unsigned status=dvbridge_creative_edit(&edited,&n,m,bytes,&p,&report);
            assert(status!=DVBRIDGE_CREATIVE_INVALID && n==bytes && !memcmp(before,m,bytes));
            assert(!memcmp(av_dovi_get_color(m),av_dovi_get_color(edited),sizeof(AVDOVIColorMetadata)));
            assert(!memcmp(av_dovi_get_ext(m,m->num_ext_blocks-1),av_dovi_get_ext(edited,m->num_ext_blocks-1),sizeof(AVDOVIDmData)));
            if(status!=DVBRIDGE_CREATIVE_READY)assert(!memcmp(edited,m,bytes));
            if(!preset && targets[ti]<=cm4_eotf(p.master_pq/4095))assert(!memcmp(edited,m,bytes));
            printf("{\"master\":%u,\"target\":%u,\"family\":%u,\"authored\":%u,\"scene\":%u,\"preset\":%u,\"status\":%u,\"reason\":%u,\"evaluations\":%u,\"fit_ns\":%llu,\"error_before\":%.9g,\"error_after\":%.9g}\n",
                masters[mi],targets[ti],family,authored,scene,preset,status,report.reason,report.candidate_evaluations,(unsigned long long)report.fit_ns,
                report.reference_error_before,report.reference_error_after);
            av_free(before);av_free(edited);
        }
    }else if(!strcmp(argv[1],"representable")){
        policy.tv.peak_nits=1000;
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        struct trim_fit f={0};assert(fit_anchor(&f,&p,m,av_dovi_get_ext(m,0)));
        assert(fit_samples(&f,cm4_eotf(p.master_pq/4095)));
        unsigned reference[5];memcpy(reference,f.source,sizeof(reference));reference[0]+=32;
        for(unsigned i=0;i<257;i++){
            double v=f.gray_input[i],out[3];assert(fit_response(&f,reference,(double[3]){v,v,v},out));
            f.gray_goal[i]=pq(out[0])/4095;
        }
        for(unsigned i=0;i<24;i++){
            assert(fit_response(&f,reference,f.colour_input[i],f.colour_rgb_goal[i]));
            cm4_to_ipt(&f.c,f.colour_rgb_goal[i],f.colour_goal[i]);
        }
        struct dvbridge_creative_edit_report report={0};unsigned result[5];
        assert(fit_words(&f,result,&report));
        assert(report.reference_error_after<=1 && report.reference_error_after<report.reference_error_before*.9);
    }else if(!strcmp(argv[1],"objective")){
        const double input[]={0,100,250,500,750,1000},natural[]={0,100,250,668.518518518519,1472.22222222222,2300};
        const double signature[]={0,105.4,278.125,768.796296296297,1637.84722222222,2300};
        for(unsigned i=0;i<6;i++){
            assert(fabs(enhanced_nits(input[i],1000,2300)-signature[i])<1e-8);
        }
        double last=0;
        for(unsigned i=0;i<=10000;i++){
            double v=enhanced_nits(i*.1,1000,2300);assert(v>=last);last=v;
        }
    }else if(!strcmp(argv[1],"identity")){
        av_dovi_get_color(m)->source_max_pq=(unsigned)floor(pq(500)+.5);
        policy.tv.peak_nits=400;
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        void *edited=NULL;size_t n=0;
        assert(dvbridge_creative_edit(&edited,&n,m,bytes,&p,NULL)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(n==bytes && !memcmp(edited,m,bytes));av_free(edited);
    }else if(!strcmp(argv[1],"domain")){
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        struct trim_fit f={0};assert(fit_anchor(&f,&p,m,av_dovi_get_ext(m,0)));
        assert(fabs(f.c.peak_nits-2300)<1e-9 && "Fit must use the requested display domain, not the authored anchor peak");
    }else if(!strcmp(argv[1],"sample-range")){
        
        av_dovi_get_color(m)->source_max_pq=(unsigned)floor(pq(5)+.5);
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        struct trim_fit f={0};assert(fit_anchor(&f,&p,m,av_dovi_get_ext(m,0)));
        assert(fit_samples(&f,5));
        for(unsigned i=0;i<257;i++)assert(f.gray_input[i]<=5+1e-9);
        for(unsigned i=0;i<24;i++)for(unsigned j=0;j<3;j++)assert(f.colour_input[i][j]<=5+1e-9);
    }else if(!strcmp(argv[1],"resolved")){
        policy.tv.peak_nits=800;m->num_ext_blocks=2;
        for(unsigned level=2;level<=8;level+=6){
            *av_dovi_get_ext(m,0)=trim(level,600);*av_dovi_get_ext(m,1)=trim(level,1000);
            dvbridge_creative_resolve(&p,m,bytes,&policy);
            struct trim_fit f={0};assert(fit_anchor(&f,&p,m,av_dovi_get_ext(m,0)));
            unsigned words[5];memcpy(words,f.source,sizeof(words));words[0]+=64;
            double got[3],want[3],in[3]={400,200,100};assert(fit_response(&f,words,in,got));
            AVDOVIDmData *e=av_dovi_get_ext(m,0);
            if(level==8)write_l8_words(e,words);else e->l2.trim_slope=words[0];
            struct dvbridge_creative_plan candidate;
            dvbridge_creative_resolve(&candidate,m,bytes,&policy);
            assert(level==8?dvbridge_creative_cm4_trim_rgb(&candidate,in,want):dvbridge_creative_trim_rgb(&candidate,in,want));
            for(unsigned j=0;j<3;j++)assert(fabs(got[j]-want[j])<1e-8 && "Fit must include the anchor interpolation used by the final resolver");
        }
    }else if(!strcmp(argv[1],"excluded")){
        m->num_ext_blocks=2;
        *av_dovi_get_ext(m,1)=trim(8,1000);
        AVDOVIDmData *sdr=av_dovi_get_ext(m,1);
        sdr->l8.target_display_index=sdr->dvbridge_original_bytes[0]=1;
        policy.tv.peak_nits=800;
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        assert(p.cm4_targets==DVBRIDGE_CM4_TARGETS_RESOLVED);
        void *edited=NULL;size_t n=0;struct dvbridge_creative_edit_report report;
        assert(dvbridge_creative_edit(&edited,&n,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(!memcmp(edited,m,bytes));av_free(edited);
    }else if(!strcmp(argv[1],"inactive")){
        *av_dovi_get_ext(m,0)=trim(2,600);
        dvbridge_creative_resolve(&p,m,bytes,&policy);
        void *edited=NULL;size_t n=0;struct dvbridge_creative_edit_report report;
        assert(dvbridge_creative_edit(&edited,&n,m,bytes,&p,&report)==DVBRIDGE_CREATIVE_UNSUPPORTED);
        assert(report.reason==DVBRIDGE_CREATIVE_EDIT_NOT_REPRESENTABLE && !memcmp(edited,m,bytes));av_free(edited);
    }else assert(!"Unknown case");
    av_free(m);printf("PASS %s\n",argv[1]);
}
