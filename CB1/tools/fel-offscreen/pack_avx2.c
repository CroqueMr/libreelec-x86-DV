// SPDX-License-Identifier: MIT
#include <assert.h>
#include <immintrin.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
enum { W=3840,H=2160,LUT=1024*61, CHUNK=128 };
// Each entry stores the 22-bit PQ value and a 10-bit delta to the next sample.
static uint32_t words[LUT];
static float *src;
static uint32_t *dst;
static unsigned threads, bits;
static inline __m256 pq(__m256 x)
{
    // Index 10 mantissa bits per float exponent; interpolate over the other 13.
    const __m256i base=_mm256_set1_epi32(67u<<23);
    x=_mm256_mul_ps(_mm256_max_ps(_mm256_min_ps(_mm256_set1_ps(1),x),_mm256_setzero_ps()),_mm256_set1_ps(.1f));
    __m256i u=_mm256_sub_epi32(_mm256_max_epu32(_mm256_castps_si256(x),base),base);
    __m256i idx=_mm256_srli_epi32(u,13);
    __m256i entry=_mm256_i32gather_epi32((const int*)words,idx,4);
    __m256 l=_mm256_cvtepi32_ps(_mm256_and_si256(entry,_mm256_set1_epi32((1<<22)-1)));
    __m256 delta=_mm256_cvtepi32_ps(_mm256_srli_epi32(entry,22));
    __m256 f=_mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_and_si256(u,_mm256_set1_epi32(8191))),_mm256_set1_ps(1.0f/8192));
    __m256 v=_mm256_mul_ps(_mm256_fmadd_ps(f,delta,l),_mm256_set1_ps(1.0f/4194304));
    return _mm256_blendv_ps(v,_mm256_set1_ps(7.309559e-7f),
        _mm256_cmp_ps(x,_mm256_setzero_ps(),_CMP_EQ_OQ));
}
static inline __m256 range(__m256 x,float low,float high)
{
    return _mm256_min_ps(_mm256_max_ps(x,_mm256_set1_ps(low)),_mm256_set1_ps(high));
}
static inline __m256 weighted(const float *p)
{
    __m256 a=_mm256_loadu_ps(p-1),b=_mm256_loadu_ps(p),c=_mm256_loadu_ps(p+1);
    __m256 value=_mm256_mul_ps(_mm256_add_ps(_mm256_add_ps(a,_mm256_add_ps(b,b)),c),_mm256_set1_ps(.25f));
    return _mm256_permutevar8x32_ps(value,_mm256_setr_epi32(0,0,2,2,4,4,6,6));
}
static inline __m256 luminance(__m256 r,__m256 g,__m256 b)
{
    return _mm256_fmadd_ps(r,_mm256_set1_ps(.2627f),
           _mm256_fmadd_ps(g,_mm256_set1_ps(.6780f),_mm256_mul_ps(b,_mm256_set1_ps(.0593f))));
}
static void *process(void *priv)
{
    unsigned thread=(uintptr_t)priv;
    unsigned padding=12-bits;
    const __m128i pad=_mm_cvtsi32_si128(padding);
    const __m256 scale=_mm256_set1_ps(1.0f/(1u<<padding));
    const __m256 half=_mm256_set1_ps(.5f);
    float rline[CHUNK+2],gline[CHUNK+2],bline[CHUNK+2];
    enum { ROW_BATCH=16 };
    for(unsigned begin=thread*ROW_BATCH;begin<H;begin+=threads*ROW_BATCH)
    for(unsigned y=begin;y<H && y<begin+ROW_BATCH;y++){
        const float *row=src+4*(size_t)y*W;
        const __m256i mask=_mm256_setr_epi32(0x7fffffff,0x7fffffff,0x7fffffff,0,
                                            0x7fffffff,0x7fffffff,0x7fffffff,0);
        int probe=0;
        for(;probe<W;probe+=2){
            __m256i value=_mm256_loadu_si256((const __m256i *)(row+probe*4));
            if(!_mm256_testz_si256(value,mask))break;
        }
        if(probe==W){
            __m256i black=_mm256_set1_epi32(0xff001080);
            for(int x=0;x<W;x+=8)_mm256_stream_si256((void *)(dst+(size_t)y*W+x),black);
            continue;
        }
        for(int x=0;x<W;x+=CHUNK){
            for(int k=0;k<CHUNK;k+=8){
                const float *p=row+4*(x+k);
                __m128 a=_mm_loadu_ps(p+0),b0=_mm_loadu_ps(p+4),c=_mm_loadu_ps(p+8),d=_mm_loadu_ps(p+12);
                __m128 e=_mm_loadu_ps(p+16),f=_mm_loadu_ps(p+20),g0=_mm_loadu_ps(p+24),h=_mm_loadu_ps(p+28);
                _MM_TRANSPOSE4_PS(a,b0,c,d);
                _MM_TRANSPOSE4_PS(e,f,g0,h);
                __m256 r=_mm256_set_m128(e,a),g=_mm256_set_m128(f,b0),b=_mm256_set_m128(g0,c);
                const int grey=_mm256_movemask_ps(_mm256_and_ps(_mm256_cmp_ps(r,g,_CMP_EQ_OQ),_mm256_cmp_ps(r,b,_CMP_EQ_OQ)));
                r=pq(r);
                if(grey==255){g=r;b=r;}else{g=pq(g);b=pq(b);}
                _mm256_storeu_ps(rline+1+k,r);_mm256_storeu_ps(gline+1+k,g);_mm256_storeu_ps(bline+1+k,b);
            }
            if(!x){rline[0]=rline[1];gline[0]=gline[1];bline[0]=bline[1];}
            // Each chroma pair is cosited at its even pixel; the rightmost halo is unused.
            rline[CHUNK+1]=rline[CHUNK];gline[CHUNK+1]=gline[CHUNK];bline[CHUNK+1]=bline[CHUNK];
            for(int k=0;k<CHUNK;k+=8){
                __m256 r=_mm256_loadu_ps(rline+1+k),g=_mm256_loadu_ps(gline+1+k),b=_mm256_loadu_ps(bline+1+k);
                __m256 yv=_mm256_fmadd_ps(range(luminance(r,g,b),0,1),_mm256_set1_ps(3504),_mm256_set1_ps(256));
                __m256 rw=weighted(rline+1+k),gw=weighted(gline+1+k),bw=weighted(bline+1+k);
                __m256 lw=luminance(rw,gw,bw);
                __m256 cb=_mm256_mul_ps(_mm256_sub_ps(bw,lw),_mm256_set1_ps(1.0f/1.8814f));
                __m256 cr=_mm256_mul_ps(_mm256_sub_ps(rw,lw),_mm256_set1_ps(1.0f/1.4746f));
                __m256 cv=_mm256_fmadd_ps(range(_mm256_blend_ps(cb,cr,0xaa),-.5,.5),_mm256_set1_ps(3584),_mm256_set1_ps(2048));
                __m256i Y=_mm256_sll_epi32(_mm256_cvttps_epi32(_mm256_fmadd_ps(yv,scale,half)),pad);
                __m256i C=_mm256_sll_epi32(_mm256_cvttps_epi32(_mm256_fmadd_ps(cv,scale,half)),pad);
                __m256i cy=_mm256_or_si256(_mm256_srli_epi32(C,4),_mm256_slli_epi32(_mm256_srli_epi32(Y,4),8));
                cy=_mm256_or_si256(cy,_mm256_slli_epi32(_mm256_and_si256(C,_mm256_set1_epi32(15)),20));
                cy=_mm256_or_si256(cy,_mm256_slli_epi32(_mm256_and_si256(Y,_mm256_set1_epi32(15)),16));
                _mm256_stream_si256((void*)(dst+(size_t)y*W+x+k),_mm256_or_si256(cy,_mm256_set1_epi32(0xff000000)));
            }
            rline[0]=rline[CHUNK];gline[0]=gline[CHUNK];bline[0]=bline[CHUNK];
        }
    }
    return NULL;
}
static pthread_t ids[4];
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t wake=PTHREAD_COND_INITIALIZER;
static unsigned generation,running;
static int closing;
static void *worker(void *priv)
{
    unsigned seen=0;
    pthread_mutex_lock(&lock);
    for(;;){
        while(!closing && generation==seen)pthread_cond_wait(&wake,&lock);
        if(closing)break;
        seen=generation;
        pthread_mutex_unlock(&lock);
        process(priv);
        _mm_sfence(); // Publish the non-temporal writes before marking the job done.
        pthread_mutex_lock(&lock);
        if(!--running)pthread_cond_broadcast(&wake);
    }
    pthread_mutex_unlock(&lock);
    return NULL;
}
void cb1_cpu_init(unsigned n,unsigned depth)
{
    assert(n && n<=4 && (depth==10 || depth==12));
    threads=n;bits=depth;
    uint32_t last=0;
    for(unsigned i=0;i<=LUT;i++){
        uint32_t u=(67u<<23)+(i<<13);float f;memcpy(&f,&u,4);
        double v=pow(fmin(1,f),.1593017578125);
        unsigned value=fmin((1u<<22)-1,lround(pow((.8359375+18.8515625*v)/(1+18.6875*v),78.84375)*(1u<<22)));
        if(i){
            assert(value>=last && value-last<1024);
            words[i-1]=last|((value-last)<<22);
        }
        last=value;
    }
    for(unsigned i=0;i<n;i++)assert(!pthread_create(&ids[i],NULL,worker,(void*)(uintptr_t)i));
}
void cb1_cpu_start(float *input,uint32_t *output)
{
    pthread_mutex_lock(&lock);
    assert(!running);
    src=input;dst=output;running=threads;generation++;
    pthread_cond_broadcast(&wake);
    pthread_mutex_unlock(&lock);
}
int cb1_cpu_ready(int wait)
{
    pthread_mutex_lock(&lock);
    while(running && wait)pthread_cond_wait(&wake,&lock);
    int done=!running;
    pthread_mutex_unlock(&lock);
    return done;
}
void cb1_cpu_destroy(void)
{
    pthread_mutex_lock(&lock);
    assert(!running);
    closing=1;
    pthread_cond_broadcast(&wake);
    pthread_mutex_unlock(&lock);
    for(unsigned i=0;i<threads;i++)assert(!pthread_join(ids[i],NULL));
}
