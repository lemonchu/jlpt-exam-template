"""Measured component constraints: geometry and semantic field references only."""
import json,copy
from semantic_bindings import shape,skeleton,layout_fingerprint,field_value,chars_for,normal,CalibrationMismatch
from metadata_bindings import resolve_loaded
from geometry import body_grid
from scene import place_fragment
from cover_templates import CoverTemplates


def _integer_at_least(value, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


class ReferenceComponents(CoverTemplates):
    def __init__(self,profile,metadata_path):
        super().__init__(profile,metadata_path)
        self.asset_bindings=json.loads((self.profile/'asset-bindings.json').read_text())
        self.metadata_bindings=json.loads((self.profile/'metadata-bindings.json').read_text())
        self.layout=json.loads((self.profile/'layout.json').read_text())
        self.bindings=json.loads((self.profile/'body-bindings.json').read_text())
        self.components=json.loads((self.profile/'components.json').read_text())['groups']
        self.pages={(s,p['section_page']):p for s,section in self.layout['sections'].items() for p in section['pages']}
        self.run_specs={c['run_id']:c for p in self.pages.values() for c in p['commands'] if c['type']=='run'}
        capacity=self.profile/'glyph-capacities.json'
        self.glyph_capacities=json.loads(capacity.read_text())['widths'] if capacity.exists() else {}
        contracts=self.profile/'composition-contracts.json'
        self.contracts=json.loads(contracts.read_text()) if contracts.exists() else {}
        self.layout_contracts=self.contracts.get('content_layout_sha256',{})
        if not isinstance(self.layout_contracts,dict):raise ValueError('Invalid content layout contracts')
        missing=set(self.components)-set(self.layout_contracts)
        if missing:raise ValueError('Missing content layout contracts: '+', '.join(sorted(missing)))
    def require_layout_compatibility(self,group):
        expected=self.layout_contracts.get(group['id'])
        if expected is None:raise CalibrationMismatch('Measured component has no content layout contract')
        if layout_fingerprint(group)!=expected:
            raise CalibrationMismatch('Content layout attributes changed')
    def resolve_runs(self,group,run_ids):
        spec=self.components[group['id']];gi=spec['group_index']
        data={'groups':[None]*(gi+1)};data['groups'][gi]=group
        needed={ref['field'] for rid in run_ids for g in self.bindings['runs'][rid]['glyphs'] for ref in g['refs']}
        values={}
        for field in needed:
            f=self.bindings['fields'][field]
            try:value=field_value(f,data)
            except (KeyError,IndexError,TypeError) as e:raise CalibrationMismatch(f'{field}: component structure changed') from e
            if shape(value)!=f['shape']:raise CalibrationMismatch(f'{field}: component capacity changed')
            values[field]=chars_for(value,f['role'])
        result={};ledger=[]
        for rid in run_ids:
            glyphs=[]
            for i,g in enumerate(self.bindings['runs'][rid]['glyphs']):
                refs=g['refs'];raw=[values[t['field']][t['char']] for t in refs];fmt=g['formatter']
                if fmt=='identity':text=raw[0]
                elif fmt=='ascii':text=normal(raw[0])
                elif fmt=='fullwidth':text=''.join(chr(ord(c)+0xFEE0) if '!'<=c<='~' else c for c in normal(raw[0]))
                elif fmt=='circled':
                    n=normal(raw[0]);text=chr(0x2460+int(n)-1) if n.isdigit() and 1<=int(n)<=9 else raw[0]
                elif fmt=='ring':
                    if raw[0] not in '①②③④⑤⑥⑦⑧⑨':raise CalibrationMismatch('Circled mark changed')
                    text='○'
                elif fmt=='combined':
                    text=''.join(normal(c)[t['part']] for c,t in zip(raw,refs))
                    if text!='()':raise CalibrationMismatch('Combined delimiter changed')
                    text='( )'
                else:raise ValueError(fmt)
                glyphs.append(text);ledger.append({'run':rid,'index':i,'refs':refs,'text':text})
            if self.fonts is not None and rid in self.glyph_capacities:
                command=self.run_specs[rid]
                for text,form,expected in zip(glyphs,command.get('forms',['normal']*len(glyphs)),self.glyph_capacities[rid]):
                    fid,code=self.fonts.resolver.resolve(command['font'],text,form)
                    face=self.fonts.faces[fid];advance=face.widths[code]/face.upm
                    if abs(advance-expected)>.002:raise CalibrationMismatch(f'{rid}: current glyph width no longer fits the measured advance')
            result[rid]={'glyphs':glyphs}
        return result,ledger
    def body_runs(self,page):return [c['run_id'] for c in page['commands'] if c['type']=='run' and c['run_id'] in self.bindings['runs']]
    def meta(self,commands):
        runs=[c['run_id'] for c in commands if c['type']=='run' and c['run_id'] not in self.bindings['runs']]
        return resolve_loaded(self.metadata,self.metadata_bindings,
                              self.metadata_path.name,run_ids=runs)['runs']
    def _relocated_body(self,page,section,source_number,printed_page,group_id):
        """Move measured body geometry; the caller supplies fresh page furniture."""
        if not _integer_at_least(printed_page,1):
            raise CalibrationMismatch('Printed page must be a positive integer')
        source_left=body_grid(section).left(source_number)
        target_left=body_grid(section).left(printed_page)
        clip_left,clip_right=(0,595) if section=='L' else (29,565)
        commands=place_fragment(
            page['commands'],source_origin=(source_left,0),target_origin=(target_left,0),
            page_height=self.layout['paper']['height'],clip=(clip_left,40,clip_right-clip_left,745),
            run_ids=self.bindings['runs'],include_images=True,
        )
        bands=[]
        if section!='L':
            bands=[{'section':section,'text':self.metadata['sections'][section]['sidebar_label']}]
        return {'commands':commands,'bands':bands,'group_ids':[group_id],'measured_body':True}
    def _prepare_page(self,group,page_info,printed_page,refresh_furniture):
        section=group['id'][0]
        page=copy.deepcopy(self.pages[(section,page_info['source_page'])])
        resolved,ledger=self.resolve_runs(group,self.body_runs(page))
        furniture=None
        if page_info['printed_page']==printed_page and not refresh_furniture:
            try:furniture=self.meta(page['commands'])
            except ValueError:pass
        if furniture is not None:
            resolved.update(furniture)
            result={'commands':page['commands'],'bands':[],'group_ids':[group['id']],'measured':True}
        else:
            result=self._relocated_body(page,section,page_info['printed_page'],printed_page,group['id'])
        return result,resolved,ledger
    def take_page(self,group,page_info,printed_page,refresh_furniture=False):
        self.require_layout_compatibility(group)
        result,current,ledger=self._prepare_page(group,page_info,printed_page,refresh_furniture)
        self.resolved.update(current);self.ledger+=ledger
        return result
    def take_group(self,group,printed_page,refresh_furniture=False):
        if group['id'] not in self.components:raise CalibrationMismatch('New question group')
        self.require_layout_compatibility(group)
        spec=self.components[group['id']];gi=spec['group_index'];sec=spec['section']
        expected=self.bindings['skeletons'][sec]['groups'][gi]
        if skeleton(group)!=expected:raise CalibrationMismatch('Question/block count changed')
        pages=[];pending={};ledger=[]
        for i,info in enumerate(spec['pages']):
            page,rr,ll=self._prepare_page(group,info,printed_page+i,refresh_furniture)
            pending.update(rr);ledger+=ll
            pages.append(page)
        self.resolved.update(pending);self.ledger+=ledger
        return pages
    def heading(self,group,left):
        if group['id'] not in self.components:raise CalibrationMismatch('New question heading')
        spec=self.components[group['id']];first=spec['pages'][0];page=self.pages[(group['id'][0],first['source_page'])]
        rr,ll=self.resolve_runs(group,spec['heading_runs'])
        source_left=body_grid(group['id'][0]).left(first['printed_page'])
        commands=place_fragment(
            page['commands'],source_origin=(source_left,0),target_origin=(left,0),
            page_height=self.layout['paper']['height'],
            clip=(source_left-2,40,520,spec['heading_end_top']-40),run_ids=rr,
        )
        self.resolved.update(rr);self.ledger+=ll
        return commands,spec
    def slice_item(self,group,item_index,printed_page,left):
        """Reuse one measured item, resolving every glyph from the current item.

        The item must occupy a contiguous vertical interval on one source page.
        Surrounding body baselines delimit its vector clip; the next item's
        first prompt baseline is returned in top-origin bp for flowing content.
        No surrounding item or page furniture is copied into the result.
        """
        self.require_layout_compatibility(group)
        try:
            spec=self.components[group['id']];sec=spec['section'];gi=spec['group_index']
            if not _integer_at_least(item_index,0):
                raise CalibrationMismatch('Item index must be a nonnegative integer')
            item=group['items'][item_index]
            expected=self.bindings['skeletons'][sec]['groups'][gi]['items'][item_index]
        except (KeyError,IndexError,TypeError) as e:
            raise CalibrationMismatch('Measured item is absent or has changed structure') from e
        if skeleton(item)!=expected:raise CalibrationMismatch('Measured item structure changed')
        prefix=f'/groups/{gi}/items/{item_index}/'
        selected=set()
        run_fields={}
        for rid,binding in self.bindings['runs'].items():
            if not rid.startswith(sec+'-'):continue
            fields=[self.bindings['fields'][ref['field']]
                    for glyph in binding['glyphs'] for ref in glyph['refs']]
            run_fields[rid]=fields
            belongs=[f['file']==sec+'.yaml' and f['pointer'].startswith(prefix) for f in fields]
            if any(belongs):
                if not all(belongs):raise CalibrationMismatch('Measured run mixes multiple items')
                selected.add(rid)
        if not selected:raise CalibrationMismatch('Measured item has no text runs')
        locations=[]
        for (section,source_page),page in self.pages.items():
            if section!=sec:continue
            ids={c['run_id'] for c in page['commands'] if c['type']=='run'}
            if ids&selected:locations.append((source_page,page,ids&selected))
        if len(locations)!=1 or locations[0][2]!=selected:
            raise CalibrationMismatch('Measured item must be entirely on one page')
        source_page,page,_=locations[0]
        source_info=next((p for p in spec['pages'] if p['source_page']==source_page),None)
        if source_info is None:raise CalibrationMismatch('Measured item page is outside its group')
        if not _integer_at_least(printed_page,1):
            raise CalibrationMismatch('Printed page must be a positive integer')
        page_height=self.layout['paper']['height'];page_width=self.layout['paper']['width']
        body=[c for c in page['commands'] if c['type']=='run' and c['run_id'] in run_fields]
        current=[c for c in body if c['run_id'] in selected]
        first=min(page_height-c['y'] for c in current)
        last=max(page_height-c['y'] for c in current)
        surrounding=[c for c in body if c['run_id'] not in selected]
        if any(first<=page_height-c['y']<=last for c in surrounding):
            raise CalibrationMismatch('Measured item overlaps another body component')
        preceding=[page_height-c['y'] for c in surrounding if page_height-c['y']<first]
        following=[c for c in surrounding if page_height-c['y']>last]
        if not following:
            raise CalibrationMismatch('Measured item has no following body baseline on this page')
        after=min(page_height-c['y'] for c in following)
        clip_top=(max(preceding)+first)/2 if preceding else max(0,first-max(c['sy'] for c in current)*2)
        clip_bottom=(last+after)/2
        # The question number is usually a little above the actual first line.
        # Return the prompt baseline, without that typographic number offset.
        next_prefix=f'/groups/{gi}/items/{item_index+1}/'
        next_runs=[c for c in following if any(f['pointer'].startswith(next_prefix)
                    for f in run_fields[c['run_id']])]
        if not next_runs:raise CalibrationMismatch('Following measured item is not contiguous')
        prompts=[c for c in next_runs if any(f['pointer']==next_prefix+'prompt' and f['role']=='base'
                    for f in run_fields[c['run_id']])]
        if not prompts:
            prompts=[c for c in next_runs if any(f['role']=='base' and not f['pointer'].endswith('/source_number')
                     for f in run_fields[c['run_id']])]
        if not prompts:raise CalibrationMismatch('Following item has no body text baseline')
        next_body_baseline=min(page_height-c['y'] for c in prompts)
        source_left=body_grid(sec).left(source_info['printed_page'])
        commands=place_fragment(
            page['commands'],source_origin=(source_left,clip_top),target_origin=(float(left),clip_top),
            page_height=page_height,
            clip=(source_left-2,clip_top,page_width-source_left,clip_bottom-clip_top),run_ids=selected,
        )
        rr,ll=self.resolve_runs(group,[c['run_id'] for c in current])
        self.resolved.update(rr);self.ledger+=ll
        return commands,next_body_baseline
