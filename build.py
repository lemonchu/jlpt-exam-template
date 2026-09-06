#!/usr/bin/env python3
"""Compose every exam with shared measured N1 components and one XeLaTeX renderer."""
from pathlib import Path
from argparse import ArgumentParser,Namespace
import json,copy,re,shutil,sys,hashlib
import yaml
ROOT=Path(__file__).resolve().parent
CONTENT_FIELDS={'title','instruction','prompt','text','label','options','rows'}
CONTENT_CONTAINERS={'items','questions','stimulus','blocks'}
NUMBERING_MODES=('continuous','source','per_group')
PAGE_SIDES={'left':0,'right':1}
GROUP_BOOLEAN_FIELDS=(
    'new_page','passages_new_page','questions_new_page','example_separate_page',
)
STYLE_CONTROL_FIELDS={
    'id','sidebar','numbering','number_start','new_page','start_on','use_measured','items',
}
HEADING_STYLE_FIELDS=(
    'heading_layout','heading_size','instruction_font_size','instruction_line_height',
    'instruction_width',
)
BOOKLET_SECTIONS={'written':{'V','G','R'},'listening':{'L'}}
sys.path.insert(0,str(ROOT/'engine'))
from component_fonts import ComponentFonts
from component_layout import ComponentLayout
from reference_components import ReferenceComponents
from calibrated_renderer import render
from semantic_bindings import iter_questions,pointer

def load(p):
    d=yaml.safe_load(Path(p).read_text(encoding='utf-8'))
    if not isinstance(d,dict):raise ValueError(f'{p}: expected YAML mapping')
    return d

def require_schema_v1(document,path):
    version=document.get('schema_version')
    if type(version) is not int or version!=1:raise ValueError(f'{path}: schema_version must be integer 1')
    return document

def require_number(value,message):
    """Return a finite numeric value while treating YAML booleans as booleans."""
    if isinstance(value,bool):raise ValueError(message)
    try:number=float(value)
    except (TypeError,ValueError) as error:raise ValueError(message) from error
    if not number==number or abs(number)==float('inf'):raise ValueError(message)
    return number

def require_positive_integer(value,message):
    if isinstance(value,bool) or not isinstance(value,int) or value<1:raise ValueError(message)
    return value

def require_boolean(value,message):
    if not isinstance(value,bool):raise ValueError(message)
    return value

def validate_blueprint(blueprint,path):
    if not isinstance(blueprint.get('groups'),list):raise ValueError(f'{path}: groups must be a list')
    page=blueprint.get('page',{})
    if not isinstance(page,dict):raise ValueError(f'{path}: page must be a mapping')
    dimensions_message=f'{path}: page width and height must be numbers'
    width=require_number(page.get('width',595),dimensions_message)
    height=require_number(page.get('height',842),dimensions_message)
    if abs(width-595)>1e-6 or abs(height-842)>1e-6:
        raise ValueError(f'{path}: the calibrated XeLaTeX renderer supports only 595 x 842 bp pages')
    numbering=blueprint.get('numbering',{})
    if not isinstance(numbering,dict):raise ValueError(f'{path}: numbering must be a mapping')
    if numbering.get('mode','continuous') not in NUMBERING_MODES:
        raise ValueError(f'{path}: unknown numbering mode {numbering.get("mode")!r}')
    if 'start' in numbering:
        require_positive_integer(numbering['start'],f'{path}: numbering.start must be a positive integer')
    if 'page_number_start' in blueprint:
        require_positive_integer(blueprint['page_number_start'],f'{path}: page_number_start must be a positive integer')
    if 'cover' in blueprint:
        require_boolean(blueprint['cover'],f'{path}: cover must be true or false')
    return blueprint

def validate_group_config(config):
    """Validate values that control numbering and page flow before layout."""
    if 'number_start' in config:
        require_positive_integer(config['number_start'],'number_start must be a positive integer')
    if 'items_per_page' in config:
        require_positive_integer(config['items_per_page'],'items_per_page must be a positive integer')
    for name in GROUP_BOOLEAN_FIELDS:
        if name in config:require_boolean(config[name],f'{name} must be true or false')
    start_on=config.get('start_on')
    if start_on is not None and start_on not in PAGE_SIDES:
        raise ValueError('start_on must be left or right')
    return config

