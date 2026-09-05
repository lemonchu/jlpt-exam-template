#!/usr/bin/env python3
"""Check fresh input snapshots, scene glyphs, PDF text positions, and font roles."""
from pathlib import Path
from collections import Counter
import hashlib,json,sys
import fitz,yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from calibrated_renderer import Resolver,supplied_slots
from font_overrides import install_overrides,font_role

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def questions(obj):
    if isinstance(obj,dict):
        yield from ([obj] if 'options' in obj and not obj.get('is_example') else [])
        for key,value in obj.items():
            if key!='options':yield from questions(value)
    elif isinstance(obj,list):
        for value in obj:yield from questions(value)

def verify(name):
    out=ROOT/'output'/name;build=read(out/'build-report.json');render=read(out/'render-report.json')
    scene=read(out/'scene.json');bindings=read(out/'resolved.json');pdf=out/'main.pdf'
    assert pdf.read_bytes().rstrip().endswith(b'%%EOF'),f'{name}: incomplete PDF'
    doc=fitz.open(pdf);assert not doc.is_repaired and len(doc)==build['page_count']==render['pages']
    for key,digest in build['inputs'].items():assert sha(out/'inputs'/key)==digest,f'{name}: input snapshot changed: {key}'
    for path in (out/'inputs').glob('*.yaml'):
        if path.name in ('V.yaml','G.yaml','R.yaml','L.yaml'):
            assert sha(ROOT/'content'/build['paper']/path.name)==sha(path),f'{name}: current YAML differs; rebuild'
    resolver=Resolver(ROOT/'profiles/n1-original')
    policy=install_overrides(resolver,render.get('font_policy',{}).get('config'),ROOT)
    assert policy['config_sha256']==render.get('font_policy',{}).get('config_sha256'),f'{name}: font configuration changed; rebuild'
    assert [(f['id'],f['sha256']) for f in policy['registered_fonts']]==[(f['id'],f['sha256']) for f in render['font_policy']['registered_fonts']],f'{name}: full font files changed; rebuild'
    max_error=0;total=0;missing=[];fallback=Counter();cross_role=[]
    for index,page in enumerate(scene['sections']['booklet']['pages']):
        expected=[]
        for command in page['commands']:
            if command['type']!='run':continue
            for slot,(text,form) in enumerate(supplied_slots(bindings['runs'][command['run_id']],command)):
                target,code=resolver.resolve(command['font'],text,form)
                if target is None:continue
                accepted={code}
                if len(text)==1:accepted.add(ord(text))
                x=command['x']+command['offsets'][slot]*command['sx']/command['sy']
                expected.append((accepted,x,842-command['y'],text))
                record=resolver.fonts[target].record
                if record.get('family')=='fallback':
                    fallback[(target,text)]+=1
                    missing.append({'page':index+1,'text':text,'font':target,'font_name':record.get('name'),'source_face':record.get('source_face'),'user_supplied':record.get('user_supplied',False),'bundled_sample':record.get('bundled_sample',False),'preferred':command['font'],'x':round(x,4),'baseline':round(842-command['y'],4)})
                    original_role=font_role(resolver.fonts[command['font']].record)
                    if original_role!=font_role(record):cross_role.append((original_role,font_role(record),text))
        actual=[char for span in doc[index].get_texttrace() for char in span['chars']]
        assert len(expected)==len(actual),f'{name} page {index+1}: glyph count {len(expected)} != {len(actual)}'
        for i,(want,got) in enumerate(zip(expected,actual)):
            assert got[0] in want[0],f'{name} page {index+1} glyph {i}: Unicode {got[0]} != {want}'
            delta=max(abs(want[1]-got[2][0]),abs(want[2]-got[2][1]));max_error=max(max_error,delta)
        total+=len(expected)
    assert max_error<.001,f'{name}: glyph coordinate mismatch {max_error}'
    assert total==render['drawn_glyphs'] and not cross_role
    assert not render['unbound_required_runs'] and not render['layout_text_fallback']
    selected=yaml.safe_load((out/'selected-content.yaml').read_text());qs=list(questions(selected))
    assert all(len(q['options'])==4 for q in qs)
    top=ROOT/'output'/f'N1-{name}.pdf';assert sha(top)==sha(pdf)
    complete=[m for m in missing if m['user_supplied']]
    samples=[m for m in missing if m['bundled_sample']]
    substitutes=[m for m in missing if not m['user_supplied'] and not m['bundled_sample']]
    return {'status':'PASS','pages':len(doc),'drawn_glyphs':total,'formal_printed_choice_items':len(qs),'max_coordinate_error_bp':max_error,'sha256':sha(pdf),'input_snapshots_current':True,'ordered_scene_glyphs_match_pdf':True,'cross_family_or_weight_fallbacks':len(cross_role)}, {'occurrences':len(missing),'unique_characters':len({m['text'] for m in missing}),'characters':''.join(sorted({m['text'] for m in missing})),'complete_font_occurrences':len(complete),'bundled_sample_occurrences':len(samples),'substitute_font_occurrences':len(substitutes),'substitute_characters':''.join(sorted({m['text'] for m in substitutes})),'details':missing}

def main():
    names=sys.argv[1:] or ['paper-a-written','paper-a-listening','paper-b-written','paper-b-listening']
    results={};fonts={}
    for name in names:results[name],fonts[name]=verify(name)
    dest=ROOT/'validation';dest.mkdir(exist_ok=True)
    (dest/'build-integrity.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    (dest/'font-coverage.json').write_text(json.dumps(fonts,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
