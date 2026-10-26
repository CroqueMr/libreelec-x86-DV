/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "../src/dvbridge_render.c"

/* A stale specialization silently selects a different analysis or transport. */
static void check_program(struct dvbridge_renderer *r,bool lookup,const char *prefix,
                          unsigned lanes)
{
    assert(dve_program(r,lookup));
    GLint linked,size[3];
    glGetProgramiv(r->enhanced_program,GL_LINK_STATUS,&linked);
    glGetProgramiv(r->enhanced_program,GL_COMPUTE_WORK_GROUP_SIZE,size);
    assert(linked && size[0]==(int)lanes && size[1]==1 && size[2]==1);
    GLuint shader;GLsizei count;
    glGetAttachedShaders(r->enhanced_program,1,&count,&shader);assert(count==1);
    GLint length;glGetShaderiv(shader,GL_SHADER_SOURCE_LENGTH,&length);
    char *source=malloc(length);assert(source);
    glGetShaderSource(shader,length,NULL,source);
    assert(!strncmp(source,prefix,strlen(prefix)));
    /* Include the compiler's actual input in the before/after witness. */
    uint64_t hash=14695981039346656037ULL;
    for(char *p=source;*p;p++){hash^=(unsigned char)*p;hash*=1099511628211ULL;}
    printf("shader %016llx\n",(unsigned long long)hash);
    free(source);
    GLuint cached=r->enhanced_program;
    assert(dve_program(r,lookup) && r->enhanced_program==cached);
    assert(glGetError()==GL_NO_ERROR);
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    const char *base="#version 310 es\nprecision highp float;";
    check_program(r,false,base,128);
    check_program(r,true,"#version 310 es\n#define CB1_DVE_PQ_LOOKUP 1\nprecision",128);
    check_program(r,false,base,128);
    struct {bool *value;const char *prefix;unsigned lanes;} cases[]={
        {&r->enhanced_analytic_pq,"#define CB1_DVE_ANALYTIC_PQ 1\n",64},
        {&r->enhanced_linear,"#define CB1_DVE_LINEAR_INPUT 1\n",128},
        {&r->enhanced_prepack,"#define CB1_DVE_PREPACK 1\n",128},
        {&r->ai_enhanced_fused,"#define CB1_DVE_STATS_ONLY 1\n",128},
        {&r->ai_enhanced_prepack,"#define CB1_DVE_STATS_ONLY 1\n#define CB1_DVE_QUAD_STATS 1\n",128},
        {&r->enhanced_authored,"#define CB1_DVE_AUTHORED 1\n",128},
        {&r->enhanced_skip_aux,"#define CB1_DVE_SKIP_AUX 1\n",128},
        {&r->enhanced_authored_curve,"#define CB1_DVE_AUTHORED_CURVE 1\n",128},
    };
    for(unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++){
        char prefix[160];snprintf(prefix,sizeof(prefix),"#version 310 es\n%sprecision",cases[i].prefix);
        if(cases[i].value==&r->ai_enhanced_prepack)r->ai_enhanced_fused=true;
        *cases[i].value=true;check_program(r,false,prefix,cases[i].lanes);
        if(cases[i].value==&r->ai_enhanced_prepack)r->ai_enhanced_fused=false;
        *cases[i].value=false;check_program(r,false,base,128);
    }
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS shader specialization transitions and cache reuse");
}
