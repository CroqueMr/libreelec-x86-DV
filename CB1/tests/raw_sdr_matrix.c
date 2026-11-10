/* SPDX-License-Identifier: MIT */
/* Reuse the frozen matrix's native output/readback/fixed comparison helpers. */
#define main prior_dv_matrix_main
#include "sdr_direct_matrix.c"
#undef main
#include "dvbridge_gl_frame.h"
extern bool raw_native_import(struct dvbridge_gl_frame*,pl_gpu,enum dvbridge_gl_layout,
    int,int,const struct dvbridge_gl_plane[3],unsigned,bool,unsigned,unsigned*);

struct native_planes { GLuint textures[3];struct dvbridge_gl_plane planes[3]; };
static struct native_planes native_planes(enum dvbridge_gl_layout layout,bool residual)
{
    struct native_planes out={0};
    bool planar=layout==DVBRIDGE_YUV420P10||layout==DVBRIDGE_YUV444P10;
    bool packed=layout==DVBRIDGE_Y416,sub=layout!=DVBRIDGE_YUV444P10&&!packed;
    unsigned depth=layout==DVBRIDGE_NV12?8:layout==DVBRIDGE_P012?12:layout==DVBRIDGE_P016?16:10;
    unsigned shift=layout==DVBRIDGE_P010||packed?6:layout==DVBRIDGE_P012?4:0;
    unsigned count=packed?1:planar?3:2;glGenTextures(count,out.textures);
    for(unsigned plane=0;plane<count;plane++){
        int width=plane&&sub?W/2:W,height=plane&&sub?H/2:H;
        int components=packed?4:!planar&&plane?2:1;
        uint8_t u8[N];uint16_t u16[N];
        for(int y=0;y<height;y++)for(int x=0;x<width;x++)for(int c=0;c<components;c++){
            int channel=packed?(c==0?1:c==1?0:c):plane?(planar?plane:c+1):0;
            float v=channel==0?x/(float)(width-1):y==0?.5f:channel==1?.05f+.9f*x/(width-1):.95f-.9f*x/(width-1);
            if(channel==0&&y==4)v*=.02f;
            if(channel==0&&y==5)v=.5f+.5f*v;
            if(residual)v=.5f+(channel==0?.03f*(x/(float)(width-1)-.5f):channel==1?.005f:-.005f);
            unsigned code=lrintf(fminf(1,fmaxf(0,v))*((1u<<depth)-1));
            int i=(y*width+x)*components+c;u8[i]=code;u16[i]=packed&&c==3?65535:code<<shift;
        }
        glBindTexture(GL_TEXTURE_2D,out.textures[plane]);
        GLenum format=components==4?GL_RGBA:components==2?GL_RG:GL_RED;
        GLint internal=components==4?0x805B:depth==8?(components==2?GL_RG8:GL_R8):(components==2?0x822C:0x822A);
        glTexImage2D(GL_TEXTURE_2D,0,internal,width,height,0,format,depth==8?GL_UNSIGNED_BYTE:GL_UNSIGNED_SHORT,depth==8?(void*)u8:(void*)u16);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        out.planes[plane]=(struct dvbridge_gl_plane){out.textures[plane],width,height};
    }
    assert(glGetError()==GL_NO_ERROR);return out;
}

static unsigned run_case(struct reference_gpu* gpu,struct dvbridge_renderer* r,bool direct,
    const char* root,const char* name,enum dvbridge_gl_layout layout,unsigned metadata,
    bool sourceFull,unsigned chroma,const struct dvbridge_sdr_profile* profile,
    bool unorm,unsigned bits,bool limited,bool flip,const void* dv,size_t bytes,bool fel)
{
    struct native_planes planes=native_planes(layout,false),enhanced={0};
    struct dvbridge_gl_frame frame={0},el={0};unsigned used;
    assert(raw_native_import(&frame,gpu->gl->gpu,layout,W,H,planes.planes,dv?100:metadata,sourceFull,chroma,&used));
    if(fel){
        enhanced=native_planes(layout,true);
        assert(raw_native_import(&el,gpu->gl->gpu,layout,W,H,enhanced.planes,100,sourceFull,chroma,&used));
        frame.frame.enhancement_layer=&el.frame;
    }
    assert(frame.frame.repr.alpha==PL_ALPHA_UNKNOWN);
    const struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR,.sdr=*profile};
    const struct dvbridge_identity id={1,1,3};pl_tex out=target(gpu->gl->gpu,unorm,bits);assert(out);
    printf("CASE %s native_alpha=%d imported_used=%u\n",name,frame.frame.repr.alpha,used);fflush(stdout);
    if(!draw(r,direct,&p,&id,&frame.frame,dv,bytes,out,flip,limited,bits))exit(2);
    if(!compare(root,name,direct,gpu->gl->gpu,out,unorm,bits))exit(1);
    if(unorm){
        float first[N],again[N];read_target(gpu->gl->gpu,out,true,first);
        assert(draw(r,direct,&p,&id,&frame.frame,dv,bytes,out,flip,limited,bits));
        read_target(gpu->gl->gpu,out,true,again);assert(!memcmp(first,again,sizeof(first)));
    }
    pl_tex_destroy(gpu->gl->gpu,&out);dvbridge_gl_frame_release(&el);dvbridge_gl_frame_release(&frame);
    glDeleteTextures(3,enhanced.textures);glDeleteTextures(3,planes.textures);return 1;
}

