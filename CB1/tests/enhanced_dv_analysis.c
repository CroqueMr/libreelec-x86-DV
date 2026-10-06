/* Pure native analysis fixture, not a runtime geometry eligibility claim. */
#include "reference_test.h"
#define CB1_TEST_LEGACY_ANALYSIS 1
#include "../src/dvbridge_render.c"
#include <time.h>
int main(int argc,char **argv)
{
    bool uniform=argc==2 && !strcmp(argv[1],"uniform");float constant=0;
    unsigned w,h,left,top,right,bottom;
    assert(scanf("%u%u%u%u%u%u",&w,&h,&left,&top,&right,&bottom)==6);
    assert(w && h && w<=3840 && h<=2160 && (uniform || w*h<=4096) && left<right && top<bottom && right<=w && bottom<=h);
    float *image=uniform?NULL:calloc(w*h*4,sizeof(float));assert(uniform || image);
    if(uniform)assert(scanf("%f",&constant)==1 && isfinite(constant) && constant>=0 && constant<=1);
    for(unsigned i=0;!uniform && i<w*h;i++){
        assert(scanf("%f%f%f",image+4*i,image+4*i+1,image+4*i+2)==3);image[4*i+3]=1;
        for(unsigned c=0;c<3;c++)assert(isfinite(image[4*i+c]) && image[4*i+c]>=0 && image[4*i+c]<=1);
    }
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_retirement_owner *o=dvbridge_retirement_owner_create(g.gl->gpu);assert(o);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(o);assert(r);
    if(!dv_allocate(r)){dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&o));free(image);reference_gpu_destroy(&g);return 77;}
    pl_tex_clear(r->gpu,r->rgb,(float[4]){constant,constant,constant,1});
    if(!uniform){
        glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,r->rgb,NULL,NULL,NULL));
        glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,h,GL_RGBA,GL_FLOAT,image);glBindTexture(GL_TEXTURE_2D,0);free(image);
    }
    if(uniform){uint32_t bits;memcpy(&bits,&constant,4);fprintf(stderr,"UNIFORM exact FP32 clear input=%a bits=%08x raster=%ux%u active=%u,%u,%u,%u\n",constant,bits,w,h,left,top,right,bottom);}
    r->dv.active=true;r->dv.output.value.identity=(struct dvbridge_identity){17,29,43};
    memcpy(r->dv.output.value.margins,(unsigned[4]){left,3840-right,top,2160-bottom},4*sizeof(unsigned));
    assert(glGetError()==GL_NO_ERROR && dv_analyze(r));
    GLenum status=GL_TIMEOUT_EXPIRED;unsigned checks=0;
    for(;checks<10000 && status==GL_TIMEOUT_EXPIRED;checks++){
        status=r->dv.wait_sync(r->dv.fence,0,0);
        if(status==GL_TIMEOUT_EXPIRED)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(status==GL_ALREADY_SIGNALED || status==GL_CONDITION_SATISFIED);
    uint32_t record[12];memcpy(record,r->dv.mapped,sizeof(record));
    r->dv.delete_sync(r->dv.fence);r->dv.fence=NULL;
    fprintf(stderr,"UNIT native genuine fence result=%x callbacks=%u record_bytes=48 GLerror=%x\n",status,checks,glGetError());
    size_t bytes;r->dv.source_metadata=task3_fixture(&bytes);assert(r->dv.source_metadata);
    r->dv.output.value.nominal_max_nits=10000;
    r->dv.output.value.output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL;
    assert(dv_derive(r,record));
    printf("{\"raw_record\":[");for(unsigned i=0;i<12;i++)printf("%s%u",i?",":"",record[i]);
    printf("],\"statistics\":[%.17g,%.17g,%.17g]}\n",r->dv.output.value.statistics[0],r->dv.output.value.statistics[1],r->dv.output.value.statistics[2]);
    dvbridge_render_dv_policy_cancel(r);assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&o));reference_gpu_destroy(&g);
}
