/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10_expert.h"
#include "hdr10_expert_fixture.h"
#include <math.h>
#include <stdio.h>

static double pq(double nits)
{
    double x=pow(nits/10000,2610.0/16384);
    return pow((3424.0/4096+(2413.0/128)*x)/(1+(2392.0/128)*x),2523.0/32);
}

int main(void)
{
    size_t bytes;AVDOVIMetadata *m=expert_fixture(&bytes,false);
    m->num_ext_blocks=1;
    const double peaks[]={50,600,1000,2000},blacks[]={0,.005,.05,.5};
    double largest=0;
    for(unsigned p=0;p<4;p++)for(unsigned b=0;b<4;b++){
        struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
            .tv={peaks[p],DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020},.expert_black_nits=blacks[b]};
        struct cb1_hdr10_expert_plan plans[2];
        unsigned below=floor(pq(peaks[p])*4095);
        for(unsigned side=0;side<2;side++){
            av_dovi_get_ext(m,0)->l1.max_pq=below+side;
            assert(cb1_hdr10_expert_prepare(&plans[side],&policy,m,bytes,false));
        }
        const double probes[]={1,10,peaks[p]*.1};
        for(unsigned i=0;i<3;i++){
            double a=pl_tone_map_sample(pq(probes[i]),&plans[0].tone);
            double c=pl_tone_map_sample(pq(probes[i]),&plans[1].tone);
            double difference=fabs(a-c)*4095;largest=fmax(largest,difference);
            if(difference>=1)fprintf(stderr,"Expert threshold P=%g B=%g input=%g jump=%.9g PQ12\n",
                peaks[p],blacks[b],probes[i],difference);
            assert(difference<1);
        }
    }
    /* Same scene, manual target crosses the scene maximum in 0.1-nit steps. */
    av_dovi_get_ext(m,0)->l1.max_pq=3079;
    for(unsigned b=0;b<4;b++){
        double previous=0;
        for(unsigned step=0;step<21;step++){
            struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
                .tv={999.6+.1*step,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020},.expert_black_nits=blacks[b]};
            struct cb1_hdr10_expert_plan plan;
            assert(cb1_hdr10_expert_prepare(&plan,&policy,m,bytes,false));
            double value=pl_tone_map_sample(pq(100),&plan.tone);
            if(step)assert(fabs(value-previous)*4095<1);
            previous=value;
        }
    }
    av_free(m);
    printf("PASS Expert adjacent scene/target thresholds, maximum jump %.9g PQ12\n",largest);
}