def canonicalize_config(value):
    """Match YAML mappings to the JSON-backed composition contracts."""
    return json.loads(json.dumps(value))

def parse_args(argv=None):
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--paper',default='paper-a')
    parser.add_argument('--booklet',choices=['written','listening'],default='written')
    parser.add_argument('--blueprint',type=Path);parser.add_argument('--metadata',type=Path)
    parser.add_argument('--fonts',type=Path,default=ROOT/'fonts.yaml' if (ROOT/'fonts.yaml').is_file() else None,
                        help='Complete-font configuration; defaults to project fonts.yaml when present')
    parser.add_argument('--no-compile',action='store_true')
    parser.add_argument('--recompose',action='store_true',help='Recompute every variable content component using the same standard typography')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.paper):parser.error('Invalid paper folder name')
    return args

def load_content(content):
    groups={};documents={}
    for section in ('V','G','R','L'):
        path=content/f'{section}.yaml'
        if not path.exists():continue
        document=require_schema_v1(load(path),path);documents[path.name]=document
        if document.get('section')!=section:raise ValueError(f'{path}: section must be {section}')
        if not isinstance(document.get('groups'),list):raise ValueError(f'{path}: groups must be a list')
        for group in document['groups']:
            group_id=group.get('id') if isinstance(group,dict) else None
            if not isinstance(group_id,str) or not group_id.startswith(section):
                raise ValueError(f'{path}: every group id must begin with {section}')
            if group_id in groups:raise ValueError(f'Duplicate group id: {group_id}')
            groups[group_id]=group
    return groups,documents

def select_items(group,item_ids):
    items=group.get('items',[])
    if not isinstance(items,list):raise ValueError(f'Items in group {group["id"]} must be a list')
    ids=[item.get('id') if isinstance(item,dict) else None for item in items]
    if any(not isinstance(item_id,str) or not item_id for item_id in ids):raise ValueError(f'Every item in group {group["id"]} must have an id')
    by_id=dict(zip(ids,items))
    if len(by_id)!=len(items):raise ValueError(f'Duplicate item id in group {group["id"]}')
    if item_ids is None:return group
    if not isinstance(item_ids,list):raise ValueError('Blueprint items must be a list of item ids')
    if len(item_ids)!=len(set(item_ids)):raise ValueError(f'Duplicate item selection in group {group["id"]}')
    missing=[item_id for item_id in item_ids if item_id not in by_id]
    if missing:raise ValueError(f'Unknown item in group {group["id"]}: {missing[0]}')
    group['items']=[by_id[item_id] for item_id in item_ids]
    return group

def renumber_group(group,config,default_mode,next_number):
    """Apply one numbering policy and keep cloze references in sync."""
    mode=config.get('numbering',default_mode)
    if mode not in NUMBERING_MODES:raise ValueError(f'Unknown numbering mode {mode!r}')
    start=int(config.get('number_start',1)) if mode=='per_group' else next_number
    mapping={}
    for index,question in enumerate(iter_questions(group.get('items',[]))):
        previous=question.get('source_number')
        if mode!='source' and question.get('label') is None:
            question['source_number']=start+index
            if previous is not None:mapping[int(previous)]=start+index
    if group.get('kind')!='cloze':return group
    def rewrite_text(value):
        if isinstance(value,str):return re.sub(r'〔([0-9]+)(-[A-Za-z])?〕',lambda m:'〔'+str(mapping.get(int(m[1]),int(m[1])))+(m[2] or '')+'〕',value)
        if isinstance(value,list):return [rewrite_text(child) for child in value]
        if isinstance(value,dict):return {key:rewrite_text(child) for key,child in value.items()}
        return value
    def rewrite_content(value):
        if isinstance(value,list):return [rewrite_content(child) for child in value]
        if not isinstance(value,dict):return value
        return {key:(rewrite_text(child) if key in CONTENT_FIELDS else
                     rewrite_content(child) if key in CONTENT_CONTAINERS else child)
                for key,child in value.items()}
    return rewrite_content(group)

