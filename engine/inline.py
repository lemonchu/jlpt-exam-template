"""Readable inline markup, ruby clusters, and Japanese line breaking."""
from dataclasses import dataclass,replace
import re
from geometry import CLOZE_BOX

@dataclass
class Atom:
    text: str
    bold: bool=False
    underline: bool=False
    ruby: str=''
    width: float=0
    annotation: str=''
    annotation_span: int=0
    ruby_parts: tuple=()

@dataclass
class NetworkAddress(Atom):
    """An email/URL, whose internal letter spacing must remain natural."""

OPEN='（([｛{「『【〈《〔'
CLOSE='、。，．・：；？！ー〜～）)]｝}」』】〉》〕ァィゥェォッャュョぁぃぅぇぉっゃゅょ々'
# A's measured cloze frames use half-em side spacing, compressed before closing punctuation.
REFERENCE_BOX_CLOSING='、。，．・：；？！）)]｝}」』】〉》'
REFERENCE_BOX_PATTERN=r'〔([0-9]+)(-[A-Za-z])?〕'
REFERENCE_BOX_RE=re.compile(REFERENCE_BOX_PATTERN)
EDITORIAL_LABEL_PATTERN=r'[（(](?:注[ \u3000]*[0-9０-９]*|中略|前略|後略)[）)]'
EDITORIAL_LABEL_RE=re.compile(EDITORIAL_LABEL_PATTERN)
TOKEN_RE=re.compile(REFERENCE_BOX_PATTERN+'|'+EDITORIAL_LABEL_PATTERN+r'|（[ \u3000]+）|[A-Za-z0-9]+(?:[.\-’\'][A-Za-z0-9]+)*')
ADDRESS_RE=re.compile(
    r'(?:https?://|www\.)[A-Za-z0-9][A-Za-z0-9._~:/?#@!$&+,;=%-]*'
    r'|[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}',
    re.IGNORECASE)

def parse(text,bold=False,underline=False,*,preserve_addresses=False):
    """Markup is deliberately small; malformed paired markup is an error."""
    if not isinstance(text,str):raise TypeError(f'Inline text must be a string, got {type(text).__name__}')
    out=[];i=0
    while i<len(text):
        if text.startswith('{{',i):
            end=text.find('}}',i+2)
            if end<0 or '|' not in text[i+2:end]:raise ValueError('Invalid note anchor')
            label,inner=text[i+2:end].split('|',1)
            children=parse(inner,bold,underline,preserve_addresses=preserve_addresses)
            if not children:raise ValueError('Empty note anchor')
            span=sum(sum(not c.isspace() for c in child.text) for child in children)
            children[0]=replace(children[0],annotation=('（'+label+'）') if label.startswith('注') else label,
                                annotation_span=span)
            out+=children;i=end+2;continue
        marker=next((m for m in ('__','**') if text.startswith(m,i)),None)
        if marker:
            end=text.find(marker,i+2)
            if end<0:raise ValueError(f'Unclosed inline marker {marker!r} in {text!r}')
            inner=text[i+2:end]
            if marker=='__' and re.fullmatch(r'[ 　]+',inner):out.append(Atom(inner,bold,True))
            else:out += parse(inner,bold or marker=='**',underline or marker=='__',
                              preserve_addresses=preserve_addresses)
            i=end+2;continue
        if text[i]=='｜':
            m=re.match(r'｜([^《\n]+)《([^》\n]+)》',text[i:])
            if not m:raise ValueError(f'Invalid ruby markup near {text[i:]!r}')
            parts=tuple(m[2].split('|')) if '|' in m[2] else ()
            if parts and (len(parts)!=len(m[1]) or not all(parts)):
                raise ValueError('Partitioned ruby requires one nonempty reading per base character')
            out.append(Atom(m[1],bold,underline,''.join(parts) if parts else m[2],ruby_parts=parts));i+=len(m[0]);continue
        if preserve_addresses:
            address=ADDRESS_RE.match(text,i)
            if address:
                # Sentence punctuation is outside an address; fullwidth CJK
                # punctuation is already excluded from the ASCII pattern.
                token=address[0].rstrip('.,;:!')
                out.append(NetworkAddress(token,bold,underline));i+=len(token);continue
        # A fill-in blank is indivisible; ordinary Latin words also stay together.
        m=TOKEN_RE.match(text,i)
        if m:out.append(Atom(m[0],bold,underline));i+=len(m[0]);continue
        out.append(Atom(text[i],bold,underline));i+=1
    return out

def address_fragments(atom,catalog,size,width,section=''):
    """Keep an address whole when possible, then prefer URL/mail separators.

    Only an address longer than the applicable line measure reaches this path.
    A path component without any safe delimiter may finally break at a glyph
    boundary, preserving every character instead of overflowing or truncating.
    All fragments retain their address type so justification cannot spread them.
    """
    if not isinstance(atom,NetworkAddress) or atom.width<=width+1e-7:
        return [atom]
    result=[];remaining=atom.text;offset=0
    scheme_end=atom.text.find('://')+3 if '://' in atom.text else 0
    while remaining:
        used=0;end=0
        for char in remaining:
            advance=catalog.width(char,size,atom.bold,section)
            if used+advance>width+1e-7:break
            used+=advance;end+=1
        if not end:raise ValueError('An address glyph exceeds line width: '+remaining[0])
        if end<len(remaining):
            safe=[i+1 for i,char in enumerate(remaining[:end])
                  if char in '/?&#@.-' and offset+i+1>scheme_end]
            if safe:end=safe[-1]
        fragment=replace(atom,text=remaining[:end],
                         annotation=atom.annotation if not result else '',
                         annotation_span=atom.annotation_span if not result else 0)
        result.extend(measure([fragment],catalog,size,section))
        remaining=remaining[end:];offset+=end
    return result

def measure(atoms,catalog,size,section=''):
    result=[]
    prepare=getattr(catalog,'prepare_atoms',None)
    if prepare:atoms=prepare(atoms)
    for a in atoms:
        ref=REFERENCE_BOX_RE.fullmatch(a.text)
        if ref and getattr(catalog,'compress_ruby',False):
            frame=CLOZE_BOX.frame_width(ref[2])
            base=(frame+2*CLOZE_BOX.margin)*size/CLOZE_BOX.body_size
            # Delimiters describe a vector frame, not printed font glyphs.
            result.append(replace(a,width=base));continue
        base=sum(catalog.width(c,size,a.bold,section) for c in a.text) if a.text!='\n' else 0
        adjust_width=getattr(catalog,'atom_width',None)
        if adjust_width:base=adjust_width(a,base,size,section)
        ruby=sum(catalog.width(c,size*.5,a.bold,section) for c in a.ruby)
        if a.underline and a.text=='★':base=max(base,size*3)
        result.append(replace(a,width=base if getattr(catalog,"compress_ruby",False) else max(base,ruby)))
    if getattr(catalog,'compress_ruby',False):
        reduction=(CLOZE_BOX.margin-CLOZE_BOX.closing_margin)*size/CLOZE_BOX.body_size
        for i in range(len(result)-1):
            if REFERENCE_BOX_RE.fullmatch(result[i].text) and result[i+1].text[:1] in REFERENCE_BOX_CLOSING:
                result[i]=replace(result[i],width=result[i].width-reduction)
    return result

def lines(text,catalog,size,width,section='',bold=False):
    atoms=measure(parse(text,bold),catalog,size,section)
    # An unusually long Latin token may break character by character.
    expanded=[]
    for a in atoms:
        if a.width>width and len(a.text)>1 and not a.ruby and not EDITORIAL_LABEL_RE.fullmatch(a.text):
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
