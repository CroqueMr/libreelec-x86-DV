/* SPDX-License-Identifier: MIT */
/* Standalone validation oracle. No decoder or display device is opened. */
#include CB1_IMPORT_IMPLEMENTATION
#include <assert.h>
#include <stdio.h>
#include <unistd.h>

static uint32_t random_state=23;
static unsigned next(void)
{ random_state=random_state*1664525u+1013904223u;return random_state; }
static void result(uint64_t value)
{ assert(fwrite(&value,sizeof(value),1,stdout)==1); }

int main(void)
{
    FILE *file=tmpfile();assert(file);
    const int sizes[][2]={{1,1},{63,63},{1920,1080},{2560,1440},{3840,2160},
        {4096,2304},{0,1080},{4097,1080},{1920,2305},{INT_MAX,INT_MAX}};
    const unsigned formats[]={DRM_FORMAT_GR1616,DRM_FORMAT_RG1616,DRM_FORMAT_R16,DRM_FORMAT_R8};
    unsigned cases[16]={0};
    for(unsigned i=0;i<24000;i++){
        unsigned index=(i/16)%10;int w=sizes[index][0],h=sizes[index][1];
        AVDRMFrameDescriptor d={.nb_objects=2,.nb_layers=2};
        for(unsigned p=0;p<2;p++){
            d.objects[p]=(AVDRMObjectDescriptor){.fd=fileno(file),.size=UINT64_C(1)<<30,
                .format_modifier=(i/1280)&1?DRM_FORMAT_MOD_LINEAR:DRM_FORMAT_MOD_INVALID};
            d.layers[p]=(AVDRMLayerDescriptor){.format=p?formats[(i/160)%4]:DRM_FORMAT_R16,.nb_planes=1};
            d.layers[p].planes[0]=(AVDRMPlaneDescriptor){.object_index=p,.offset=16,.pitch=8192};
        }
        unsigned plane=(i/640)%2,mutation=i%16;
        cases[mutation]++;
        switch(mutation){
        case 0:d.nb_layers=(next()>>16)%5;break;
        case 1:d.nb_objects=(int)((next()>>16)%7)-1;break;
        case 2:d.layers[plane].nb_planes=(next()>>16)%3;break;
        case 3:d.layers[plane].planes[0].object_index=(int)((next()>>16)%6)-1;break;
        case 4:d.layers[plane].planes[0].pitch=(int)((next()>>16)%16384)-1;break;
        case 5:d.layers[plane].planes[0].pitch=(ptrdiff_t)INT_MAX+1;break;
        case 6:d.layers[plane].planes[0].offset=-1;break;
        case 7:d.layers[plane].planes[0].offset=(ptrdiff_t)INT_MAX+1;break;
        case 8:d.objects[plane].fd=-1;break;
        case 9:d.objects[plane].size=next()%20000000;break;
        case 10:d.objects[plane].format_modifier=1234;break;
        case 11:d.layers[0].format=DRM_FORMAT_RG1616;break;
        default:break;
        }
        bool accepted=dvbridge_dmabuf_validate_p010(&d,w,h);result(accepted);
        struct dvbridge_dmabuf_key key,other;
        memset(&key,0x5a,sizeof(key));
        bool keyed=dvbridge_dmabuf_make_key(&key,&d,w,h,(void*)1,(void*)2,(void*)3);
        assert(!keyed || accepted);result(keyed);
        if(accepted){
            for(int p=0;p<d.nb_objects;p++){
                struct stat st;
                bool written=!fstat(d.objects[p].fd,&st) &&
                    key.objects[p][0]==(uint64_t)st.st_dev && key.objects[p][1]==(uint64_t)st.st_ino;
                if(keyed)assert(written);
                if(written){key.objects[p][0]=d.objects[p].fd+1;key.objects[p][1]=0;}
            }
        }
        if(keyed){
            other=key;assert(dvbridge_dmabuf_key_equal(&key,&other));
            other.layers[0][3]++;assert(!dvbridge_dmabuf_key_equal(&key,&other));
        }
        assert(fwrite(&key,sizeof(key),1,stdout)==1);
    }
    for(unsigned i=0;i<16;i++)assert(cases[i]==1500);
    fclose(file);
    fprintf(stderr,"24000 descriptor decisions and normalized identity records; 16 mutations x 1500\n");
}