def resolve_assets(profile,metadata,content_files,layout,out):
    assets={};resources=(ROOT/'resources').resolve()
    for slot,spec in json.loads((profile/'asset-bindings.json').read_text()).items():
        if 'metadata_pointer' in spec:name=pointer(metadata,spec['metadata_pointer'])
        else:
            try:name=pointer(content_files[spec['file']],spec['pointer'])
            except (KeyError,IndexError,TypeError):continue
        path=(resources/name).resolve()
        if not path.is_relative_to(resources):raise ValueError(f'Unsafe asset path: {name}')
        if path.is_file():assets[slot]=str(path)
    for asset in layout.assets:assets[asset]=str(out/asset)
    return assets

def printed_page(layout):
    """Return the number of the page that would be created next/currently."""
    return len(layout.pages)+layout.start_page

def starts_on(layout,side):
    """Whether the current printed-page position is on the requested side."""
    return printed_page(layout)%2==PAGE_SIDES[side]

def style_config(config):
    """Keep only values that determine reusable measured component geometry."""
    return {key:value for key,value in config.items() if key not in STYLE_CONTROL_FIELDS}

def prepare_group(source_group,entry,*,blueprint,component_defaults,
                  canonical_blueprint,canonical_components,canonical_entries,
                  page_is_canonical,recompose,blueprint_has_header):
    """Copy one content group and derive all renderer policy flags for it."""
    group=copy.deepcopy(source_group)
    config={
        **blueprint.get('group_defaults',{}),
        **component_defaults.get(group['kind'],{}),
        **entry,
    }
    validate_group_config(config)
    canonical_style={
        **canonical_blueprint.get('group_defaults',{}),
        **canonical_components.get(group['kind'],{}),
        **canonical_entries.get(group['id'],{}),
    }
    config['use_measured']=(
        not recompose and 'items' not in config and page_is_canonical
        and canonicalize_config(style_config(config))
            ==canonicalize_config(style_config(canonical_style))
    )
    config['_use_measured_heading']=(
        not recompose
        and all(config.get(key)==canonical_style.get(key) for key in HEADING_STYLE_FIELDS)
    )
    config['_use_measured_example']=config['use_measured']
    config['_refresh_furniture']=(
        blueprint.get('sidebar')!=canonical_blueprint.get('sidebar')
        or 'sidebar' in entry or blueprint_has_header or 'footer' in blueprint
    )
    if config.get('title') is not None:group['title']=config['title']
    select_items(group,config.get('items'))
    return group,config

def use_group_layout(layout,group,config):
    """Make a group current before inserting a page outside render_group()."""
    layout.section=group['id'][0];layout.group=group;layout.gc=config

def insert_facing_interleaf(layout,reference,metadata,group,config,*,pristine,recompose):
    """Align facing-page material, preserving the one calibrated reference page."""
    if config.get('layout')!='facing_pages' or starts_on(layout,'left'):return
    use_group_layout(layout,group,config)
    page_number=printed_page(layout)
    if page_number==29 and pristine and not recompose:
        page=copy.deepcopy(reference.pages[('R',18)])
        reference.resolved.update(reference.meta(page['commands']))
        layout.pages.append({
            'commands':page['commands'],'bands':[],
            'group_ids':[group['id']],'measured':True,
        })
        layout.page=layout.pages[-1]
        return
    layout.new_page()
    asset=metadata['assets'].get('reading_interleaf')
    if asset:layout.image({'asset':asset,'width':452.41,'height':708.96},layout.left,layout.width)

