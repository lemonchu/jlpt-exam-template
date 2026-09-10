"""Shared semantic text and content traversal helpers."""
import unicodedata
from inline import parse

def binding_text(text):
    """Expand hanging-note markup to the equivalent visible character order.

    Fixed template slots and row diagnostics include the note label in the
    visible spelling ``base（注）``; layout keeps it as annotation metadata.
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

def iter_questions(value):
    """Yield every non-example object that owns answer options."""
    if isinstance(value,dict):
        if 'options' in value and not value.get('is_example',False):yield value
        for key,child in value.items():
            if key!='options':yield from iter_questions(child)
    elif isinstance(value,list):
        for child in value:yield from iter_questions(child)

def pointer(data,path):
    value=data
    if path=='':return value
    for segment in path.strip('/').split('/'):
        segment=segment.replace('~1','/').replace('~0','~')
        value=value[int(segment)] if isinstance(value,list) else value[segment]
    return value

def chars_for(value,role):
    return [c for a in parse(binding_text(value)) for c in (a.ruby if role=='ruby' else a.text) if not c.isspace()]

def normal(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if not c.isspace())
