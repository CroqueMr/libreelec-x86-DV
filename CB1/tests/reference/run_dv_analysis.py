"""Native fixed scalar records against independent exact-input Decimal arithmetic."""
import json,subprocess,sys,struct
from decimal import Decimal as D,localcontext,ROUND_FLOOR
from pathlib import Path
from dv_analysis_oracle import qualify, analyze

def fp32(x):return struct.unpack('>f',struct.pack('>f',x))[0]
def halfup(x):return (x*100000+D('.5')).to_integral_value(rounding=ROUND_FLOOR)/100000
def code(x):return min(4095,int((x*4096+D('.5')).to_integral_value(rounding=ROUND_FLOOR)))
data=json.loads(Path(sys.argv[2]).read_text());cases=[]
for p in data['dv_cases']:
    if 'rgb' not in p['input']:continue
    v=p['input'];cases.append((p['id'],v['rgb'],v['size'],v['active']))
for name,q,size in [('black',0,[3,3]),('constant-three',.7,[5,1]),('constant-full-small',.5,[32,32]),
                     ('near-halfup-below',.5501749,[2,2]),('near-halfup-above',.5501751,[2,2]),
                     ('wire-degenerate',.25000001,[3,3]),('peak',1,[2,2])]:
    cases.append((name,[[q]*3 for _ in range(size[0]*size[1])],size,[0,0,*size]))
for q in (.5,.7):
    for name,size,active in [('three',[6,2],[0,0,6,2]),('129',[258,2],[0,0,258,2]),
                             ('4K',[3840,2160],[0,0,3840,2160]),('odd-partial',[9,7],[1,1,8,6])]:
        cases.append((f'uniform-{q}-{name}',q,size,active))
for name,size in [('528',[48,44]),('581',[166,14])]:
    cases.append((f'uniform-0.7-{name}',.7,size,[0,0,*size]))
failed=0;round_diff=0;worst=D(0)
for name,rgb,size,active in cases:
    uniform=isinstance(rgb,float)
    if uniform:
        expected=[D.from_float(fp32(rgb))]*3;original=[D(str(rgb))]*3
        groups=((active[2]-active[0]+1)//2)*((active[3]-active[1]+1)//2)
        numbers=[*size,*active,rgb]
    else:
        actual_input=[[fp32(q) for q in p] for p in rgb]
        expected,groups=analyze(actual_input,size,active)
        original,_=analyze([[D(str(q)) for q in p] for p in rgb],size,active)
        numbers=[*size,*active,*[q for p in rgb for q in p]]
    text=' '.join(map(str,numbers))+'\n'
    result=subprocess.run([sys.argv[1]]+(['uniform'] if uniform else []),input=text,text=True,capture_output=True)
    print('CASE',name,'exit',result.returncode,flush=True);print(result.stderr,end='')
    if result.returncode==77:
        print('UNSUPPORTED required real analyzer capability; no GPU qualification',flush=True)
        sys.exit(77)
    if result.returncode:failed+=1;continue
    record=json.loads(result.stdout)['raw_record'];floats=[struct.unpack('>f',v.to_bytes(4,'big'))[0] for v in record[:3]]
    actual=[D.from_float(floats[0]),D.from_float(floats[1]/record[3]),D.from_float(floats[2])]
    assert record[3]==groups and record[4:]==[17,0,29,0,43,0,1,0]
    errors=[a-b for a,b in zip(actual,expected)];worst=max(worst,*map(abs,errors))
    passed=all(abs(e)<=D('.000001') for e in errors);failed+=not passed
    rounded=json.loads(result.stdout)['statistics']
    qualify(record,expected,original,rounded,name)
    rounded=list(map(lambda q:D(str(q)),rounded));round_diff+=rounded!=[halfup(q) for q in expected]
    if name=='black':assert actual==[D(0)]*3
    print('RECORD',record,'FP32_input_Decimal',list(map(str,expected)),'original_input_Decimal',list(map(str,original)),
          'actual_raw',list(map(str,actual)),'signed_errors',list(map(str,errors)),'pre_round_pass',passed,
          'rounded_actual',list(map(str,rounded)),'rounded_expected',list(map(str,map(halfup,expected))),
          'codes_actual',[code(q) for q in rounded],'codes_expected',[code(halfup(q)) for q in expected],flush=True)
print('SUMMARY pure_analyzer_cases',len(cases),'accuracy_failures',failed,'round_differences',round_diff,'worst_PQ_error',worst,flush=True)
sys.exit(bool(failed))