def compose_groups(*,blueprint,groups,component_defaults,contracts,layout,reference,
                   metadata,booklet,recompose,pristine,blueprint_has_header):
    """Compose the blueprint's ordered groups and return their selected content."""
    canonical_blueprint=contracts['blueprints'][booklet]
    canonical_components=(contracts['components'].get(booklet) or {}).get('components',{})
    canonical_entries={
        item['id'] if isinstance(item,dict) else item:
            item if isinstance(item,dict) else {'id':item}
        for item in canonical_blueprint['groups']
    }
    page_is_canonical=(
        canonicalize_config(blueprint.get('page'))==canonical_blueprint.get('page')
    )
    default_numbering=blueprint.get('numbering',{}).get('mode','continuous')
    selected=set();selected_data=[]
    for raw_entry in blueprint['groups']:
        entry={'id':raw_entry} if isinstance(raw_entry,str) else raw_entry
        group_id=entry['id']
        if group_id not in groups:raise ValueError('Unknown group: '+group_id)
        if group_id[:1] not in BOOKLET_SECTIONS[booklet]:
            raise ValueError(f'Group {group_id} does not belong in the {booklet} booklet')
        group,config=prepare_group(
            groups[group_id],entry,blueprint=blueprint,
            component_defaults=component_defaults,
            canonical_blueprint=canonical_blueprint,
            canonical_components=canonical_components,
            canonical_entries=canonical_entries,
            page_is_canonical=page_is_canonical,recompose=recompose,
            blueprint_has_header=blueprint_has_header,
        )
        if group_id in selected:raise ValueError('Duplicate group selection: '+group_id)
        start_on=config.get('start_on')
        if start_on and not starts_on(layout,start_on):
            use_group_layout(layout,group,config);layout.new_page()
        if config.get('sidebar',blueprint.get('sidebar')) is not False:
            config['sidebar']={
                'text':metadata['sections'][group_id[0]]['sidebar_label'],
                **(blueprint.get('sidebar') or {}),**(config.get('sidebar') or {}),
            }
        insert_facing_interleaf(
            layout,reference,metadata,group,config,
            pristine=pristine,recompose=recompose,
        )
        group=renumber_group(group,config,default_numbering,layout.number)
        layout.render_group(group,config)
        selected.add(group_id);selected_data.append(group)
    layout.decorate()
    return selected_data

def write_json(path,value,*,indent=None):
    options={'ensure_ascii':False}
    if indent is None:options['separators']=(',',':')
    else:options['indent']=indent
    path.write_text(json.dumps(value,**options)+'\n')

def write_scene_inputs(out,pages,resolved_runs,assets):
    scene={
        'schema_version':1,
        'units':'bp',
        'paper':{'width':595,'height':842},
        'sections':{'booklet':{'pages':[
            {'section_page':index+1,'commands':page['commands']}
            for index,page in enumerate(pages)
        ]}},
    }
    resolved={'schema_version':1,'runs':resolved_runs,'asset_files':assets}
    write_json(out/'scene.json',scene)
    write_json(out/'resolved.json',resolved)

def archive_inputs(out,content,blueprint_path,metadata_path,component_path,font_config):
    """Snapshot build inputs and remove YAML snapshots no longer in use."""
    destination=out/'inputs';destination.mkdir(exist_ok=True)
    snapshots=[(path,path.name) for path in sorted(content.glob('*.yaml'))]
    snapshots.extend(((blueprint_path,'blueprint.yaml'),(metadata_path,'metadata.yaml')))
    if component_path:snapshots.append((component_path,'components.yaml'))
    if font_config:snapshots.append((Path(font_config),'fonts.yaml'))
    # Explicit build inputs win over same-named content files (notably metadata.yaml).
    snapshot_by_name={name:source for source,name in snapshots}
    for name,source in snapshot_by_name.items():
        target=destination/name
        if source.resolve()!=target.resolve():shutil.copyfile(source,target)
    for stale in destination.glob('*.yaml'):
        if stale.name not in snapshot_by_name:stale.unlink()
    return destination

