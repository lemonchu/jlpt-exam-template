"""Readable inline markup, ruby clusters, and Japanese line breaking."""
from dataclasses import dataclass,replace
import re

@dataclass
class Atom:
    text: str
    bold: bool=False
    underline: bool=False
    ruby: str=''
    width: float=0
    annotation: str=''

OPEN='（([｛{「『【〈《〔'
CLOSE='、。，．・：；？！ー〜～）)]｝}」』】〉》〕ァィゥェォッャュョぁぃぅぇぉっゃゅょ々'

def parse(text,bold=False,underline=False):
    """Markup is deliberately small; malformed paired markup is an error."""
    if not isinstance(text,str):raise TypeError(f'Inline text must be a string, got {type(text).__name__}')
    out=[];i=0
    while i<len(text):
        if text.startswith('{{',i):
            end=text.find('}}',i+2)
            if end<0 or '|' not in text[i+2:end]:raise ValueError('Invalid note anchor')
            label,inner=text[i+2:end].split('|',1)
            children=parse(inner,bold,underline)
            if not children:raise ValueError('Empty note anchor')
            children[0]=replace(children[0],annotation=('（'+label+'）') if label.startswith('注') else label)
            out+=children;i=end+2;continue
        marker=next((m for m in ('__','**') if text.startswith(m,i)),None)
        if marker:
            end=text.find(marker,i+2)
            if end<0:raise ValueError(f'Unclosed inline marker {marker!r} in {text!r}')
            inner=text[i+2:end]
            if marker=='__' and re.fullmatch(r'[ 　]+',inner):out.append(Atom(inner,bold,True))
            else:out += parse(inner,bold or marker=='**',underline or marker=='__')
            i=end+2;continue
        if text[i]=='｜':
            m=re.match(r'｜([^《\n]+)《([^》\n]+)》',text[i:])
            if not m:raise ValueError(f'Invalid ruby markup near {text[i:]!r}')
            out.append(Atom(m[1],bold,underline,m[2]));i+=len(m[0]);continue
        # A fill-in blank is indivisible; ordinary Latin words also stay together.
        m=re.match(r'〔[0-9]+(?:-[A-Za-z])?〕|（[ \u3000]+）|[A-Za-z0-9]+(?:[.\-’\'][A-Za-z0-9]+)*',text[i:])
        if m:out.append(Atom(m[0],bold,underline));i+=len(m[0]);continue
        out.append(Atom(text[i],bold,underline));i+=1
    return out

def measure(atoms,catalog,size,section=''):
    result=[]
    for a in atoms:
        base=sum(catalog.width(c,size,a.bold,section) for c in a.text) if a.text!='\n' else 0
        ruby=sum(catalog.width(c,size*.5,a.bold,section) for c in a.ruby)
        if a.underline and a.text=='★':base=max(base,size*3)
        ref=re.fullmatch(r'〔([0-9]+)(-[A-Za-z])?〕',a.text)
        if ref and getattr(catalog,'compress_ruby',False):base=(33.75+(11.31 if ref[2] else 0))*size/11.3
        result.append(replace(a,width=base if getattr(catalog,"compress_ruby",False) else max(base,ruby)))
    return result

def lines(text,catalog,size,width,section='',bold=False):
    atoms=measure(parse(text,bold),catalog,size,section)
    # An unusually long Latin token may break character by character.
    expanded=[]
    for a in atoms:
        if a.width>width and len(a.text)>1 and not a.ruby:
            expanded += measure([replace(a,text=c) for c in a.text],catalog,size,section)
        else:expanded.append(a)
    result=[];line=[];used=0
    for a in expanded:
        if a.text=='\n':result.append(line);line=[];used=0;continue
        if a.width>width+1e-6:raise ValueError(f'An indivisible ruby/blank cluster exceeds line width: {a.text!r}')
        # An overflowing separator is discarded without committing the line;
        # the following closing punctuation can still carry its preceding atom.
        if a.text==' ' and not a.underline and used+a.width>width+1e-7:continue
        if line and used+a.width>width+1e-7:
            # Avoid leading closing punctuation by moving a preceding glyph with it.
            moved=[]
            if a.text[0] in CLOSE:
                # Carry the entire closing-punctuation suffix and at least one
                # preceding content atom. Moving just the last punctuation can
                # leave a sequence such as 。」 isolated on the next line.
                while line:
                    moved.insert(0,line.pop())
                    if moved[0].text[0] not in CLOSE and not (moved[0].text.isspace() and not moved[0].underline):break
            while line and line[-1].text[-1] in OPEN:moved.insert(0,line.pop())
            if line:result.append(line)
            line=moved;used=sum(x.width for x in line)
            if used+a.width>width+1e-7 and line:
                result.append(line);line=[];used=0
        if not line and a.text==' ':continue
        line.append(a);used+=a.width
    if line or not result:result.append(line)
    return result

def plain(text):
    return ''.join(a.text for a in parse(text))
