/* SPDX-License-Identifier: MIT */
#include "cb1_hdr10_temporal.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    struct cb1_hdr10_temporal *ctx=cb1_hdr10_temporal_create();assert(ctx);
    cb1_hdr10_temporal_reset(ctx,11,13);
    struct cb1_hdr10_temporal_result out;
    unsigned submitted=0;
    for(unsigned picture=0;picture<480;++picture){
        unsigned target=picture+24;if(target>479)target=479;
        while(submitted<=target){
            const bool second=submitted>=24;
            struct cb1_hdr10_descriptor d={.pts=submitted/24.};
            d.global[0]=second?.2f:.1f;d.global[1]=second?.7f:.3f;d.global[2]=second?.5f:.2f;
            for(unsigned i=0;i<38;++i)d.spatial[i]=.5f;
            float motion[1728];
            for(unsigned c=0;c<3;++c)for(unsigned i=0;i<576;++i)
                motion[c*576+i]=((i%32)<16)^second?.75f:.25f;
            struct cb1_ai_identity id={11,submitted+1,13};
            assert(cb1_hdr10_temporal_push(ctx,&d,motion,id)==CB1_AI_READY);
            /* Paused resubmission must not change aggregates. */
            assert(cb1_hdr10_temporal_push(ctx,&d,motion,id)==CB1_AI_READY);
            ++submitted;
        }
        if(submitted==480)cb1_hdr10_temporal_end(ctx);
        struct cb1_ai_identity id={11,picture+1,13};
        assert(cb1_hdr10_temporal_poll(ctx,id,&out)==CB1_AI_READY);
        assert(out.id.picture==id.picture && out.observed_until<=picture/24.+1.+1e-9);
        /* Future scene pixels must not pulse the current scene's metadata. */
        unsigned average=picture<24?819:2048;
        unsigned peak=picture<24?2081:2866;
        if(out.base[1]!=average)fprintf(stderr,"picture %u: %u/%u/%u expected avg%u\n",picture,out.base[0],out.base[1],out.base[2],average);
        assert(out.base[0]==12 && out.base[1]==average && out.base[2]==peak);
        assert(cb1_hdr10_temporal_size(ctx)<=29);
    }
    out.base[0]=123;
    cb1_hdr10_temporal_reset(ctx,12,13);
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){11,1,13},&out)==CB1_AI_INVALID && out.base[0]==123);
    cb1_hdr10_temporal_destroy(&ctx);
    ctx=cb1_hdr10_temporal_create();assert(ctx);
    cb1_hdr10_temporal_reset(ctx,1,1);
    float motion[1728]={0};
    for(unsigned i=0;i<25;++i){
        struct cb1_hdr10_descriptor d={.pts=i*.04};
        d.global[1]=.5;d.global[2]=.25;
        assert(cb1_hdr10_temporal_push(ctx,&d,motion,(struct cb1_ai_identity){1,i+1,1})==CB1_AI_READY);
    }
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){1,1,1},&out)==CB1_AI_PENDING);
    assert(cb1_hdr10_temporal_advance(ctx,1.)==CB1_AI_READY);
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){1,1,1},&out)==CB1_AI_READY);
    assert(out.observed_until==.96);
    struct cb1_hdr10_descriptor next={.pts=1.};
    next.global[1]=.5;next.global[2]=.25;
    assert(cb1_hdr10_temporal_push(ctx,&next,motion,(struct cb1_ai_identity){1,26,1})==CB1_AI_READY);
    assert(cb1_hdr10_temporal_push(ctx,&next,motion,(struct cb1_ai_identity){1,27,1})==CB1_AI_INVALID);
    next.pts=1.04;
    assert(cb1_hdr10_temporal_push(ctx,&next,motion,(struct cb1_ai_identity){1,27,1})==CB1_AI_READY);
    cb1_hdr10_temporal_destroy(&ctx);
    /* A future timestamp gap cannot change an earlier one-second window. */
    struct cb1_hdr10_temporal *control=cb1_hdr10_temporal_create();assert(control);
    ctx=cb1_hdr10_temporal_create();assert(ctx);
    cb1_hdr10_temporal_reset(control,2,3);cb1_hdr10_temporal_reset(ctx,2,3);
    struct cb1_hdr10_descriptor first={.pts=0};
    first.global[0]=.1f;first.global[1]=.5f;first.global[2]=.25f;
    const struct cb1_ai_identity before_gap={2,1,3},after_gap={2,2,3};
    assert(cb1_hdr10_temporal_push(control,&first,motion,before_gap)==CB1_AI_READY);
    assert(cb1_hdr10_temporal_push(ctx,&first,motion,before_gap)==CB1_AI_READY);
    assert(cb1_hdr10_temporal_advance(control,1.)==CB1_AI_READY);
    struct cb1_hdr10_temporal_result expected;
    assert(cb1_hdr10_temporal_poll(control,before_gap,&expected)==CB1_AI_READY);
    first.pts=2.;first.global[0]=.2f;first.global[1]=.8f;first.global[2]=.75f;
    assert(cb1_hdr10_temporal_push(ctx,&first,motion,after_gap)==CB1_AI_READY);
    assert(cb1_hdr10_temporal_poll(ctx,before_gap,&out)==CB1_AI_READY);
    for(unsigned i=0;i<3;++i)assert(out.base[i]==expected.base[i]);
    for(unsigned i=0;i<222;++i)assert(out.calibration[i]==expected.calibration[i]);
    assert(out.observed_until==0.);
    assert(cb1_hdr10_temporal_advance(ctx,3.)==CB1_AI_READY);
    assert(cb1_hdr10_temporal_poll(ctx,after_gap,&out)==CB1_AI_READY);
    assert(out.base[0]==12 && out.base[1]==3071 && out.base[2]==3276);
    assert(out.observed_until==2.);
    cb1_hdr10_temporal_destroy(&control);cb1_hdr10_temporal_destroy(&ctx);
    /* Exposure changes are not scene cuts and must retain real source peaks. */
    ctx=cb1_hdr10_temporal_create();assert(ctx);
    cb1_hdr10_temporal_reset(ctx,3,4);
    for(unsigned i=0;i<25;++i){
        const bool flash=i==24;
        struct cb1_hdr10_descriptor d={.pts=i/24.};
        d.global[0]=flash?.2f:.1f;d.global[1]=flash?.7f:.3f;d.global[2]=flash?.5f:.2f;
        for(unsigned c=0;c<3;++c)for(unsigned j=0;j<576;++j)
            motion[c*576+j]=((j%32)<16?.3f:.1f)+(flash?.2f:0);
        assert(cb1_hdr10_temporal_push(ctx,&d,motion,(struct cb1_ai_identity){3,i+1,4})==CB1_AI_READY);
    }
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){3,1,4},&out)==CB1_AI_READY);
    assert(out.base[1]==868 && out.base[2]==2866 && fabs(out.peak-.7f)<1e-9);
    cb1_hdr10_temporal_end(ctx);
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){3,25,4},&out)==CB1_AI_READY);
    assert(out.base[2]==2866 && fabs(out.peak-.7f)<1e-9);
    cb1_hdr10_temporal_destroy(&ctx);
    /* An irregular cadence may expose a future cut before its 200 ms confirmation. */
    ctx=cb1_hdr10_temporal_create();assert(ctx);
    cb1_hdr10_temporal_reset(ctx,4,5);
    const double times[]={0.,.2,1.1,1.7};
    float calibration[222];
    for(unsigned i=0;i<4;++i){
        const bool second=i>=2;
        struct cb1_hdr10_descriptor d={.pts=times[i]};
        d.global[0]=second?.2f:.1f;d.global[1]=second?.7f:.3f;d.global[2]=second?.5f:.2f;
        for(unsigned c=0;c<3;++c)for(unsigned j=0;j<576;++j)
            motion[c*576+j]=((j%32)<16)^second?.75f:.25f;
        assert(cb1_hdr10_temporal_push(ctx,&d,motion,(struct cb1_ai_identity){4,i+1,5})==CB1_AI_READY);
        if(i==2){
            assert(cb1_hdr10_temporal_advance(ctx,1.2)==CB1_AI_READY);
            assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){4,2,5},&out)==CB1_AI_READY);
            assert(out.base[1]==819 && out.base[2]==2081);
            memcpy(calibration,out.calibration,sizeof(calibration));
        }
    }
    cb1_hdr10_temporal_end(ctx);
    assert(cb1_hdr10_temporal_poll(ctx,(struct cb1_ai_identity){4,3,5},&out)==CB1_AI_READY);
    assert(out.base[1]==2048 && out.base[2]==2866);
    assert(!memcmp(calibration,out.calibration,sizeof(calibration)));
    cb1_hdr10_temporal_destroy(&ctx);
    puts("Bounded temporal cuts, pause, reset and long baseline passed");
}
