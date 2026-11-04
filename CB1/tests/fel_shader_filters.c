/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "dvbridge_gl_frame.h"
#if CB1_FEL_FILTER_API < 2
extern void dvbridge_renderer_set_fel_filter(struct dvbridge_renderer *,unsigned) __attribute__((weak));
#endif

static int clampi(int x,int lo,int hi){return x<lo?lo:x>hi?hi:x;}
static int code(int c,int x,int y,bool edge)
{
    return edge?((x==3 && y==4)?1023:0):384+((x*3+y*5+c)%5)*64;
}
static double fetch(const int *a,int w,int h,int x,int y)
{return a[clampi(y,0,h-1)*w+clampi(x,0,w-1)];}
static double linear(const int *a,int w,int h,double x,double y)
{
    int ix=floor(x),iy=floor(y);double fx=x-ix,fy=y-iy;
    return (1-fy)*((1-fx)*fetch(a,w,h,ix,iy)+fx*fetch(a,w,h,ix+1,iy))+
        fy*((1-fx)*fetch(a,w,h,ix,iy+1)+fx*fetch(a,w,h,ix+1,iy+1));
}
static int *annex_b(const int *a,int w,int h,bool chroma)
{
    int *v=malloc((size_t)w*h*2*sizeof(int)),*out=malloc((size_t)w*h*4*sizeof(int));assert(v && out);
    for(int y=0;y<2*h;y++)for(int x=0;x<w;x++){
        int n=y/2,sum;
        if(chroma)sum=(y&1)?192*fetch(a,w,h,x,n)+64*fetch(a,w,h,x,n+1):64*fetch(a,w,h,x,n-1)+192*fetch(a,w,h,x,n);
        else if(y&1)sum=-9*fetch(a,w,h,x,n-1)+111*fetch(a,w,h,x,n)+29*fetch(a,w,h,x,n+1)-3*fetch(a,w,h,x,n+2);
        else sum=-3*fetch(a,w,h,x,n-2)+29*fetch(a,w,h,x,n-1)+111*fetch(a,w,h,x,n)-9*fetch(a,w,h,x,n+1);
        v[y*w+x]=clampi((sum+(chroma?128:64))>>(chroma?8:7),0,65535);
    }
    const int weights[]={22,94,-524,2456,2456,-524,94,22};
    for(int y=0;y<2*h;y++)for(int x=0;x<2*w;x++){
        int n=x/2,sum=0;
        if(x&1){for(int i=0;i<8;i++)sum+=weights[i]*fetch(v,w,2*h,n+i-3,y);sum=clampi((sum+2048)>>12,0,65535);}
        else sum=v[y*w+n];
        out[y*2*w+x]=sum;
    }
    free(v);return out;
}

