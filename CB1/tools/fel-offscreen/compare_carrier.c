// SPDX-License-Identifier: MIT
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static double pq(double sample)
{
    const double x=pow(fmin(fmax(sample,0),1)*.1,2610.0/16384);
    return pow((3424.0/4096+(2413.0/128)*x)/(1+(2392.0/128)*x),2523.0/32);
}
static void values(const float *rgb, double out[3])
{
    double r=pq(rgb[0]),g=pq(rgb[1]),b=pq(rgb[2]);
    double y=.2627*r+.6780*g+.0593*b;
    out[0]=y;
    out[1]=(b-y)/1.8814;
    out[2]=(r-y)/1.4746;
}
static void *read_file(const char *path, size_t bytes)
{
    FILE *file=fopen(path,"rb");assert(file);
    void *data=malloc(bytes);assert(data);
    assert(fread(data,1,bytes,file)==bytes && fgetc(file)==EOF && !fclose(file));
    return data;
}
int main(int argc,char **argv)
{
    assert(argc==7);
    const size_t width=atoi(argv[4]),height=atoi(argv[5]),n=width*height;
    const int bits=atoi(argv[6]);
    assert(width%2==0 && (bits==10 || bits==12));
    const int step=1<<(12-bits);
    uint8_t *a=read_file(argv[1],n*4),*b=read_file(argv[2],n*4);
    float *rgb=read_file(argv[3],n*4*sizeof(float));
    size_t different=0, matches_a=0,matches_b=0,matches_none=0;
    double worst_threshold=0,worst_a=0,worst_b=0;
    int worst_delta=0;
    for (size_t i=0;i<n;i++) {
        const uint8_t *p=a+4*i,*q=b+4*i;
        assert(p[3]==255 && q[3]==255);
        int x[]={16*p[1]+(p[2]&15),16*p[0]+(p[2]>>4)};
        int y[]={16*q[1]+(q[2]&15),16*q[0]+(q[2]>>4)};
        for (int c=0;c<2;c++) {
            assert(x[c]%step==0 && y[c]%step==0);
            if (x[c]==y[c]) continue;
            double exact;
            if (c==0) {
                double current[3];
                values(rgb+4*i,current);
                exact=(256+3504*current[0])/step;
            } else {
                size_t even=i&~(size_t)1,left=even%width?even-1:even;
                double l[3],m[3],r[3];
                values(rgb+4*left,l);values(rgb+4*even,m);values(rgb+4*(even+1),r);
                int lane=1+i%2;
                exact=(2048+3584*(l[lane]+2*m[lane]+r[lane])/4)/step;
            }
            int ref=(int)floor(exact+.5), aa=x[c]/step, bb=y[c]/step;
            different++;
            matches_a+=aa==ref;matches_b+=bb==ref;matches_none+=aa!=ref && bb!=ref;
            worst_threshold=fmax(worst_threshold,fabs(exact-floor(exact)-.5));
            worst_a=fmax(worst_a,fabs(exact-aa));worst_b=fmax(worst_b,fabs(exact-bb));
            if(abs(aa-bb)>worst_delta)worst_delta=abs(aa-bb);
        }
    }
    printf("changes=%zu/%zu max_step=%d half_distance=%.7f old_match=%zu new_match=%zu neither=%zu max_old_err=%.7f max_new_err=%.7f\n",
           different,2*n,worst_delta,worst_threshold,matches_a,matches_b,matches_none,worst_a,worst_b);
    free(a);free(b);free(rgb);
}
