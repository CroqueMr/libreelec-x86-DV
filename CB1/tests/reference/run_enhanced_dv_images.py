# SPDX-License-Identifier: MIT
"""Frozen full FEL images, exact scalar/packet pairing and actual TV-Led packing."""
import copy
import json
import math
from pathlib import Path
import subprocess
import struct
import sys
import reference as R
from run_gpu_images import wire
from decimal import Decimal as D
from dv_analysis_oracle import analyze, fp32, qualify

def crc_division(data):
    polynomial = 0x104c11db7
    dividend = (int.from_bytes(data, 'big') << 32) ^ (0xffffffff << (8*len(data)))
    while dividend.bit_length() > 32:
        dividend ^= polynomial << (dividend.bit_length()-33)
    return dividend

def runtime_packet(pair, actual=None):
    frozen = bytes.fromhex(pair['wire']['packet_hex'])
    assert crc_division(frozen[:124]) == int.from_bytes(frozen[124:], 'big')
    payload = bytearray.fromhex(pair['wire']['payload_hex'])
    # Controller-approved embedding of the unchanged picture in real 4K.
    # Neither actual output nor the serializer supplies these expectations.
    assert len(payload) == 95 and payload[86] == 5
    w,h=pair['input']['size']
    l,t,r,b=pair['input']['active']
    payload[87:] = b''.join(x.to_bytes(2,'big') for x in (l,3840-r,t,2160-b))
    if actual is not None:
        # Independently convert the retained 48-byte record, not serialized
        # output fields. Preserve mandated CPU binary64 sum/count arithmetic.
        record=actual['raw_record']
        assert len(record)==12 and record[3]==pair['expected']['groups']
        raw=[struct.unpack('f',struct.pack('I',v))[0] for v in record[:3]]
        scalar=[raw[0],raw[1]/record[3],raw[2]]
        if raw[0]==raw[2] or scalar[1]<raw[0]:scalar[1]=raw[0]
        elif scalar[1]>raw[2]:scalar[1]=raw[2]
        rounded=[math.floor(q*100000+.5)/100000 for q in scalar]
        assert actual['statistics']==rounded
        codes=[min(4095,math.floor(rounded[i]*4096+.5)) for i in (0,2,1)]
        assert actual['l1']==codes
        assert payload[75]==1
        payload[76:82]=b''.join(x.to_bytes(2,'big') for x in codes)
    packet = bytearray(frozen[:5]) + payload + bytearray(24)
    assert len(packet) == 124
    return bytes(packet) + crc_division(packet).to_bytes(4,'big')

