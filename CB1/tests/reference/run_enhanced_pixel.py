# SPDX-License-Identifier: GPL-3.0-only
"""Independent binary64 trim-guided expansion comparison, linear BT.2020."""
import json
import math
import subprocess
import sys
from functools import lru_cache
import cm4_reference as cm4
import creative_reference as cm29

P3=[[.68,.32],[.265,.69],[.15,.06],[.3127,.3290]]
BT=cm4.decode_controls({},1000,cm4.BT2020)
LMS=BT['rgb_to_lms']
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def interpolate(values,x):
    x=max(0,min(1,x))*(len(values)-1);i=min(len(values)-2,int(x))
    return values[i]+(values[i+1]-values[i])*(x-i)
def pq(v):
    v=(max(v,0)/10000)**(2610/16384)
    return ((3424/4096+2413/128*v)/(1+2392/128*v))**(2523/32)
def nits(q):
    v=q**(32/2523)
    return 10000*(max(v-3424/4096,0)/(2413/128-2392/128*v))**(16384/2610)
def smooth(a,b,v):
    x=max(0,min(1,(v-a)/(b-a)))
    return x*x*(3-2*x)
@lru_cache(None)
def parameters(m,t,preset,family,gamut,control,anchors):
    u=[k/256 for k in range(257)];x=[(10+(m-10)*v)/m for v in u]
    retention=[1. if family==0 and anchors==0 else 0.]*257;color=[0.]*67
    for a in range(anchors):
        weight=1 if anchors==1 else [.35,.65][a]
        raw=dict(primary=[2048]*6,mid_contrast=2048,clip_trim=2048,
                 saturation=[128]*6,hue=[128]*6)
        if control==1:
            raw['primary'][0]=raw['primary'][2]=2304
            raw.update(mid_contrast=2400,clip_trim=1800)
        if control==2:
            raw['primary'][3:5]=[3000,2700]
            raw['saturation'][a]=220;raw['hue'][4-a]=200
        if family==2:raw={'primary':raw['primary']}
        peak=nits([2851,3388][a]/4095)
        c=cm4.decode_controls(raw,peak,P3 if gamut else cm4.BT2020)
        secondary=[]
        for k in range(65):
            hue=-math.pi+2*math.pi*k/64
            weights=[math.exp(4*(math.cos(hue-v)-1)) for v in c['hue_centres']]
            magnitude=[abs(math.log2(g))+abs(r)/(math.pi/12) for g,r in zip(c['secondary_gain'],c['secondary_rotation'])]
            secondary.append(dot(weights,magnitude)/sum(weights))
        secondary[-1]=secondary[0]
        response=[abs(math.log2(c['chroma_base'])),abs(math.log2(c['saturation_gain'])),*secondary]
        color=[v+weight*r for v,r in zip(color,response)]
        c.update(chroma_base=1,saturation_gain=1,secondary_gain=[1]*6,secondary_rotation=[0]*6,detail_mix=0)
        if family==8:
            values=[cm4.trim_rgb([float(v*peak)]*3,c)[0]/peak for v in x]
        else:
            values=[cm29.trim_rgb([float(v*peak)]*3,peak,raw['primary'][:3]+[2048]*2)[0]/peak for v in x]
        retention=[v+weight*max(.5,min(1.15,r/z)) for v,r,z in zip(retention,values,x)]
    high,mid=nits(3080/4095),nits(1463/4095)
    amount=smooth(100,400,high)*(1-.5*smooth(.04,.30,mid/high))
    legacy_signature=bool(preset or family)
    scene_signature=bool(preset and family)
    shape=[0.];exponent=2 if legacy_signature else 3
    if scene_signature:exponent+=2*smooth(.04,.30,mid/high)
    for k in range(1,257):shape.append(shape[-1]+(u[k]**exponent-u[k-1]**exponent)*(retention[k-1]+retention[k])/2)
    extra=[amount*max(t-m,0)*v/max(1,shape[-1]) for v in shape]
    reference=min(m,max(100,high))
    if scene_signature and t>reference:
        normalization=max(1e-9,interpolate(shape,(reference-10)/(m-10)))
        extra=[smooth(100,400,high)*(t-reference)*min(1,v/normalization) for v in shape]
    if legacy_signature:extra=[v+(1-smooth(m,1.5*m,t))*amount*.12*(m-10)*16*z*z*(1-z)*(1-z)*r for v,z,r in zip(extra,u,retention)]
    return extra,color

def expected(row):
    m,t=row['master'],row['target'];rgb=row['input']
    if row['preset']==0 and not row['family'] and t<=m:return rgb
    extra,color=parameters(m,t,*(row[k] for k in ('preset','family','gamut','control','anchors')))
    y=dot(rgb,BT['luma'])
    if y<=10:return rgb
    addition=interpolate(extra,(y-10)/(m-10))
    if any(color) and not all(v==rgb[0] for v in rgb):
        cone=[pq(dot(line,rgb)) for line in LMS]
        ipt=[dot(line,cone) for line in cm4.IPT]
        gate=smooth(0,.15,math.hypot(*ipt[1:])/ipt[0])
        z=max(0,min(1,ipt[0]/pq(m)))
        hue=math.atan2(ipt[2],ipt[1])
        severity=color[0]*abs(2*z-1)+color[1]+interpolate(color[2:],(hue+math.pi)/(2*math.pi))
        addition*=max(.65,1/(1+.5*gate*severity))
    ceiling=t if row['preset'] and row['family'] else max(m,t)
    delta=addition/y;head=max(0,ceiling/max(rgb)-1);knee=.9*head;width=.1*head
    if delta>knee:
        tail=delta-knee;delta=knee+(width*tail/(width+tail) if width+tail else 0)
    return [v*(1+delta) for v in rgb]

if __name__=='__main__':
    rows=json.loads(subprocess.run([sys.argv[1],'--json'],capture_output=True,text=True,check=True).stdout)
    maximum=0
    for row in rows:
        want=expected(row);error=max(abs(pq(got)-pq(ref)) for got,ref in zip(row['output'],want))*4096
        maximum=max(maximum,error)
        assert error<=1,(row,want,error)
        assert all(math.isfinite(v) for v in row['output']) and max(row['output'])<=max(row['master'],row['target'])+1e-6
    assert len(rows)==(56 if '--ai' in sys.argv else 1008),len(rows)
    print(f'PASS {len(rows)} independent expansion samples; maximum error {maximum:.6g} logical 12-bit codes')
