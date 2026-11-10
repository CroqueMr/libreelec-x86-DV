/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "dvbridge_gl_frame.h"
extern bool raw_native_import(struct dvbridge_gl_frame*,pl_gpu,enum dvbridge_gl_layout,
    int,int,const struct dvbridge_gl_plane[3],unsigned,bool,unsigned,unsigned*);
enum { W=256,H=4,N=W*H*4 };
int main(int argc,char**argv)
{
    assert(argc==3);bool direct=!strcmp(argv[1],"direct"),red=!strcmp(argv[1],"red");
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer* r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    unsigned char y[W*H],uv[W*H/2];
    for(int row=0;row<H;row++)for(int x=0;x<W;x++)y[row*W+x]=x;
    for(int row=0;row<H/2;row++)for(int x=0;x<W/2;x++){
        uv[(row*W/2+x)*2]=row?x*2:128;uv[(row*W/2+x)*2+1]=row?255-x*2:128;
    }
    GLuint textures[2];glGenTextures(2,textures);
    for(int i=0;i<2;i++){
        glBindTexture(GL_TEXTURE_2D,textures[i]);
        glTexImage2D(GL_TEXTURE_2D,0,i?GL_RG8:GL_R8,i?W/2:W,i?H/2:H,0,
            i?GL_RG:GL_RED,GL_UNSIGNED_BYTE,i?uv:y);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    }
    assert(glGetError()==GL_NO_ERROR);
    struct dvbridge_gl_plane planes[3]={{textures[0],W,H},{textures[1],W/2,H/2}};
    struct dvbridge_gl_frame imported={0};unsigned used;
    assert(raw_native_import(&imported,gpu.gl->gpu,DVBRIDGE_NV12,W,H,planes,0,false,AVCHROMA_LOC_LEFT,&used));
    assert(imported.frame.repr.alpha==PL_ALPHA_UNKNOWN&&used==3);
    pl_tex output=reference_texture(gpu.gl->gpu,W,H,NULL);
    struct dvbridge_policy policy={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    struct dvbridge_identity id={1,1,3};struct dvbridge_geometry g={W,H,0,0,W,H,W,H};
    if(red){
        assert(!dvbridge_render_hdr10_policy_direct(r,&policy,&id,&imported.frame,NULL,0,1,1,g,output,false,false,16));
        size_t bytes;AVDOVIMetadata* m=task3_fixture(&bytes);av_dovi_get_header(m)->bl_bit_depth=8;
        for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->curves[c].pivots[1]=255;
        struct pl_frame dv=imported.frame;
        assert(!dvbridge_render_hdr10_policy_direct(r,&policy,&id,&dv,m,bytes,1,1,g,output,false,false,16));
        dv.repr.alpha=PL_ALPHA_NONE; /* Diagnostic A/B only; never the tested native input. */
        assert(dvbridge_render_hdr10_policy_direct(r,&policy,&id,&dv,m,bytes,1,1,g,output,false,false,16));
        printf("RED native no-RPU unsupported; native DV UNKNOWN rejected while NONE control accepted\n");return 0;
    }
    bool ok=direct?dvbridge_render_hdr10_policy_direct(r,&policy,&id,&imported.frame,NULL,0,1,1,g,output,false,false,16):
        (dvbridge_render_sdr_policy_rgb(r,&policy,&id,&imported.frame,NULL,0,1,1,g)&&
         dvbridge_render_sdr_policy_resolve(r,output,false,false,16));
    if(!ok){fprintf(stderr,"%s rejected native imported HDR\n",argv[1]);return 2;}
    assert(dvbridge_render_policy_commit(r,&id,output));
    float a[N],b[N];reference_read(gpu.gl->gpu,output,0,0,W,H,a);
    FILE* f=fopen(argv[2],direct?"rb":"wb");assert(f);
    if(!direct){assert(fwrite(a,sizeof(float),N,f)==N);fclose(f);return 0;}
    assert(fread(b,sizeof(float),N,f)==N);fclose(f);
    unsigned failed=0,endpoints=0;double maximum=0,ratio=0;int worst=0;
    for(int i=0;i<N;i++)if(i%4!=3){
        double error=fabs((double)a[i]-b[i]),limit=fmax(1e-7,2e-6*fabs(b[i]));
        failed+=!isfinite(a[i])||!isfinite(b[i])||error>limit;
        endpoints+=(b[i]==0||b[i]==1)&&a[i]!=b[i];
        if(error>maximum){maximum=error;worst=i;}ratio=fmax(ratio,error/limit);
    }
    printf("{\"failed_channels\":%u,\"endpoints\":%u,\"max_abs\":%.12g,\"max_gate_ratio\":%.12g,\"worst_index\":%d,\"reference\":%.12g,\"direct\":%.12g,\"alpha\":%d,\"used\":%u}\n",
        failed,endpoints,maximum,ratio,worst,b[worst],a[worst],imported.frame.repr.alpha,used);
    return failed||endpoints?1:0;
}
