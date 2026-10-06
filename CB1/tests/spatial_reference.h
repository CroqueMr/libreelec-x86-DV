/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Frozen scalar shader for exact descriptor comparisons. */
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/custom.h>
static const char spatial_reference_header[]=
    "void accumulate(inout float sum,inout float error,float value){"
    "precise float corrected=value-error,next=sum+corrected;error=(next-sum)-corrected;sum=next;}"
    "float peak_at(ivec2 p){vec3 q=texelFetch(small_image,p,0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))return uintBitsToFloat(0x7fc00000u);"
    "return max(q.r,max(q.g,q.b));}"
    "float coordinate(int index){"
    "if(index>=1766)return 0.0;"
    "if(index>=38){int i=index-38,c=i/576;i=i%576;"
    "return texelFetch(small_image,ivec2((i%32)*4,(i/32)*4),0)[c];}"
    "if(index<32){int tile=index/2;float total=0.0,maximum=0.0;"
    "for(int y=0;y<18;y++)for(int x=0;x<32;x++){float q=peak_at(ivec2((tile%4)*32+x,(tile/4)*18+y));"
    "if(isnan(q))return q;total+=q;maximum=max(maximum,q);}return (index&1)==0?total/576.0:maximum;}"
    "float total=0.0,mass=0.0,total_error=0.0,mass_error=0.0;"
    "for(int y=0;y<72;y++)for(int x=0;x<128;x++){float q=peak_at(ivec2(x,y));if(isnan(q))return q;"
    "if(index<36){float threshold=index==32?.5:index==33?.7:index==34?.8:.9;total+=q>=threshold?1.0:0.0;}"
    "else{float w=max(q-.5,0.0);w*=w;accumulate(mass,mass_error,w);"
    "accumulate(total,total_error,w*(index==36?float(x)*2.0/127.0-1.0:float(y)*2.0/71.0-1.0));}}"
    "return index<36?total/9216.0:mass>0.0?total/mass:0.0;}";
static void spatial_reference(pl_gpu gpu,pl_tex texture,float record[1768])
{
    pl_dispatch dispatch=pl_dispatch_create(gpu->log,gpu);
    pl_tex output=reference_texture(gpu,442,1,NULL);
    struct pl_shader_desc descriptor={.desc={.name="small_image",.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=texture,.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    pl_shader shader=pl_dispatch_begin(dispatch);
    assert(pl_shader_custom(shader,&(struct pl_custom_shader){.description="Frozen spatial reference",
        .header=spatial_reference_header,.body="int i=int(gl_FragCoord.x)*4;color=vec4(coordinate(i),coordinate(i+1),coordinate(i+2),coordinate(i+3));",
        .output=PL_SHADER_SIG_COLOR,.descriptors=&descriptor,.num_descriptors=1}));
    assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=output)));
    reference_read(gpu,output,0,0,442,1,record);
    pl_tex_destroy(gpu,&output);pl_dispatch_destroy(&dispatch);
}
