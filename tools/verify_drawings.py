"""Check drawing source references and SVG/PDF pairs, not visual graph equivalence."""
import math
import hashlib
import json
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import adc_topology


def verify():
    cells=adc_topology.describe((ROOT/'design/adc_topology.scs').read_text(encoding='utf-8'))['cells']
    figures=sorted((ROOT/'report/figures').glob('*.tex'))
    manifest=json.loads((ROOT/'report/figures/manifest.json').read_text(encoding='utf-8'))['drawings']
    assert set(manifest)=={p.stem for p in figures}
    count=0
    for source in figures:
        for line in source.read_text(encoding='utf-8').splitlines():
            if line.startswith('% @mos '):
                _,_,cell,name,polarity,d,g,s,b,w,l=line.split()
                row=next(x for x in cells[cell]['mos'] if x['instance']==name)
                assert row['polarity']==polarity and row['nodes']==[d,g,s,b], source.name+': '+name
                assert math.isclose(row['nominal_width_m'],float(w),rel_tol=1e-12)
                assert math.isclose(row['nominal_length_m'],float(l),rel_tol=1e-12)
                count+=1
            elif line.startswith('% @instance '):
                _,_,cell,name,kind,*ports=line.split()
                row=next(x for x in cells[cell]['instances'] if x['instance']==name)
                assert row['cell']==kind and row['nodes']==ports, source.name+': '+name
                count+=1
            elif line.startswith('% @passive '):
                _,_,cell,name,kind,a,b,parameter=line.split()
                row=next(x for x in cells[cell]['passives'] if x['instance']==name)
                assert row['kind']==kind and row['nodes']==[a,b],source.name+': '+name
                left,right=row['nominal_schematic_parameters'].split('=')
                key,value=parameter.split('=')
                assert left==key and math.isclose(float(right),float(value),rel_tol=1e-12)
                count+=1
        pdf,svg=source.with_suffix('.pdf'),source.with_suffix('.svg')
        row=manifest[source.stem]
        for key,path in (('source',source),('style',ROOT/'report/circuit-style.tex'),('pdf',pdf),('svg',svg)):
            assert row[key+'_sha256']==hashlib.sha256(path.read_bytes()).hexdigest(), source.name+': '+key
        assert pdf.read_bytes().startswith(b'%PDF-'), pdf.name
        xml=ET.parse(svg).getroot()
        assert xml.get('viewBox') and xml.get('width') and xml.get('height'), svg.name
        first=list(xml)[0]
        assert first.tag.endswith('rect') and first.get('fill')=='#ffffff', svg.name
        assert first.get('width')==first.get('height')=='100%', svg.name
    assert len(figures)>=4 and count>=17
    style=(ROOT/'report/circuit-style.tex').read_text(encoding='utf-8')
    for setting in ('transistors/scale=0.8','resistors/scale=0.5','capacitors/scale=0.5',
        'sources/scale=0.8','logic ports/scale=0.6','flipflops/scale=0.6',
        'tripoles/mos style=arrows','transistors/arrow pos=end',
        'amplifiers/scale=0.7','blocks/scale=0.7'):
        assert setting in style,setting
    assert r'\usepackage[american]{circuitikz}' in (ROOT/'report/main.tex').read_text(encoding='utf-8')
    # Validate local Markdown links, including image targets. External links are not fetched.
    for doc in ROOT.rglob('*.md'):
        if any(x in {'.git','runs'} for x in doc.relative_to(ROOT).parts):continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):continue
            path=target.split('#',1)[0]
            assert (doc.parent/path).exists(), str(doc.relative_to(ROOT))+': '+target
    return {'figures':len(figures),'annotated_source_instances_checked':count,
            'scope':'Source annotations and vector pairs checked; rendered geometry requires visual review',
            'electrical_simulations_started':0}


if __name__=='__main__':
    print(verify())
