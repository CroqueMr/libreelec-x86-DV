"""Independent exact represented-pixel analysis and unchanged error-bin gates."""
from decimal import Decimal as D, localcontext, ROUND_FLOOR
import math
import struct

ERROR = D('.000001')

def fp32(value):
    return struct.unpack('>f', struct.pack('>f', value))[0]

def halfup(value):
    return (value*100000+D('.5')).to_integral_value(rounding=ROUND_FLOOR)/100000

def code(value):
    return min(4095, int((value*4096+D('.5')).to_integral_value(rounding=ROUND_FLOOR)))

def permitted_bins(value):
    return halfup(max(D(0), value-ERROR)), halfup(min(D(1), value+ERROR))

def analyze(rgb, size, active):
    # Retained independent Decimal ST2084 equations, not renderer arithmetic.
    with localcontext() as c:
        c.prec=100;m1=D(2610)/16384;m2=D(2523)/32;c1=D(3424)/4096;c2=D(2413)/128;c3=D(2392)/128
        def decode(q):
            q=D(q)
            if not q:return D(0)
            t=c.power(q,1/m2)
            return c.power(max(t-c1,D(0))/(c2-c3*t),1/m1)
        def encode(v):
            if not v:return D(0)
            t=c.power(v,m1)
            return c.power((c1+c2*t)/(1+c3*t),m2)
        w,h=size;l,t,r,b=active;samples=[]
        for y in range(t,b,2):
            for x in range(l,r,2):
                group=[rgb[yy*w+xx] for yy in range(y,min(y+2,b)) for xx in range(x,min(x+2,r))]
                samples.append(encode(max(sum(decode(p[k]) for p in group)/len(group) for k in range(3))))
        return [min(samples),sum(samples)/len(samples),max(samples)],len(samples)

def record_values(record):
    raw=[struct.unpack('>f', v.to_bytes(4,'big'))[0] for v in record[:3]]
    cpu_mean=raw[1]/record[3]
    delivered=[D.from_float(raw[0]),D.from_float(cpu_mean),D.from_float(raw[2])]
    if raw[0]==raw[2] or cpu_mean<raw[0]:
        selected_mean=raw[0]
    elif cpu_mean>raw[2]:
        selected_mean=raw[2]
    else:
        selected_mean=cpu_mean
    selected=[raw[0],selected_mean,raw[2]]
    with localcontext() as c:
        c.prec=100
        exact_division=D.from_float(raw[1])/record[3]
    rounded=[math.floor(q*100000+.5)/100000 for q in selected]
    return delivered, selected, rounded, exact_division

def qualify(record, expected, ideal, rounded, name):
    raw,selected,wanted,exact_division=record_values(record)
    assert rounded==wanted, ('exact fixed-record CPU half-up',name,rounded,wanted)
    errors=[a-b for a,b in zip(raw,expected)]
    assert all(abs(e)<=ERROR for e in errors), ('raw actual-input budget',name,errors)
    assert all(abs(D.from_float(q)-e)<=ERROR for q,e in zip(selected,expected))
    bins=[permitted_bins(q) for q in expected]
    for q,e,(low,high) in zip(rounded,expected,bins):
        observed=D(str(q))
        assert low<=observed<=high, ('permitted unchanged-error bins',name,observed,low,high)
        if low==high:assert observed==halfup(e), ('stable exact rounded bin',name)
        if code(low)==code(high):assert code(observed)==code(halfup(e)), ('stable exact code',name)
    print('QUALIFICATION',name,'raw_record',record,'A_I',list(map(str,ideal)),
          'A_P_exact_binary32',list(map(str,expected)),'G_raw_CPU',list(map(str,raw)),
          'exact_sum_division',str(exact_division),'selected',selected,
          'G_minus_A_P',list(map(str,errors)),
          'A_P_minus_A_I',list(map(str,(a-b for a,b in zip(expected,ideal)))),
          'G_minus_A_I',list(map(str,(a-b for a,b in zip(raw,ideal)))),
          'rounded_I',list(map(str,map(halfup,ideal))),'rounded_P',list(map(str,map(halfup,expected))),
          'rounded_G',rounded,'permitted_bins',[[str(a),str(b)] for a,b in bins],
          'codes_I',[code(halfup(q)) for q in ideal],'codes_P',[code(halfup(q)) for q in expected],
          'codes_G',[code(D(str(q))) for q in rounded],flush=True)
    return errors
