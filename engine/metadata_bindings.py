"""Resolve measured non-body text from editable YAML only.
No PDF, source transcript, or literal fallback is read at runtime.
"""
from pathlib import Path
import json,re
import yaml
from semantic_bindings import pointer as pointer_get

FULLWIDTH_DIGITS = str.maketrans('0123456789', '０１２３４５６７８９')
HALFWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')


def width_digits(value,width):
    text=str(value)
    if width=='fullwidth':return text.translate(FULLWIDTH_DIGITS)
    if width=='halfwidth':return text.translate(HALFWIDTH_DIGITS)
    if width is None:return text
    raise ValueError(f'Unknown digit width: {width}')


def variable_value(spec,metadata):
    if 'pointer' in spec:value=pointer_get(metadata,spec['pointer'])
    elif spec.get('calc')=='section_page':
        section=metadata['sections'][spec['section']]
        value=int(spec['page'])-int(section['first_content_page'])+int(section['first_printed_page'])
    elif spec.get('calc')=='booklet_body_pages':
        if '_body_pages' in metadata:value=metadata['_body_pages']
        else:
            sections=metadata['booklets'][spec['booklet']]['sections']
            value=sum(int(metadata['sections'][s]['page_count'])-int(metadata['sections'][s]['first_content_page'])+1 for s in sections)
    elif 'number' in spec:value=int(spec['number'])
    else:raise ValueError(f'Unsupported variable expression: {spec}')
    return width_digits(value,spec.get('digits'))


def _format_template(template,transform,metadata):
    variables={k:variable_value(v,metadata) for k,v in transform.get('variables',{}).items()}
    return str(template).format(**variables)


def format_pointer_template(transform,metadata):
    """Resolve one metadata template and all of its declared variables."""
    return _format_template(pointer_get(metadata,transform['pointer']),transform,metadata)


def format_field(field,metadata):
    text=str(pointer_get(metadata,field['pointer']))
    for transform in field.get('formatter',[]):
        op=transform['op']
        if op=='format':
            text=_format_template(text,transform,metadata)
        elif op=='prepend':
            text=format_pointer_template(transform,metadata)+text
        elif op=='digits':text=width_digits(text,transform['width'])
        elif op=='strip_whitespace':text=re.sub(r'\s+','',text)
        else:raise ValueError(f'Unsupported generic formatter: {op}')
    if field.get('role','text')!='text':raise ValueError('Non-body fields must have text role')
    return list(text)


def load_metadata(metadata_path,bindings,body_pages=None):
    """Load metadata and apply the measured profile's explicit page plan."""
    metadata=yaml.safe_load(Path(metadata_path).read_text())
    for category,entries in bindings.get('page_plan',{}).items():
        for key,value in entries.items():metadata.setdefault(category,{}).setdefault(key,{}).update(value)
    if body_pages is not None:
        if isinstance(body_pages,bool) or not isinstance(body_pages,int) or body_pages<0:
            raise ValueError('body_pages must be a nonnegative integer')
        metadata['_body_pages']=body_pages
    return metadata


def resolve_loaded(metadata,bindings,metadata_name='metadata.yaml',*,sections=None,run_ids=None):
    """Resolve runs from metadata and bindings that have already been loaded."""
    selected_runs={runid:record for runid,record in bindings['runs'].items()
                   if (run_ids is None or runid in run_ids) and (sections is None or runid[0] in sections)}
    active={binding['field'] for record in selected_runs.values() for binding in record['glyphs']}
    field_chars={}
    for name,field in bindings['fields'].items():
        if name not in active:continue
        if field['file']!=metadata_name:
            raise ValueError(f'Binding references {field["file"]}, but metadata file is {metadata_name}')
        chars=format_field(field,metadata)
        expected=field.get('glyph_slots')
        if expected is not None and len(chars)!=expected:
            raise ValueError(f'Metadata field {field["pointer"]} now has {len(chars)} glyphs; measured layout has {expected}. Regenerate the flowing layout for a length-changing edit.')
        field_chars[name]=chars
    resolved_runs={}
    for runid,record in selected_runs.items():
        glyphs=[]
        for binding in record['glyphs']:
            text=''.join(field_chars[binding['field']][i] for i in binding['char_indices'])
            glyphs.append(text)
        resolved_runs[runid]={'glyphs':glyphs}
    return {'runs':resolved_runs}


def resolve(metadata_path,bindings_path,sections=None,body_pages=None,run_ids=None):
    metadata_path=Path(metadata_path);bindings=json.loads(Path(bindings_path).read_text())
    metadata=load_metadata(metadata_path,bindings,body_pages)
    return resolve_loaded(metadata,bindings,metadata_path.name,sections=sections,run_ids=run_ids)
