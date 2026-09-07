#!/usr/bin/env python3
"""Render all measured slots exclusively from caller-supplied semantic text."""
import argparse,json,os,re,shutil,subprocess,sys
from dataclasses import dataclass,field
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

@dataclass(frozen=True)
class _RenderInputs:
    resources:Path
    out:Path
    layout:dict
    resolved:dict
    bindings:dict
    sections:list

@dataclass
class _RenderState:
    contents:list=field(default_factory=list)
    fallback_glyphs:list=field(default_factory=list)
    run_count:int=0
    slot_count:int=0
    drawn:int=0

class Resolver:
    def __init__(self,resources):
        self.resources=Path(resources);data=json.loads((self.resources/'font-catalog.json').read_text());self.fonts={};self.used=set();self.used_codes={};self.fallback_events=[];self._resolve_impl=None
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
        if self._resolve_impl is None:
            raise RuntimeError('Install the font policy before resolving glyphs')
        return self._resolve_impl(fontid,text,form)
    def use(self,fontid,text,form,runid,index):
        target,code=self.resolve(fontid,text,form)
        if target:
            self.used.add(target);self.used_codes.setdefault(target,set()).add(code)
            if target!=fontid:self.fallback_events.append({'run_id':runid,'index':index,'from_font':fontid,'to_font':target,'text':text,'form':form})
        return target,code
    def export(self,out):
        shutil.rmtree(out/'fonts',ignore_errors=True)
        lines=[]
        for fid in sorted(self.used):
            f=self.fonts[fid];source=Path(f.record['file'])
            if not source.is_absolute():source=self.resources/source
            if f.record.get('user_supplied'):
                font_dir=source.parent
                font_name=source.name
            else:
                rel=Path(f.record['file']);target=out/rel;target.parent.mkdir(parents=True,exist_ok=True)
                if f.record.get('family')=='fallback':export_subset(source,target,self.used_codes[fid])
                else:shutil.copyfile(source,target)
                font_dir=rel.parent;font_name=rel.name
            directory=font_dir.as_posix().rstrip('/')+'/'
            features=[f'Path={{{directory}}}',*f.record.get('fontspec_features',[])]
            lines.append('\\expandafter\\newfontfamily\\csname NFont%s\\endcsname[%s]{%s}'%(fid,','.join(features),font_name))
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

def _load_inputs(args):
    resources=Path(args.resources).resolve();out=Path(args.output_dir).resolve()
    if out==resources or out.is_relative_to(resources) or resources.is_relative_to(out):raise ValueError('Generated output must be separate from the text-free layout resources')
    out.mkdir(parents=True,exist_ok=True)
    (out/'render-report.json').unlink(missing_ok=True)
    if not args.compile:(out/'main.pdf').unlink(missing_ok=True)
    layout=json.loads(Path(getattr(args,'scene',None) or resources/'layout.json').read_text());resolved=json.loads(Path(args.resolved).read_text())
    if resolved.get('schema_version')!=1:raise ValueError('Unsupported resolved schema version')
    bindings=resolved.get('runs')
    if not isinstance(bindings,dict):raise ValueError('resolved.runs must be a mapping keyed by run_id')
    sections=args.sections.split(',')
    if len(sections)!=len(set(sections)) or any(s not in layout['sections'] for s in sections):raise ValueError('Unknown or duplicated section selection')
    return _RenderInputs(resources,out,layout,resolved,bindings,sections)

def _render_run(command,binding,resolver,page_number,state):
    runid=command['run_id'];slots=supplied_slots(binding,command)
    state.run_count+=1;state.slot_count+=len(slots)
    chunks=[]
    for i,(text,form) in enumerate(slots):
        fid,code=resolver.use(command['font'],text,form,runid,i)
        if fid is None:continue
        record=resolver.fonts[fid].record
        if record.get('family')=='fallback':
            state.fallback_glyphs.append({'page':page_number,'run_id':runid,'index':i,'text':text,'font':fid,'role':command.get('role'),'user_supplied':record.get('user_supplied',False)})
        if not chunks or chunks[-1]['font']!=fid:chunks.append({'font':fid,'offsets':[],'codes':[]})
        chunks[-1]['offsets'].append(command['offsets'][i]);chunks[-1]['codes'].append(code);state.drawn+=1
    output=[]
    for j,chunk in enumerate(chunks):
        contentid=runid+'-c'+str(j+1);characters=''.join('\\NChar{%d}'%code for code in chunk['codes'])
        state.contents.append('\\NDefineText{%s}{%s}'%(contentid,characters))
        values=[chunk['font'],number(command['sx']),number(command['sy']),number(command['x']),number(command['y']),','.join(number(x) for x in chunk['offsets']),'\\NGetText{'+contentid+'}']
        name='NRun'
        if command.get('rotation'):
            if command['shear']:raise ValueError('Simultaneous rotation and shear is unsupported')
            name='NRunRot';values.insert(0,number(command['rotation']))
        elif command['shear']:name='NRunSkew';values.insert(0,number(command['shear']))
        output.append('\\'+name+''.join('{'+x+'}' for x in values))
    return output

