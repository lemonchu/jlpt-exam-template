#!/usr/bin/env python3
"""Resolve measured non-body text from editable YAML only.
No PDF, source transcript, or literal fallback is read at runtime.
"""
from pathlib import Path
import argparse,json,re
import yaml


def pointer_get(data,pointer):
    value=data
    if pointer=='':return value
    for part in pointer.strip('/').split('/'):
        key=part.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def width_digits(value,width):
    text=str(value)
    if width=='fullwidth':return text.translate(str.maketrans('0123456789','０１２３４５６７８９'))
    if width=='halfwidth':return text.translate(str.maketrans('０１２３４５６７８９','0123456789'))
    if width is None:return text
    raise ValueError(f'Unknown digit width: {width}')


def variable_value(spec,metadata):
    if 'pointer' in spec:value=pointer_get(metadata,spec['pointer'])
    elif spec.get('calc')=='section_page':
        section=metadata['sections'][spec['section']]
        value=int(spec['page'])-int(section['first_content_page'])+int(section['first_printed_page'])
    elif spec.get('calc')=='booklet_body_pages':
        if '_body_pages' in metadata:return width_digits(metadata['_body_pages'],spec.get('digits'))
        sections=metadata['booklets'][spec['booklet']]['sections']
        value=sum(int(metadata['sections'][s]['page_count'])-int(metadata['sections'][s]['first_content_page'])+1 for s in sections)
    elif 'number' in spec:value=int(spec['number'])
    else:raise ValueError(f'Unsupported variable expression: {spec}')
    return width_digits(value,spec.get('digits'))


def format_field(field,metadata):
    text=str(pointer_get(metadata,field['pointer']))
    for transform in field.get('formatter',[]):
        op=transform['op']
        if op=='format':
            variables={k:variable_value(v,metadata) for k,v in transform.get('variables',{}).items()}
            text=text.format(**variables)
        elif op=='prepend':
            template=str(pointer_get(metadata,transform['pointer']))
            variables={k:variable_value(v,metadata) for k,v in transform.get('variables',{}).items()}
            text=template.format(**variables)+text
        elif op=='digits':text=width_digits(text,transform['width'])
        elif op=='strip_whitespace':text=re.sub(r'\s+','',text)
        else:raise ValueError(f'Unsupported generic formatter: {op}')
    if field.get('role','text')!='text':raise ValueError('Non-body fields must have text role')
    return list(text)


def resolve(metadata_path,bindings_path,sections=None,body_pages=None,run_ids=None):
    metadata_path=Path(metadata_path);bindings=json.loads(Path(bindings_path).read_text())
    metadata=yaml.safe_load(metadata_path.read_text())
    for category,entries in bindings.get('page_plan',{}).items():
        for key,value in entries.items():metadata.setdefault(category,{}).setdefault(key,{}).update(value)
    if body_pages is not None:metadata['_body_pages']=body_pages
    if run_ids is not None:bindings['runs']={k:v for k,v in bindings['runs'].items() if k in run_ids}
    active={b['field'] for runid,r in bindings['runs'].items() if sections is None or runid[0] in sections for b in r['glyphs']}
    field_chars={}
    for name,field in bindings['fields'].items():
        if name not in active:continue
        if field['file']!='metadata.yaml':
            raise ValueError(f'Binding references {field["file"]}, but metadata file is {metadata_path.name}')
        chars=format_field(field,metadata)
        expected=field.get('glyph_slots')
        if expected is not None and len(chars)!=expected:
            raise ValueError(f'Metadata field {field["pointer"]} now has {len(chars)} glyphs; measured layout has {expected}. Regenerate the flowing layout for a length-changing edit.')
        field_chars[name]=chars
    runs={}
    for runid,record in bindings['runs'].items():
        if sections is not None and runid[0] not in sections:continue
        glyphs=[]
        for binding in record['glyphs']:
            text=''.join(field_chars[binding['field']][i] for i in binding['char_indices'])
            glyphs.append(text)
        runs[runid]={'glyphs':glyphs}
    return {'runs':runs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata',type=Path,default=Path(__file__).with_name('metadata.yaml'))
    parser.add_argument('--bindings',type=Path,default=Path(__file__).with_name('nonbody-bindings.json'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=resolve(args.metadata,args.bindings)
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(encoded)
    else:print(encoded,end='')

if __name__=='__main__':main()
