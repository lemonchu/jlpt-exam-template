"""Resolve a calibrated layout from the current semantic YAML content only."""
from pathlib import Path
import json,re,unicodedata
import yaml
from inline import parse

class CalibrationMismatch(ValueError):pass

def shape(text):
    atoms=parse(str(text));base=''.join(a.text for a in atoms);ruby=[];styles=[];offset=0
    for a in atoms:
        n=sum(not c.isspace() for c in a.text)
        if a.ruby:ruby.append([offset,n,len(''.join(c for c in a.ruby if not c.isspace()))])
        if a.underline or a.bold:styles.append([offset,n,a.underline,a.bold])
        offset+=n
    result={'base_count':offset,'ruby':ruby,'styles':styles,'whitespace':[[m.start(),m.group()] for m in re.finditer(r'\s+',base)],'vector_marks':[[i,c] for i,c in enumerate(base) if c in '〔〕―-']}
    if any(a.annotation for a in atoms):result['annotations']=[a.annotation for a in atoms]
    return result

def skeleton(v):
    keys={'groups','items','questions','stimulus','blocks','options','rows','title','instruction','prompt','text','label','asset','type','kind','is_example'}
    if isinstance(v,dict):return {k:(c if k in ('type','kind','is_example') else skeleton(c)) for k,c in v.items() if k in keys}
    if isinstance(v,list):return [skeleton(c) for c in v]
    return type(v).__name__

def pointer(data,path):
    value=data
    for segment in path.strip('/').split('/'):
        segment=segment.replace('~1','/').replace('~0','~')
        value=value[int(segment)] if isinstance(value,list) else value[segment]
    return value

def field_value(f,data):
    gen=f.get('generator')
    if gen:
        if gen['kind']=='option_number':return str(gen['index'])
        if gen['kind']=='memo_label':return '－メモ－'
        if gen['kind']=='number':return str(pointer(data,f['pointer']))+gen['suffix']
        raise ValueError('Unknown field generator '+str(gen['kind']))
    return str(pointer(data,f['pointer']))

def chars_for(value,role):
    return [c for a in parse(value) for c in (a.ruby if role=='ruby' else a.text) if not c.isspace()]

def normal(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if not c.isspace())

def resolve(content_dir,binding_file,sections):
    content_dir=Path(content_dir);bindings=json.loads(Path(binding_file).read_text());data={};values={};reasons=[]
    for sec in sections:
        try:data[sec+'.yaml']=yaml.safe_load((content_dir/(sec+'.yaml')).read_text())
        except (FileNotFoundError,ValueError) as e:raise CalibrationMismatch(str(e)) from e
        expected=bindings.get('skeletons',{}).get(sec)
        if expected is not None and skeleton(data[sec+'.yaml'])!=expected:reasons.append(sec+': question/block structure changed')
    for fid,f in bindings['fields'].items():
        if fid[0] not in sections:continue
        try:value=field_value(f,data[f['file']])
        except (KeyError,IndexError,TypeError) as e:
            reasons.append(fid+': field is absent or changed type');continue
        if shape(value)!=f['shape']:reasons.append(fid+': text length, ruby, underline, whitespace or vector-mark geometry changed')
        values[fid]=chars_for(value,f['role'])
    if reasons:raise CalibrationMismatch('; '.join(reasons[:8])+(f'; {len(reasons)} differences in total' if len(reasons)>8 else ''))
    runs={};ledger=[]
    for runid,run in bindings['runs'].items():
        if runid[0] not in sections:continue
        glyphs=[]
        for i,g in enumerate(run['glyphs']):
            refs=g['refs'];formatter=g['formatter'];raw=[values[r['field']][r['char']] for r in refs]
            if formatter=='identity':text=raw[0]
            elif formatter=='ascii':text=normal(raw[0])
            elif formatter=='fullwidth':
                n=normal(raw[0]);text=''.join(chr(ord(c)+0xFEE0) if '!'<=c<='~' else c for c in n)
            elif formatter=='circled':
                n=normal(raw[0]);text=chr(0x2460+int(n)-1) if n.isdigit() and 1<=int(n)<=9 else raw[0]
            elif formatter=='ring':
                if raw[0] not in '①②③④⑤⑥⑦⑧⑨':raise CalibrationMismatch('Circled-answer demonstration changed symbol class')
                text='○'
            elif formatter=='combined':
                text=''.join(normal(c)[r['part']] for c,r in zip(raw,refs))
                if text!='()':raise CalibrationMismatch('Combined parenthesis component changed delimiter class')
                text='( )'
            else:raise ValueError('Unknown semantic formatter '+formatter)
            glyphs.append(text);ledger.append({'run':runid,'index':i,'refs':refs,'text':text})
        runs[runid]={'glyphs':glyphs}
    return {'schema_version':1,'runs':runs},ledger