int main(int argc,char**argv)
{
    assert(argc==3);bool direct=!strcmp(argv[1],"direct");
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer* r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    const struct dvbridge_sdr_profile profiles[]={{DVBRIDGE_SDR_REFERENCE},{DVBRIDGE_SDR_BRIGHT},
        {DVBRIDGE_SDR_CUSTOM,20,1.8,0},{DVBRIDGE_SDR_CUSTOM,500,2.8,5},{DVBRIDGE_SDR_CUSTOM,100,2.3,.02}};
    const unsigned chromas[]={AVCHROMA_LOC_LEFT,AVCHROMA_LOC_TOPLEFT,AVCHROMA_LOC_CENTER};
    unsigned cases=0;char name[100];
    for(unsigned layout=0;layout<7;layout++)for(unsigned full=0;full<2;full++)
    for(unsigned c=0;c<3;c++)for(unsigned processing=0;processing<2;processing++)for(unsigned p=0;p<5;p++){
        dvbridge_renderer_set_processing_optimizations(r,processing);
        snprintf(name,sizeof(name),"raw-l%u-full%u-c%u-opt%u-p%u",layout,full,c,processing,p);
        cases+=run_case(&gpu,r,direct,argv[2],name,layout,0,full,chromas[c],&profiles[p],false,16,false,false,NULL,0,false);
    }
    dvbridge_renderer_set_processing_optimizations(r,false);
    for(unsigned meta=0;meta<11;meta++)for(unsigned layout=0;layout<2;layout++)
    for(unsigned full=0;full<2;full++)for(unsigned p=0;p<2;p++){
        snprintf(name,sizeof(name),"metadata-m%u-l%u-full%u-p%u",meta,layout,full,p);
        cases+=run_case(&gpu,r,direct,argv[2],name,layout,meta,full,AVCHROMA_LOC_LEFT,&profiles[p?3:0],false,16,false,false,NULL,0,false);
    }
    const unsigned depths[]={8,10,12,16};
    for(unsigned d=0;d<4;d++)for(unsigned limited=0;limited<2;limited++)
    for(unsigned flip=0;flip<2;flip++)for(unsigned p=0;p<5;p++)for(unsigned l=0;l<2;l++){
        snprintf(name,sizeof(name),"raw-code-b%u-l%u-f%u-p%u-layout%u",depths[d],limited,flip,p,l);
        cases+=run_case(&gpu,r,direct,argv[2],name,l?DVBRIDGE_Y416:DVBRIDGE_P010,3,false,
            AVCHROMA_LOC_LEFT,&profiles[p],true,depths[d],limited,flip,NULL,0,false);
    }
    size_t bytes;AVDOVIMetadata* m=task3_fixture(&bytes);
    av_dovi_get_header(m)->vdr_bit_depth=12;
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(unsigned variant=0;variant<5;variant++)for(unsigned processing=0;processing<2;processing++)for(unsigned p=0;p<5;p++){
        bool fel=variant>=3,mmr=variant==2||variant==4;
        av_dovi_get_header(m)->disable_residual_flag=!fel;
        for(unsigned c=0;c<3;c++){
            AVDOVIReshapingCurve* curve=&av_dovi_get_mapping(m)->curves[c];
            memset(curve,0,sizeof(*curve));curve->num_pivots=2;curve->pivots[1]=1023;
            curve->mapping_idc[0]=mmr?AV_DOVI_MAPPING_MMR:AV_DOVI_MAPPING_POLYNOMIAL;
            curve->poly_order[0]=variant?2:1;curve->poly_coef[0][1]=variant?3500:4096;curve->poly_coef[0][2]=variant?512:0;
            if(mmr){
                curve->mmr_order[0]=2;curve->mmr_constant[0]=128;
                for(unsigned order=0;order<2;order++)for(unsigned axis=0;axis<7;axis++)
                    curve->mmr_coef[0][order][axis]=(axis&1?-1:1)*(25+axis*7+order*13);
                curve->mmr_coef[0][0][c]+=3000;
            }
            av_dovi_get_mapping(m)->nlq[c].nlq_offset=512;
            av_dovi_get_mapping(m)->nlq[c].linear_deadzone_slope=4;
            av_dovi_get_mapping(m)->nlq[c].vdr_in_max=4096;
        }
        dvbridge_renderer_set_processing_optimizations(r,processing);
        snprintf(name,sizeof(name),"native-dv-v%u-opt%u-p%u",variant,processing,p);
        cases+=run_case(&gpu,r,direct,argv[2],name,DVBRIDGE_P010,100,false,AVCHROMA_LOC_LEFT,
            &profiles[p],false,16,false,false,m,bytes,fel);
    }
    av_free(m);assert(cases==718);printf("COMPLETE %u native-import cases\n",cases);
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&gpu);return 0;
}
