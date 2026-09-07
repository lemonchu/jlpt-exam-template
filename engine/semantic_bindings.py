"""Validate semantic content against calibrated component contracts."""
import hashlib,json,re,unicodedata
from inline import parse

class CalibrationMismatch(ValueError):pass

def binding_text(text):
    """Expand hanging-note markup to the equivalent visible character order.

    Measured profiles bind every visible character, including the small note
    label. Composition keeps that label as annotation metadata, while binding
    compares it with the source spelling ``base（注）``.
    """
    text=str(text);out=[];i=0
    while i<len(text):
        if text.startswith('{{',i):
            end=text.find('}}',i+2)
            if end<0 or '|' not in text[i+2:end]:raise ValueError('Invalid note anchor')
            label,inner=text[i+2:end].split('|',1)
            out.append(binding_text(inner));out.append(('（'+label+'）') if label.startswith('注') else label)
            i=end+2;continue
        out.append(text[i]);i+=1
    return ''.join(out)

def shape(text):
    atoms=parse(binding_text(text));base=''.join(a.text for a in atoms);ruby=[];styles=[];offset=0
    for a in atoms:
        n=sum(not c.isspace() for c in a.text)
        if a.ruby:ruby.append([offset,n,len(''.join(c for c in a.ruby if not c.isspace()))])
        if a.underline or a.bold:styles.append([offset,n,a.underline,a.bold])
        offset+=n
    return {'base_count':offset,'ruby':ruby,'styles':styles,'whitespace':[[m.start(),m.group()] for m in re.finditer(r'\s+',base)],'vector_marks':[[i,c] for i,c in enumerate(base) if c in '〔〕―-']}

def skeleton(v):
    keys={'groups','items','questions','stimulus','blocks','options','rows','title','instruction','prompt','text','label','asset','type','kind','is_example'}
    if isinstance(v,dict):return {k:(c if k in ('type','kind','is_example') else skeleton(c)) for k,c in v.items() if k in keys}
    if isinstance(v,list):return [skeleton(c) for c in v]
    return type(v).__name__

def iter_questions(value):
    """Yield every non-example object that owns answer options."""
    if isinstance(value,dict):
        if 'options' in value and not value.get('is_example',False):yield value
        for key,child in value.items():
            if key!='options':yield from iter_questions(child)
    elif isinstance(value,list):
        for child in value:yield from iter_questions(child)

def inline_layout_signature(text):
    """Coarse text presence plus inline annotations that alter composition.

    Exact glyph capacity remains the responsibility of ``resolve_runs``. This
    signature only closes gaps that have no measured run, notably empty table
    cells, while still allowing same-shape replacement text.
    """
    if not isinstance(text,str):return {'value_type':type(text).__name__}
    text_shape=shape(text);annotations=[];offset=0
    for atom in parse(text):
        count=sum(not c.isspace() for c in atom.text)
        if atom.annotation:annotations.append([offset,atom.annotation_span,shape(atom.annotation)])
        offset+=count
    presence='empty' if text=='' else 'whitespace' if text.isspace() else 'text'
    result={'value_type':'str','presence':presence,'annotations':annotations}
    # Whitespace-only underlined slots have no glyph run for resolve_runs to
    # inspect, so their exact blank/underline geometry belongs in the contract.
    if text_shape['base_count']==0:result['glyphless_shape']=text_shape
    return result

def layout_signature(v,semantic_values=False):
    """Describe content-side layout choices without including visible text.

    Measured components may substitute different text when its semantic shape
    still fits. They must not hide an editor's explicit alignment, style,
    table, image, or other layout change. Unknown non-semantic fields are kept
    deliberately, so new rendering options fail closed until calibrated.
    """
    # Experimental editorial roles are consumed only by --rules. They do not
    # change the legacy renderer, unlike ordinary style/indent/size options.
    ignored={'id','source_number','source_pages','rule_style'}
    semantic={'title','instruction','prompt','text','label'}
    if isinstance(v,dict):
        result={}
        for key,value in v.items():
            if key in ignored:continue
            if key in semantic:result[key]=inline_layout_signature(value)
            elif key=='alt':continue
            elif key in ('options','rows'):result[key]=layout_signature(value,True)
            else:result[key]=layout_signature(value)
        return result
    if isinstance(v,list):return [layout_signature(value,semantic_values) for value in v]
    return inline_layout_signature(v) if semantic_values else v

def layout_fingerprint(v):
    payload=json.dumps(layout_signature(v),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def pointer(data,path):
    value=data
    if path=='':return value
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
    return [c for a in parse(binding_text(value)) for c in (a.ruby if role=='ruby' else a.text) if not c.isspace()]

def normal(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if not c.isspace())