def write_build_outputs(*,out,args,body_pages,pages,layout,reference,fonts,inputs,selected_data):
    report={
        'status':'BUILT','paper':args.paper,'booklet':args.booklet,
        'renderer':'shared-component-scene','body_pages':body_pages,
        'page_count':len(pages),'original_pdf_read_at_build_time':False,
        'content_origin':'current YAML only','components':layout.component_audit,
        'compiled':not args.no_compile,
        'inputs':{
            path.name:hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(inputs.iterdir()) if path.is_file()
        },
    }
    write_json(out/'build-report.json',report,indent=2)
    write_json(out/'semantic-ledger.json',reference.ledger)
    write_json(out/'metadata-layout-report.json',reference.metadata_audit,indent=2)
    (out/'selected-content.yaml').write_text(yaml.safe_dump(
        {'schema_version':1,'groups':selected_data},sort_keys=False,allow_unicode=True,
    ))
    write_json(out/'composition-font-usage.json',{
        'schema_version':1,
        'description':'Glyphs requested during layout, including measurement-only text.',
        'fonts':{
            font_id:sorted(codes)
            for font_id,codes in fonts.resolver.resolved_codes.items()
        },
    },indent=2)
    write_json(out/'item-layout.json',layout.item_records,indent=2)

def main():
    args=parse_args()
    content=ROOT/'content'/args.paper;bp_path=args.blueprint or ROOT/'blueprints'/f'{args.booklet}.yaml'
    bp=validate_blueprint(require_schema_v1(load(bp_path),bp_path),bp_path)
    source_blueprint=canonicalize_config(bp)
    blueprint_has_header='header' in bp
    metadata_path=args.metadata or (content/'metadata.yaml' if (content/'metadata.yaml').exists() else ROOT/'content/common/metadata.yaml');metadata=require_schema_v1(load(metadata_path),metadata_path)
    if metadata.get('schema_kind')!='exam_metadata':raise ValueError(f'{metadata_path}: schema_kind must be exam_metadata')
    groups,content_files=load_content(content)
    component_path=bp_path.parent/bp['components_file'] if bp.get('components_file') else None
    component_data=load(component_path) if component_path else None
    component_defaults=component_data.get('components',{}) if component_data else {}
    bp.setdefault('header',metadata['booklets'][args.booklet]['subject_ja'])
    profile=ROOT/'profiles/n1-original';ref=ReferenceComponents(profile,metadata_path)
    out=ROOT/'output'/f'{args.paper}-{args.booklet}';out.mkdir(parents=True,exist_ok=True)
    for generated_dir in ('assets','licenses'):shutil.rmtree(out/generated_dir,ignore_errors=True)
    fonts=ComponentFonts(profile,args.fonts,ROOT);ref.fonts=fonts;layout=ComponentLayout(fonts,bp,ROOT/'resources',out,ref)
    contracts=ref.contracts
    pristine=(source_blueprint==contracts['blueprints'][args.booklet]
              and canonicalize_config(component_data)==contracts['components'].get(args.booklet))
    selected_data=compose_groups(
        blueprint=bp,groups=groups,component_defaults=component_defaults,
        contracts=contracts,layout=layout,reference=ref,metadata=metadata,
        booklet=args.booklet,recompose=args.recompose,pristine=pristine,
        blueprint_has_header=blueprint_has_header,
    )
    body_pages=len(layout.pages)
    covers=ref.cover('L' if args.booklet=='listening' else 'V',body_pages) if bp.get('cover',True) else []
    pages=covers+layout.pages
    assets=resolve_assets(profile,metadata,content_files,layout,out)
    write_scene_inputs(out,pages,ref.resolved,assets)
    render(Namespace(resources=profile,scene=out/'scene.json',resolved=out/'resolved.json',sections='booklet',output_dir=out,compile=not args.no_compile,font_config=args.fonts,project_root=ROOT))
    font_config=fonts.font_config_report['config'] if args.fonts else None
    inputs=archive_inputs(out,content,bp_path,metadata_path,component_path,font_config)
    write_build_outputs(out=out,args=args,body_pages=body_pages,pages=pages,layout=layout,
                        reference=ref,fonts=fonts,inputs=inputs,selected_data=selected_data)
    if not args.no_compile:
        target=ROOT/'output'/f'N1-{args.paper}-{args.booklet}.pdf';shutil.copyfile(out/'main.pdf',target);print('PDF:',target)
    print(json.dumps({'pages':len(pages),'components':layout.component_audit},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