def check_transport(pair, actual, expected_packet):
    rgb = pair['expected']['rgb']
    w,h=pair['input']['size']
    assert len(actual['packed']) == w*h
    for i, pixel in enumerate(actual['packed']):
        x, y = i % w, i // w
        a, b = rgb[w*y+(x&~1)], rgb[w*y+(x&~1)+1]
        ya = sum(c*v for c,v in zip((.2627,.6780,.0593),a))
        yb = sum(c*v for c,v in zip((.2627,.6780,.0593),b))
        luma = math.floor(256+3504*(ya if not x&1 else yb)+.5)
        chroma = (2048+3584*((a[2]-ya)+(b[2]-yb))/(2*1.8814) if not x&1 else
                  2048+3584*((a[0]-ya)+(b[0]-yb))/(2*1.4746))
        wanted = math.floor(chroma+.5)
        index = y*3840+x
        if index < 3072:
            bit = index % 1024
            value = (expected_packet[bit//8] >> (7-bit%8)) & 1
            wanted = (wanted&4094) | (value ^ (((wanted>>1).bit_count()+luma.bit_count())&1))
        c = (pixel[0]<<4) | (pixel[2]>>4)
        code = (pixel[1]<<4) | (pixel[2]&15)
        assert pixel[3] == 255 and abs(code-luma) <= 1 and abs((c>>1)-(wanted>>1)) <= 1
        if index < 3072:
            value = (expected_packet[(index%1024)//8] >> (7-index%8)) & 1
            assert ((c&1) ^ (((c>>1).bit_count()+code.bit_count())&1)) == value

def main():
    data = json.loads((Path(__file__).parent/'vectors.json').read_text())
    pairs = [p for p in data['dv_cases'] if 'image_input' in p['input']]
    assert len(pairs) == 48
    additional=json.loads((Path(__file__).parent/'dv-conformant-scaled-vectors.json').read_text())['dv_cases']
    assert len(additional)==12 and all(p['expected']['groups']==6 and p['input']['size']==[4,6] for p in additional)
    pairs+=additional
    geometry_only=len(sys.argv)>2 and sys.argv[2]=='geometry-only'
    original_pairs=pairs
    if geometry_only:pairs=[]
    failed = 0;valid = 0;negative = 0
    for pair in pairs:
        image = copy.deepcopy(pair)
        image['input'] = pair['input']['image_input']
        image['input'].update(bits=10, limited=True)
        ineligible=pair['id'].startswith('dv-pair-output-scaled-')
        arguments=[sys.argv[1],image['input']['preset']]+(['negative-geometry'] if ineligible else [])
        result = subprocess.run(arguments, input=wire(image),capture_output=True,text=True)
        print(pair['id'],'exit',result.returncode,flush=True)
        print(result.stderr,end='')
        if result.returncode == 77:
            print('UNSUPPORTED real required capability: all paired GPU images remain unexecuted',flush=True)
            return 77
        if result.returncode:
            failed += 1
            continue
        actual = json.loads(result.stdout)
        if ineligible:
            assert actual == {'negative_geometry':True}
            negative+=1;print('PASS original immutable scaled pair rejected by retained DV geometry guard, no successful DV image claim',flush=True)
            continue
        valid+=1
        print('ACTUAL',pair['id'],json.dumps(actual),flush=True)
        try:
            # This code projection checks image-budget rounding movement only.
            # Actual final 12-bit YCbCr transport is checked separately below.
            image['expected'] = dict(rgb=pair['expected']['rgb'], codes=[
                [math.floor(64+876*x+.5) for x in p] for p in pair['expected']['rgb']])
            R.check_image_integrity(image,dict(rgb=actual['rgb'],codes=[
                [math.floor(64+876*x+.5) for x in p] for p in actual['rgb']]))
            assert actual['source_pq'] == pair['expected']['source_pq']
            assert actual['source_cm_version'] == (40 if pair['generation']=='CM4' else 29)
            w,h=pair['input']['size']
            assert actual['margins'] == [0,3840-w,0,2160-h]
            expected_packet = runtime_packet(pair,actual)
            assert actual['packet_hex'] == expected_packet.hex()
            check_transport(pair,actual,expected_packet)
            print('PASS literal raw-record-derived exact L1/header/L5/CRC packet and actual final transport',flush=True)
            print('FROZEN-L1-PACKET',pair['id'],'L1_exact_match',actual['l1']==pair['expected']['l1'],
                  'packet_exact_match',actual['packet_hex']==runtime_packet(pair).hex(),flush=True)
            assert actual['l1'] == pair['expected']['l1']
            assert actual['packet_hex'] == runtime_packet(pair).hex()
            expected,groups=analyze([[D.from_float(fp32(q)) for q in pixel] for pixel in actual['rgb']],
                                    [w,h],[0,0,w,h])
            ideal,_=analyze([[D(str(q)) for q in pixel] for pixel in pair['expected']['rgb']],
                            [w,h],[0,0,w,h])
            assert groups==actual['raw_record'][3]
            qualify(actual['raw_record'],expected,ideal,actual['statistics'],pair['id'])
        except AssertionError as error:
            print('FAIL unchanged paired image/statistic/packet budget:',error,'actual=',json.dumps(actual),flush=True)
            failed += 1
        else:
            print('PASS unchanged frozen image/L1/packet, exact represented-input analyzer and runtime L5/CRC/transport',flush=True)
    seed=next(p for p in original_pairs if p['id']=='dv-pair-output-0-BT2020-0-1')
    for side,active in enumerate(([1,0,2,2],[0,0,1,2],[0,1,2,2],[0,0,2,1])):
        control=copy.deepcopy(seed);raw=control['input']['image_input']
        raw.update(size=[4,4],output_size=[2,2],rgb=[[.5]*3 for _ in range(16)],el=[[512]*3 for _ in range(16)])
        words=wire(dict(input={**raw,'bits':10,'limited':True})).split()
        words[19+side]='1' # Source L5 one pixel maps to a half destination pixel.
        result=subprocess.run([sys.argv[1],raw['preset']],input=' '.join(words)+'\n',capture_output=True,text=True)
        print('HALF-SIDE',side,'source_margin=1 scaled_margin=0.5 exit',result.returncode,flush=True)
        print(result.stderr,end='')
        assert result.returncode==0
        actual=json.loads(result.stdout);print('HALF-SIDE-ACTUAL',side,json.dumps(actual),flush=True)
        l,t,r,b=active
        assert actual['margins']==[l,3840-r,t,2160-b] and actual['raw_record'][3]==1
        assert all(pixel==[0,0,0] for i,pixel in enumerate(actual['rgb']) if not(l<=i%2<r and t<=i//2<b))
        control['input'].update(size=[2,2],active=active);control['expected'].update(groups=1,rgb=actual['rgb'])
        packet=runtime_packet(control,actual)
        assert actual['packet_hex']==packet.hex();check_transport(control,actual,packet)
        print('PASS independent half-side integer L5/count, complete 4K complement, raw-record packet/CRC/actual transport',flush=True)
    assert (valid==0 and negative==0) if geometry_only else (valid==48 and negative==12)
    print('Enhanced DV eligible GPU pairs: 36 original + 12 conformant; original ineligible negative checks',negative,'failures',failed,flush=True)
    return bool(failed)

if __name__ == '__main__':
    sys.exit(main())