def _render_page(page,page_number,inputs,resolver,state):
    output=[]
    for command in page['commands']:
        kind=command['type']
        if kind=='vector':output.append('\\NVector{\n'+command['pdf']+'\n}')
        elif kind=='ink':output.append('\\NInk{'+','.join(number(v) for v in command['rgb'])+'}')
        elif kind=='image':
            asset=command['asset'];source=Path(inputs.resolved.get('asset_files',{}).get(asset,inputs.resources/asset))
            if not source.is_file():raise FileNotFoundError('Current image asset is missing: '+str(source))
            asset='assets/'+Path(asset).stem+source.suffix
            destination=inputs.out/asset;destination.parent.mkdir(parents=True,exist_ok=True)
            if source.resolve()!=destination.resolve():shutil.copyfile(source,destination)
            output.append('\\NImage{%s}{%s}{%s}{%s}{%s}'%(asset,number(command['width']),number(command['height']),number(command['x']),number(command['y'])))
        elif kind=='run':
            runid=command['run_id']
            if runid not in inputs.bindings:raise NeedReflow(f'Missing semantic binding for required run {runid}; original text is unavailable')
            output.extend(_render_run(command,inputs.bindings[runid],resolver,page_number,state))
        else:raise ValueError(f'Unknown calibrated command {kind!r}')
    return output

def _render_pages(inputs,resolver):
    pages=[];state=_RenderState()
    for section in inputs.sections:
        for page in inputs.layout['sections'][section]['pages']:
            pages.append(_render_page(page,len(pages)+1,inputs,resolver,state))
    return pages,state

def _write_latex_project(inputs,pages,state,resolver):
    out=inputs.out
    shutil.rmtree(out/'pages',ignore_errors=True);(out/'pages').mkdir()
    for i,page in enumerate(pages,1):(out/'pages'/f'page-{i:03}.tex').write_text('\n'.join(page)+'\n')
    (out/'content.generated.tex').write_text('% Generated only from supplied semantic slot text. No original-content fallback.\n'+'\n'.join(state.contents)+'\n')
    resolver.export(out);shutil.copyfile(inputs.resources/'n1-exact.sty',out/'n1-exact.sty')
    (out/'main.tex').write_text('\\documentclass{article}\n\\usepackage{n1-exact}\n\\input{content.generated.tex}\n\\begin{document}\n'+''.join('\\NPage{pages/page-%03d.tex}\n'%i for i in range(1,len(pages)+1))+'\\end{document}\n')
    (out/'build.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nxelatex -no-pdf -interaction=nonstopmode -halt-on-error main.tex\nxdvipdfmx -o main.pdf main.xdv\n');(out/'build.sh').chmod(0o755)

def _compile_project(out,page_count):
    logs=[]
    for cmd in [['xelatex','-no-pdf','-interaction=nonstopmode','-halt-on-error','main.tex'],['xdvipdfmx','-o','main.generated.pdf','main.xdv']]:
        process=subprocess.run(cmd,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);logs.append('$ '+' '.join(cmd)+'\n'+process.stdout);(out/'compile-output.txt').write_text('\n'.join(logs))
        if process.returncode or 'Missing character:' in process.stdout:raise RuntimeError('Compilation failed: '+process.stdout[-3500:])
    pdf=out/'main.generated.pdf'
    if not pdf.read_bytes().rstrip().endswith(b'%%EOF'):raise RuntimeError('Incomplete generated PDF')
    with fitz.open(pdf) as document:
        if document.is_repaired or len(document)!=page_count:raise RuntimeError('PDF page count/xref validation failed')
    # Windows requires a writable file handle for fsync and cannot open a
    # directory through os.open. Keep the directory durability step on POSIX.
    with pdf.open('r+b') as stream:os.fsync(stream.fileno())
    os.replace(pdf,out/'main.pdf')
    if os.name!='nt':
        fd=os.open(out,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

def _build_report(inputs,pages,state,resolver,font_policy):
    report={'status':'PASS','backend':'component-scene','pages':len(pages),'sections':inputs.sections,'resolved_runs':state.run_count,'resolved_slots':state.slot_count,'drawn_glyphs':state.drawn,'font_count':len(resolver.used),'fallback_events':resolver.fallback_events,'unbound_required_runs':[],'content_source':'resolved.runs only','layout_text_fallback':False}
    report['font_policy']=font_policy
    report['fallback_glyphs']=state.fallback_glyphs
    return report

def render(args):
    inputs=_load_inputs(args);resolver=Resolver(inputs.resources)
    from font_overrides import install_overrides
    font_policy=install_overrides(resolver,getattr(args,'font_config',None),getattr(args,'project_root',None))
    pages,state=_render_pages(inputs,resolver)
    _write_latex_project(inputs,pages,state,resolver)
    report=_build_report(inputs,pages,state,resolver,font_policy)
    if args.compile:_compile_project(inputs.out,len(pages))
    (inputs.out/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='fallback_events'},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resources',required=True);p.add_argument('--resolved',required=True);p.add_argument('--sections',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--compile',action='store_true')
    try:render(p.parse_args());return 0
    except NeedReflow as e:print(json.dumps({'status':'NEEDS_FLOW','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 2
    except GlyphError as e:print(json.dumps({'status':'GLYPH_ERROR','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 3
    except Exception as e:print(json.dumps({'status':'ERROR','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
