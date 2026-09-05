#!/usr/bin/env python3
"""Render all measured slots exclusively from caller-supplied semantic text."""
import argparse,json,os,re,shutil,subprocess,sys
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
from fontTools.ttLib import TTFont
import fitz
from font_subset import export_subset

class NeedReflow(ValueError):pass
class GlyphError(ValueError):pass

@dataclass
class Font:
    id:str
    record:dict
    cmap:dict
    manifest:list

class Resolver:
    def __init__(self,resources):
        self.resources=Path(resources);data=json.loads((self.resources/'font-catalog.json').read_text());self.fonts={};self.used=set();self.used_codes={};self.fallback_events=[]
        sample_path=self.resources/'sample-fonts.json'
        samples=json.loads(sample_path.read_text())['fonts'] if sample_path.is_file() else {}
        catalog={**data['fonts'],**samples,**data.get('fallback_fonts',{})}
        missing=[record['file'] for record in catalog.values() if not (self.resources/record['file']).is_file()]
        if missing:
            raise FileNotFoundError(f'{len(missing)} bundled profile font files are missing (first: {missing[0]}). '
                                    'Download or clone the complete source tree, including profiles/n1-original/fonts. '
                                    'No substitute fonts are used. See docs/FONTS.md.')
        for fid,record in catalog.items():
            tt=TTFont(self.resources/record['file']);cm=tt.getBestCmap() or {};tt.close()
            self.fonts[fid]=Font(fid,record,cm,record.get('glyphs',[]))
    @staticmethod
    def vertical(g):return any(0xFE10<=c<=0xFE1F or 0xFE30<=c<=0xFE48 for c in g.get('unicode',[]))
    @staticmethod
    def combine(text):
        return '( )' if re.fullmatch(r'[（(]\s*[）)]',text) else text
    def glyph_code(self,font,glyph,text,force_pua=False):
        if not force_pua and len(text)==1 and font.cmap.get(ord(text))==glyph['glyph']:return ord(text)
        code=glyph.get('pua')
        if code is None or font.cmap.get(code)!=glyph['glyph']:raise GlyphError(f'{font.id}: font manifest has no valid render mapping for semantic {text!r}')
        return code
    def native(self,font,text,form):
        if form=='combined':
            normalized=self.combine(text)
            choices=[g for g in font.manifest if g.get('semantic_text')==normalized]
            if len(choices)>1:raise GlyphError(f'Ambiguous combined glyph in {font.id}: {text!r}')
            if choices:return self.glyph_code(font,choices[0],text,True)
            return None
        if len(text)!=1:raise NeedReflow(f'A normal/vertical slot needs one Unicode character, got {text!r}')
        cp=ord(text)
        if form=='vertical':
            choices=[g for g in font.manifest if self.vertical(g) and (cp in g.get('unicode',[]) or g.get('semantic_text')==text)]
            if len(choices)>1:raise GlyphError(f'Ambiguous vertical glyph in {font.id}: {text!r}')
            if choices:return self.glyph_code(font,choices[0],text,True)
            # A newly authored upright CJK character uses its ordinary form.
            if text not in '、。「」『』（）()ー―—〜～':return cp if cp in font.cmap else None
            return None
        if form!='normal':raise NeedReflow(f'Unknown slot form {form!r}')
        if font.record.get('family')=='custom':
            # EdiF control codes and accidental cmap aliases are never semantic input.
            choices=[g for g in font.manifest if g.get('semantic_text')==text]
            if len(choices)>1:raise GlyphError(f'Ambiguous custom glyph in {font.id}: {text!r}')
            return self.glyph_code(font,choices[0],text) if choices else None
        return cp if cp in font.cmap and font.cmap[cp]!='.notdef' else None
    @lru_cache(maxsize=None)
    def resolve(self,fontid,text,form='normal'):
        if not isinstance(text,str) or not text:raise GlyphError('Every semantic slot must supply non-empty text')
        for char in text:
            cp=ord(char)
            if 0xE000<=cp<=0xF8FF or 0xF0000<=cp<=0xFFFFD or 0x100000<=cp<=0x10FFFD:raise GlyphError('Private-use codepoints are not accepted as semantic text; supply the character and generic form')
            if cp<32 and char not in ' \t':raise GlyphError(f'Control code U+{cp:04X} is not semantic text')
        if text.isspace():return None,None
        original=self.fonts[fontid];code=self.native(original,text,form)
        if code is not None:return fontid,code
        # Deterministic family routing; no original character is retained or compared.
        def rank(f):
            r=f.record;o=original.record
            return (r.get('bold',False)!=o.get('bold',False),r.get('family') not in (o.get('family'),'fallback'),r.get('family')=='fallback',r.get('section')!=o.get('section'),r.get('priority',1),f.id)
        candidates=sorted((f for f in self.fonts.values() if f.id!=fontid),key=rank)
        for f in candidates:
            code=self.native(f,text,form)
            if code is not None:return f.id,code
        raise GlyphError(f'No glyph covers {text!r} with form={form!r}; original font was {fontid}')
    def use(self,fontid,text,form,runid,index):
        target,code=self.resolve(fontid,text,form)
        if target:
            self.used.add(target);self.used_codes.setdefault(target,set()).add(code)
            if target!=fontid:self.fallback_events.append({'run_id':runid,'index':index,'from_font':fontid,'to_font':target,'text':text,'form':form})
        return target,code
    def export(self,out):
        lines=[]
        for fid in sorted(self.used):
            f=self.fonts[fid];rel=Path(f.record['file']);target=out/rel;target.parent.mkdir(parents=True,exist_ok=True)
            if f.record.get('family')=='fallback':export_subset(self.resources/rel,target,self.used_codes[fid])
            else:shutil.copyfile(self.resources/rel,target)
            lines.append('\\expandafter\\newfontfamily\\csname NFont%s\\endcsname[Path=%s/]{%s}'%(fid,rel.parent.as_posix(),rel.name))
        (out/'fonts.tex').write_text('\n'.join(lines)+'\n')

