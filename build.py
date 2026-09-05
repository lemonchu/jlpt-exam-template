#!/usr/bin/env python3
"""Compose every exam with shared measured N1 components and one XeLaTeX renderer."""
from pathlib import Path
from argparse import ArgumentParser,Namespace
import json,copy,re,shutil,sys,hashlib
import yaml
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'engine'))
from component_fonts import ComponentFonts
from component_layout import ComponentLayout
from reference_components import ReferenceComponents
from calibrated_renderer import render
from semantic_bindings import pointer

def load(p):
    d=yaml.safe_load(Path(p).read_text())
    if not isinstance(d,dict):raise ValueError(f'{p}: expected YAML mapping')
    return d

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--paper',default='paper-a');parser.add_argument('--booklet',choices=['written','listening'],default='written')
    parser.add_argument('--blueprint',type=Path);parser.add_argument('--metadata',type=Path)
    parser.add_argument('--fonts',type=Path,default=ROOT/'fonts.yaml' if (ROOT/'fonts.yaml').is_file() else None,
                        help='Complete-font configuration; defaults to project fonts.yaml when present')
    parser.add_argument('--no-compile',action='store_true');parser.add_argument('--recompose',action='store_true',help='Recompute every variable content component using the same standard typography')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.paper):parser.error('Invalid paper folder name')
    content=ROOT/'content'/args.paper;bp_path=args.blueprint or ROOT/'blueprints'/f'{args.booklet}.yaml';bp=load(bp_path)
    metadata_path=args.metadata or (content/'metadata.yaml' if (content/'metadata.yaml').exists() else ROOT/'content/common/metadata.yaml');metadata=load(metadata_path)
    groups={}
    for sec in ['V','G','R','L']:
        path=content/f'{sec}.yaml'
        if path.exists():
            for g in load(path)['groups']:
                if g['id'] in groups:raise ValueError('Duplicate group id')
                groups[g['id']]=g
    component_path=bp_path.parent/bp['components_file'] if bp.get('components_file') else None
    component_defaults=load(component_path).get('components',{}) if component_path else {}
    bp.setdefault('header',metadata['booklets'][args.booklet]['subject_ja'])
    profile=ROOT/'profiles/n1-original';ref=ReferenceComponents(profile,metadata_path)
    out=ROOT/'output'/f'{args.paper}-{args.booklet}';out.mkdir(parents=True,exist_ok=True)
    fonts=ComponentFonts(profile,args.fonts,ROOT);ref.fonts=fonts;layout=ComponentLayout(fonts,bp,ROOT/'resources',out,ref)
    contracts=json.loads((profile/'composition-contracts.json').read_text())
    pristine=json.loads(json.dumps(load(bp_path)))==contracts['blueprints'][args.booklet] and json.loads(json.dumps(load(component_path) if component_path else None))==contracts['components'].get(args.booklet)
    selected=[];selected_data=[]
    canonical_bp=contracts['blueprints'][args.booklet]
    canonical_components=(contracts['components'].get(args.booklet) or {}).get('components',{})
    entries={e['id'] if isinstance(e,dict) else e:e if isinstance(e,dict) else {'id':e} for e in canonical_bp['groups']}
    def style_config(c):
        return {k:v for k,v in c.items() if k not in ('id','sidebar','numbering','number_start','new_page','start_on','use_measured','items')}
    def canonical_style(group):
        return {**canonical_bp.get('group_defaults',{}),**canonical_components.get(group['kind'],{}),**entries.get(group['id'],{})}
    for entry in bp['groups']:
        entry={'id':entry} if isinstance(entry,str) else entry;gid=entry['id']
        if gid not in groups:raise ValueError('Unknown group: '+gid)
        group=copy.deepcopy(groups[gid]);config={**bp.get('group_defaults',{}),**component_defaults.get(group['kind'],{}),**entry}
        config['use_measured']=(not args.recompose and 'items' not in config
            and json.loads(json.dumps(bp.get('page')))==canonical_bp.get('page')
            and json.loads(json.dumps(style_config(config)))==json.loads(json.dumps(style_config(canonical_style(group)))) )
        config['_refresh_furniture']=(bp.get('sidebar')!=canonical_bp.get('sidebar') or 'sidebar' in entry
            or 'header' in load(bp_path) or 'footer' in bp)
        if config.get('title') is not None:group['title']=config['title']
        if config.get('items') is not None:
            by_id={i['id']:i for i in group['items']}
            group['items']=[by_id[i] for i in config['items']]
        if gid in selected:raise ValueError('Duplicate group selection: '+gid)
        if config.get('start_on') in ('left','right'):
            wanted=0 if config['start_on']=='left' else 1
            if (len(layout.pages)+layout.start_page)%2!=wanted:
                layout.section=gid[0];layout.group=group;layout.gc=config;layout.new_page()

        if config.get('sidebar',bp.get('sidebar')) is not False:
            config['sidebar']={'text':metadata['sections'][gid[0]]['sidebar_label'],**(bp.get('sidebar') or {}),**(config.get('sidebar') or {})}
        # Facing reference pages always start on the left of a spread.
        if config.get('layout')=='facing_pages' and (len(layout.pages)+layout.start_page)%2==1:
            layout.section=gid[0];layout.group=group;layout.gc=config
            pn=len(layout.pages)+layout.start_page
            if pn==29 and pristine and not args.recompose:
                page=copy.deepcopy(ref.pages[('R',18)]);ref.resolved.update(ref.meta(page['commands']))
                layout.pages.append({'commands':page['commands'],'bands':[],'group_ids':[gid],'measured':True});layout.page=layout.pages[-1]
            else:
                layout.new_page();asset=metadata['assets'].get('reading_interleaf')
                if asset:layout.image({'asset':asset,'width':452.41,'height':708.96},layout.left,layout.width)
        # Question labels and cloze references follow the same current numbering.
        questions=[]
        def collect(obj):
            if isinstance(obj,dict):
                if 'options' in obj and not obj.get('is_example'):questions.append(obj)
                for k,v in obj.items():
                    if k!='options':collect(v)
            elif isinstance(obj,list):
                for v in obj:collect(v)
        collect(group['items'])
        mode=config.get('numbering',bp.get('numbering',{}).get('mode','continuous'))
        start=int(config.get('number_start',1)) if mode=='per_group' else layout.number
        mapping={}
        for i,q in enumerate(questions):
            previous=q.get('source_number')
            if mode!='source' and q.get('label') is None:
                q['source_number']=start+i
                if previous is not None:mapping[int(previous)]=start+i
        if group['kind']=='cloze':
            def rewrite(v):
                if isinstance(v,str):return re.sub(r'〔([0-9]+)(-[A-Za-z])?〕',lambda m:'〔'+str(mapping.get(int(m[1]),int(m[1])))+(m[2] or '')+'〕',v)
                if isinstance(v,list):return [rewrite(x) for x in v]
                if isinstance(v,dict):return {k:rewrite(x) for k,x in v.items()}
                return v
            group=rewrite(group)
        layout.render_group(group,config);selected.append(gid);selected_data.append(group)
    layout.decorate();body_pages=len(layout.pages)
    covers=ref.cover('L' if args.booklet=='listening' else 'V',body_pages) if bp.get('cover',True) else []
    pages=covers+layout.pages
    assets={}
    for slot,spec in json.loads((profile/'asset-bindings.json').read_text()).items():
        if 'metadata_pointer' in spec:name=pointer(metadata,spec['metadata_pointer'])
        else:
            try:name=pointer(load(content/spec['file']),spec['pointer'])
            except (FileNotFoundError,KeyError,IndexError,TypeError):continue
        path=(ROOT/'resources'/name).resolve()
        if path.is_file():assets[slot]=str(path)
    for asset in layout.assets:assets[asset]=str(out/asset)
    scene={'schema_version':1,'units':'bp','paper':{'width':595,'height':842},'sections':{'booklet':{'pages':[{'section_page':i+1,'commands':p['commands']} for i,p in enumerate(pages)]}}}
    resolved={'schema_version':1,'runs':ref.resolved,'asset_files':assets}
    (out/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,separators=(',',':'))+'\n')
    (out/'resolved.json').write_text(json.dumps(resolved,ensure_ascii=False,separators=(',',':'))+'\n')
    render(Namespace(resources=profile,scene=out/'scene.json',resolved=out/'resolved.json',sections='booklet',output_dir=out,compile=not args.no_compile,font_config=args.fonts,project_root=ROOT))
    inp=out/'inputs';inp.mkdir(exist_ok=True)
    for p in content.glob('*.yaml'):shutil.copyfile(p,inp/p.name)
    shutil.copyfile(bp_path,inp/'blueprint.yaml');shutil.copyfile(metadata_path,inp/'metadata.yaml')
    if component_path:shutil.copyfile(component_path,inp/'components.yaml')
    if args.fonts:
        font_config=Path(fonts.font_config_report['config'])
        shutil.copyfile(font_config,inp/'fonts.yaml')
    elif (inp/'fonts.yaml').exists():
        (inp/'fonts.yaml').unlink()
    licenses=out/'licenses';licenses.mkdir(exist_ok=True)
    for p in (ROOT/'resources/fallback').glob('LICENSE-*.txt'):shutil.copyfile(p,licenses/p.name)
    report={'status':'BUILT','paper':args.paper,'booklet':args.booklet,'renderer':'shared-component-scene','body_pages':body_pages,'page_count':len(pages),'original_pdf_read_at_build_time':False,'content_origin':'current YAML only','components':layout.component_audit,'compiled':not args.no_compile,'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inp.iterdir() if p.is_file()}}
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'semantic-ledger.json').write_text(json.dumps(ref.ledger,ensure_ascii=False,separators=(',',':'))+'\n')
    (out/'metadata-layout-report.json').write_text(json.dumps(ref.metadata_audit,ensure_ascii=False,indent=2)+'\n')
    (out/'selected-content.yaml').write_text(yaml.safe_dump({'schema_version':1,'groups':selected_data},sort_keys=False,allow_unicode=True))
    (out/'composition-font-usage.json').write_text(json.dumps({
        'schema_version':1,'description':'Glyphs requested during layout, including measurement-only text.',
        'fonts':{fid:sorted(codes) for fid,codes in fonts.resolver.resolved_codes.items()}
    },ensure_ascii=False,indent=2)+'\n')
    (out/'item-layout.json').write_text(json.dumps(layout.item_records,ensure_ascii=False,indent=2)+'\n')
    if not args.no_compile:
        target=ROOT/'output'/f'N1-{args.paper}-{args.booklet}.pdf';shutil.copyfile(out/'main.pdf',target);print('PDF:',target)
    print(json.dumps({'pages':len(pages),'components':layout.component_audit},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