static void qualify(struct reference_gpu *g,int filter,bool planar,bool top,bool flip,bool edge,bool same,bool padded)
{
    const int w=64,h=48,ew=same?w:w/2,eh=same?h:h/2,bh=h+(padded?16:0);
    pl_gpu gpu=g->gl->gpu;pl_tex planes[3]={0};struct dvbridge_gl_plane handles[3]={0};
    int *raw[3]={0},*scaled[3]={0};
    for(int c=0;c<3;c++){
        int sw=c?ew/2:ew,sh=c?eh/2:eh;
        raw[c]=malloc((size_t)sw*sh*sizeof(int));assert(raw[c]);
        for(int y=0;y<sh;y++)for(int x=0;x<sw;x++)raw[c][y*sw+x]=code(c,x,flip?sh-1-y:y,edge);
        if(filter==2){
            if(!same)scaled[c]=annex_b(raw[c],sw,sh,c!=0);
            else {scaled[c]=malloc((size_t)sw*sh*sizeof(int));assert(scaled[c]);memcpy(scaled[c],raw[c],(size_t)sw*sh*sizeof(int));}
        }
    }
    for(int p=0;p<(planar?3:2);p++){
        int sw=p?ew/2:ew,sh=p?eh/2:eh,n=(!planar && p)?2:1;
        uint16_t *data=malloc((size_t)sw*sh*n*2);assert(data);
        for(int y=0;y<sh;y++)for(int x=0;x<sw;x++)for(int c=0;c<n;c++)
            data[(y*sw+x)*n+c]=code(p+c,x,y,edge)<<(planar?0:6);
        pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,n,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
        planes[p]=pl_tex_create(gpu,pl_tex_params(.w=sw,.h=sh,.format=fmt,.sampleable=true,.initial_data=data));assert(planes[p]);free(data);
        handles[p]=(struct dvbridge_gl_plane){pl_opengl_unwrap(gpu,planes[p],NULL,NULL,NULL),sw,sh};
    }
    struct dvbridge_gl_frame el={0};assert(dvbridge_gl_frame_import(&el,gpu,planar?DVBRIDGE_YUV420P10:DVBRIDGE_P010,ew,eh,handles));
    dvbridge_gl_frame_set_chroma(&el,top?PL_CHROMA_TOP_LEFT:PL_CHROMA_LEFT);
    for(int p=0;p<el.frame.num_planes;p++)el.frame.planes[p].flipped=flip;
    float base[w*bh*4],full[w*h*4],actual[w*h*4],expected[w*h*4];
    memset(base,0,sizeof(base));
    for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<4;c++){
        base[(y*w+x)*4+c]=c==3?1:.2f+c*.01f+(y&1)*.03f;
        double value=0;
        if(c<3){
            int sw=c?ew/2:ew,sh=c?eh/2:eh;
            if(filter==2)value=0; // Reference oracle uses independent integer 4:2:0 grids below.
            else {
                double ratio=same?1:2,scale=c?2*ratio:ratio;
                double sx=(same?0:-.5)-(c?.5*ratio:0),sy=c && top?-.5*ratio:0;
                value=linear(raw[c],sw,sh,(x+.5-sx)/scale-.5,(y+.5-sy)/scale-.5);
            }
        }
        full[(y*w+x)*4+c]=c==3?1:(float)(filter==2?value/1023.:value*64/65535.);
    }
    pl_tex bl=reference_texture(gpu,w,bh,base),oracle=reference_texture(gpu,w,h,full);
    struct pl_frame source=reference_frame(bl,w,h),expanded=reference_frame(oracle,w,h);
    expanded.planes[0].components=3;expanded.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    pl_tex reference_planes[3]={0};
    if(filter==2){
        expanded=el.frame;expanded.num_planes=3;expanded.crop=(pl_rect2df){0,0,w,h};
        expanded.repr.bits=(struct pl_bit_encoding){.sample_depth=10,.color_depth=10};
        for(int c=0;c<3;c++){
            int sw=c?w/2:w,sh=c?h/2:h;
            float *values=calloc((size_t)sw*sh*4,sizeof(float));assert(values);
            for(int i=0;i<sw*sh;i++)values[i*4]=(float)scaled[c][i]/1023.f;
            reference_planes[c]=reference_texture(gpu,sw,sh,values);free(values);
            expanded.planes[c]=(struct pl_plane){.texture=reference_planes[c],.components=1,
                .component_mapping={c,-1,-1,-1},.shift_x=c?-.5:0,.shift_y=c && top?-.5:0};
        }
    }
    source.enhancement_layer=&el.frame;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);av_dovi_get_header(m)->disable_residual_flag=0;
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1500}};
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++){mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;mapping->nlq[c].vdr_in_max=1023*4096;}
    void *saved=malloc(bytes);assert(saved);memcpy(saved,m,bytes);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    dvbridge_renderer_set_fel_filter(r,filter);
    struct dvbridge_geometry geo={w,h,0,0,w,h};
    assert(dvbridge_render_rgb(r,&source,m,bytes,1,1,geo));reference_read(gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    source.enhancement_layer=same?&el.frame:&expanded;
    dvbridge_renderer_set_fel_filter(r,DVBRIDGE_FEL_BILINEAR);
    assert(dvbridge_render_rgb(r,&source,m,bytes,2,2,geo));reference_read(gpu,dvbridge_render_texture(r),0,0,w,h,expected);
    float maximum=0;
    int worst=0;
    for(int i=0;i<w*h*4;i++){assert(isfinite(actual[i]));if(fabsf(actual[i]-expected[i])>maximum){maximum=fabsf(actual[i]-expected[i]);worst=i;}}
    fprintf(stderr,"FEL filter=%d planar=%d top=%d flip=%d edge=%d max_error=%.9g\n",filter,planar,top,flip,edge,maximum);
    if(maximum>=3e-5f)fprintf(stderr,"worst x=%d y=%d c=%d actual=%.9g expected=%.9g\n",(worst/4)%w,worst/4/w,worst%4,actual[worst],expected[worst]);
    assert(maximum<3e-5f && !memcmp(saved,m,bytes));
    if(filter==2){
        source.enhancement_layer=&el.frame;
        el.frame.crop.x1-=2;dvbridge_renderer_set_fel_filter(r,DVBRIDGE_FEL_REFERENCE);
        assert(!dvbridge_render_rgb(r,&source,m,bytes,3,3,geo) && "Invalid Reference ratio may not silently drop FEL");
        el.frame.crop.x1+=2;
    }
    source.enhancement_layer=NULL;av_dovi_get_header(m)->disable_residual_flag=1;
    dvbridge_renderer_set_fel_filter(r,DVBRIDGE_FEL_DEFAULT);
    assert(dvbridge_render_rgb(r,&source,m,bytes,4,NAN,geo));reference_read(gpu,dvbridge_render_texture(r),0,0,w,h,expected);
    dvbridge_renderer_set_fel_filter(r,filter);
    assert(dvbridge_render_rgb(r,&source,m,bytes,5,NAN,geo));reference_read(gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    assert(!memcmp(actual,expected,sizeof(actual)));
    av_dovi_get_header(m)->disable_residual_flag=0;
    free(saved);dvbridge_renderer_destroy(r);av_free(m);dvbridge_gl_frame_release(&el);
    pl_tex_destroy(gpu,&bl);pl_tex_destroy(gpu,&oracle);
    for(int c=0;c<3;c++){pl_tex_destroy(gpu,&planes[c]);pl_tex_destroy(gpu,&reference_planes[c]);free(raw[c]);free(scaled[c]);}
}
int main(void)
{
    assert(dvbridge_renderer_set_fel_filter && "Typed FEL bilinear/reference selector missing");
    struct reference_gpu g=reference_gpu_create();
    for(int f=1;f<=2;f++)for(int planar=0;planar<2;planar++)for(int top=0;top<2;top++)for(int flip=0;flip<2;flip++)
        for(int edge=0;edge<2;edge++)qualify(&g,f,planar,top,flip,edge,false,false);
    for(int same=0;same<2;same++)for(int flip=0;flip<2;flip++)
        qualify(&g,2,false,true,flip,true,same,true);
    reference_gpu_destroy(&g);puts("PASS FEL bilinear/reference independent interpolation oracles");
}