def supplied_slots(value,run):
    if isinstance(value,str):value={'text':value}
    if not isinstance(value,dict):raise NeedReflow(f"{run['run_id']}: run binding must contain text or glyphs")
    if 'glyphs' in value:
        glyphs=value['glyphs']
        if not isinstance(glyphs,list):raise NeedReflow(f"{run['run_id']}: glyphs must be a list")
    elif 'text' in value:glyphs=list(value['text'])
    else:raise NeedReflow(f"{run['run_id']}: missing required semantic text")
    if len(glyphs)!=run['slot_count']:raise NeedReflow(f"{run['run_id']}: semantic slot count {len(glyphs)} differs from layout capacity {run['slot_count']}; use flow layout")
    result=[];forms=run.get('forms',['normal']*run['slot_count'])
    for i,(g,form) in enumerate(zip(glyphs,forms)):
        if isinstance(g,str):text=g
        elif isinstance(g,dict):
            if 'text' not in g:raise NeedReflow(f"{run['run_id']} slot {i}: missing text")
            text=g['text'];form=g.get('form',g.get('orientation',form))
            if form=='horizontal':form='normal'
        else:raise NeedReflow(f"{run['run_id']} slot {i}: invalid semantic glyph")
        result.append((text,form))
    return result

def number(x):return format(float(x),'.12g')

def render(args):
    resources=Path(args.resources).resolve();out=Path(args.output_dir).resolve()
    if out==resources or out.is_relative_to(resources) or resources.is_relative_to(out):raise ValueError('Generated output must be separate from the text-free layout resources')
    out.mkdir(parents=True,exist_ok=True)
    layout=json.loads(Path(getattr(args,'scene',None) or resources/'layout.json').read_text());resolved=json.loads(Path(args.resolved).read_text())
    if resolved.get('schema_version')!=1:raise ValueError('Unsupported resolved schema version')
    bindings=resolved.get('runs')
    if not isinstance(bindings,dict):raise ValueError('resolved.runs must be a mapping keyed by run_id')
    sections=args.sections.split(',')
    if len(sections)!=len(set(sections)) or any(s not in layout['sections'] for s in sections):raise ValueError('Unknown or duplicated section selection')
    resolver=Resolver(resources)
    from font_overrides import install_overrides
    font_policy=install_overrides(resolver,getattr(args,'font_config',None),getattr(args,'project_root',None))
    contents=[];pages=[];run_count=slot_count=0;drawn=0;used_runs=[];fallback_glyphs=[]
    for section in sections:
        for page in layout['sections'][section]['pages']:
            output=[]
            for command in page['commands']:
                kind=command['type']
                if kind=='vector':output.append('\\NVector{\n'+command['pdf']+'\n}')
                elif kind=='ink':output.append('\\NInk{'+','.join(number(v) for v in command['rgb'])+'}')
                elif kind=='image':
                    asset=command['asset'];source=Path(resolved.get('asset_files',{}).get(asset,resources/asset))
                    if not source.is_file():raise FileNotFoundError('Current image asset is missing: '+str(source))
                    asset='assets/'+Path(asset).stem+source.suffix
                    destination=out/asset;destination.parent.mkdir(parents=True,exist_ok=True);
                    if source.resolve()!=destination.resolve():shutil.copyfile(source,destination)
                    output.append('\\NImage{%s}{%s}{%s}{%s}{%s}'%(asset,number(command['width']),number(command['height']),number(command['x']),number(command['y'])))
                elif kind=='run':
                    runid=command['run_id']
                    if runid not in bindings:raise NeedReflow(f'Missing semantic binding for required run {runid}; original text is unavailable')
                    slots=supplied_slots(bindings[runid],command);run_count+=1;slot_count+=len(slots);used_runs.append(runid)
                    chunks=[]
                    for i,(text,form) in enumerate(slots):
                        fid,code=resolver.use(command['font'],text,form,runid,i)
                        if fid is None:continue
                        if resolver.fonts[fid].record.get('family')=='fallback':fallback_glyphs.append({'page':len(pages)+1,'run_id':runid,'index':i,'text':text,'font':fid,'role':command.get('role'),'user_supplied':resolver.fonts[fid].record.get('user_supplied',False)})
                        if not chunks or chunks[-1]['font']!=fid:chunks.append({'font':fid,'offsets':[],'codes':[]})
                        chunks[-1]['offsets'].append(command['offsets'][i]);chunks[-1]['codes'].append(code);drawn+=1
                    for j,chunk in enumerate(chunks):
                        contentid=runid+'-c'+str(j+1);characters=''.join('\\NChar{%d}'%code for code in chunk['codes'])
                        contents.append('\\NDefineText{%s}{%s}'%(contentid,characters))
                        values=[chunk['font'],number(command['sx']),number(command['sy']),number(command['x']),number(command['y']),','.join(number(x) for x in chunk['offsets']),'\\NGetText{'+contentid+'}']
                        name='NRun'
                        if command.get('rotation'):
                            if command['shear']:raise ValueError('Simultaneous rotation and shear is unsupported')
                            name='NRunRot';values.insert(0,number(command['rotation']))
                        elif command['shear']:name='NRunSkew';values.insert(0,number(command['shear']))
                        output.append('\\'+name+''.join('{'+x+'}' for x in values))
                else:raise ValueError(f'Unknown calibrated command {kind!r}')
            pages.append(output)
    (out/'pages').mkdir(exist_ok=True)
    for i,p in enumerate(pages,1):(out/'pages'/f'page-{i:03}.tex').write_text('\n'.join(p)+'\n')
    (out/'content.generated.tex').write_text('% Generated only from supplied semantic slot text. No original-content fallback.\n'+'\n'.join(contents)+'\n')
    resolver.export(out);shutil.copyfile(resources/'n1-exact.sty',out/'n1-exact.sty')
    (out/'main.tex').write_text('\\documentclass{article}\n\\usepackage{n1-exact}\n\\input{content.generated.tex}\n\\begin{document}\n'+''.join('\\NPage{pages/page-%03d.tex}\n'%i for i in range(1,len(pages)+1))+'\\end{document}\n')
    (out/'build.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nxelatex -no-pdf -interaction=nonstopmode -halt-on-error main.tex\nxdvipdfmx -o main.pdf main.xdv\n');(out/'build.sh').chmod(0o755)
    report={'status':'PASS','backend':'component-scene','pages':len(pages),'sections':sections,'resolved_runs':run_count,'resolved_slots':slot_count,'drawn_glyphs':drawn,'font_count':len(resolver.used),'fallback_events':resolver.fallback_events,'unbound_required_runs':[],'content_source':'resolved.runs only','layout_text_fallback':False}
    report['font_policy']=font_policy
    report['fallback_glyphs']=fallback_glyphs
    (out/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if args.compile:
        logs=[]
        for cmd in [['xelatex','-no-pdf','-interaction=nonstopmode','-halt-on-error','main.tex'],['xdvipdfmx','-o','main.generated.pdf','main.xdv']]:
            p=subprocess.run(cmd,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);logs.append('$ '+' '.join(cmd)+'\n'+p.stdout);(out/'compile-output.txt').write_text('\n'.join(logs))
            if p.returncode or 'Missing character:' in p.stdout:raise RuntimeError('Compilation failed: '+p.stdout[-3500:])
        pdf=out/'main.generated.pdf'
        if not pdf.read_bytes().rstrip().endswith(b'%%EOF'):raise RuntimeError('Incomplete generated PDF')
        with fitz.open(pdf) as d:
            if d.is_repaired or len(d)!=len(pages):raise RuntimeError('PDF page count/xref validation failed')
        with pdf.open('rb') as f:os.fsync(f.fileno())
        os.replace(pdf,out/'main.pdf');fd=os.open(out,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    print(json.dumps({k:v for k,v in report.items() if k!='fallback_events'},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resources',required=True);p.add_argument('--resolved',required=True);p.add_argument('--sections',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--compile',action='store_true')
    try:render(p.parse_args());return 0
    except NeedReflow as e:print(json.dumps({'status':'NEEDS_FLOW','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 2
    except GlyphError as e:print(json.dumps({'status':'GLYPH_ERROR','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 3
    except Exception as e:print(json.dumps({'status':'ERROR','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
