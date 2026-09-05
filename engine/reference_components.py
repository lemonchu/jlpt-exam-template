"""Measured component constraints: geometry and semantic field references only."""
from pathlib import Path
import json,copy,re
from semantic_bindings import shape,skeleton,field_value,chars_for,normal,CalibrationMismatch
from metadata_bindings import resolve as metadata_runs

class ReferenceComponents:
    def __init__(self,profile,metadata_path):
        self.profile=Path(profile);self.metadata_path=metadata_path
        self.layout=json.loads((self.profile/'layout.json').read_text())
        self.bindings=json.loads((self.profile/'body-bindings.json').read_text())
        self.components=json.loads((self.profile/'components.json').read_text())['groups']
        self.pages={(s,p['section_page']):p for s,section in self.layout['sections'].items() for p in section['pages']}
        self.run_specs={c['run_id']:c for p in self.pages.values() for c in p['commands'] if c['type']=='run'}
        capacity=self.profile/'glyph-capacities.json'
        self.glyph_capacities=json.loads(capacity.read_text())['widths'] if capacity.exists() else {}
        self.fonts=None
        self.metadata_audit=[]
        self.resolved={};self.ledger=[]
    def resolve_runs(self,group,run_ids):
        spec=self.components[group['id']];sec=spec['section'];gi=spec['group_index']
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
    def meta(self,commands,body_pages=None):
        runs=[c['run_id'] for c in commands if c['type']=='run' and c['run_id'] not in self.bindings['runs']]
        return metadata_runs(self.metadata_path,self.profile/'metadata-bindings.json',body_pages=body_pages,run_ids=runs)['runs']
    def _relocated_body(self,page,section,source_number,printed_page,group_id):
        """Move measured body geometry; the caller supplies fresh page furniture."""
        import yaml
        if isinstance(printed_page,bool) or not isinstance(printed_page,int) or printed_page<1:
            raise CalibrationMismatch('Printed page must be a positive integer')
        margins=(63.45,45.21) if section=='L' else (78.96,63.63)
        source_left=margins[0 if source_number%2 else 1]
        target_left=margins[0 if printed_page%2 else 1]
        dx=target_left-source_left
        # One scope preserves graphics-state changes shared by vector chunks.
        # Clip in source coordinates before moving to the target mirror margin.
        clip_left,clip_right=(0,595) if section=='L' else (29,565)
        height=self.layout['paper']['height']
        vectors='\n'.join(c['pdf'] for c in page['commands'] if c['type']=='vector')
        commands=[]
        if vectors:
            commands.append({'type':'vector','pdf':(
                f'q 1 0 0 1 {dx:.12g} 0 cm '
                f'{clip_left} {height-785:.12g} {clip_right-clip_left} 745 re W n\n'
                +vectors+'\nQ')})
        for source in page['commands']:
            if source['type']=='ink':commands.append(copy.deepcopy(source))
            elif source['type']=='image' or (source['type']=='run' and source['run_id'] in self.bindings['runs']):
                command=copy.deepcopy(source);command['x']+=dx;commands.append(command)
        bands=[]
        if section!='L':
            metadata=yaml.safe_load(Path(self.metadata_path).read_text())
            bands=[{'section':section,'text':metadata['sections'][section]['sidebar_label']}]
        return {'commands':commands,'bands':bands,'group_ids':[group_id],'measured_body':True}
    def take_page(self,group,page_info,printed_page,refresh_furniture=False):
        page=copy.deepcopy(self.pages[(group['id'][0],page_info['source_page'])])
        current,ledger=self.resolve_runs(group,self.body_runs(page))
        furniture=None
        if page_info['printed_page']==printed_page and not refresh_furniture:
            try:furniture=self.meta(page['commands'])
            except ValueError:pass
        if furniture is not None:
            current.update(furniture)
            result={'commands':page['commands'],'bands':[],'group_ids':[group['id']],'measured':True}
        else:
            result=self._relocated_body(page,group['id'][0],page_info['printed_page'],printed_page,group['id'])
        self.resolved.update(current);self.ledger+=ledger
        return result
    def take_group(self,group,printed_page,refresh_furniture=False):
        if group['id'] not in self.components:raise CalibrationMismatch('New question group')
        spec=self.components[group['id']];gi=spec['group_index'];sec=spec['section']
        expected=self.bindings['skeletons'][sec]['groups'][gi]
        if skeleton(group)!=expected:raise CalibrationMismatch('Question/block count changed')
        pages=[];pending={};ledger=[]
        for i,info in enumerate(spec['pages']):
            page=copy.deepcopy(self.pages[(sec,info['source_page'])]);rr,ll=self.resolve_runs(group,self.body_runs(page))
            pending.update(rr);ledger+=ll
            furniture=None
            if printed_page+i==info['printed_page'] and not refresh_furniture:
                try:furniture=self.meta(page['commands'])
                except ValueError:pass
            if furniture is not None:
                pending.update(furniture)
                pages.append({'commands':page['commands'],'bands':[],'group_ids':[group['id']],'measured':True})
            else:
                pages.append(self._relocated_body(page,sec,info['printed_page'],printed_page+i,group['id']))
        self.resolved.update(pending);self.ledger+=ledger
        return pages
    def heading(self,group,printed_page,left):
        if group['id'] not in self.components:raise CalibrationMismatch('New question heading')
        spec=self.components[group['id']];first=spec['pages'][0];page=self.pages[(group['id'][0],first['source_page'])]
        rr,ll=self.resolve_runs(group,spec['heading_runs'])
        source_left=(63.45 if first['printed_page']%2 else 45.21) if group['id'][0]=='L' else (78.96 if first['printed_page']%2 else 63.63)
        dx=left-source_left;bottom=spec['heading_end_top'];commands=[]
        for c in page['commands']:
            c=copy.deepcopy(c)
            if c['type']=='vector':
                c['pdf']=f'q 1 0 0 1 {dx} 0 cm {source_left-2} {842-bottom} 520 {bottom-40} re W n\n'+c['pdf']+'\nQ'
                commands.append(c)
            elif c['type']=='run' and c['run_id'] in rr:c['x']+=dx;commands.append(c)
            elif c['type']=='ink':commands.append(c)
        self.resolved.update(rr);self.ledger+=ll
        return commands,spec
    def slice_item(self,group,item_index,printed_page,left):
        """Reuse one measured item, resolving every glyph from the current item.

        The item must occupy a contiguous vertical interval on one source page.
        Surrounding body baselines delimit its vector clip; the next item's
        first prompt baseline is returned in top-origin bp for flowing content.
        No surrounding item or page furniture is copied into the result.
        """
        try:
            spec=self.components[group['id']];sec=spec['section'];gi=spec['group_index']
            if isinstance(item_index,bool) or not isinstance(item_index,int) or item_index<0:
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
        if not isinstance(printed_page,int) or printed_page<1:
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
        source_left=((63.45 if source_info['printed_page']%2 else 45.21) if sec=='L'
                     else (78.96 if source_info['printed_page']%2 else 63.63))
        dx=float(left)-source_left
        # Keep all vector chunks in one graphics-state scope: later chunks can
        # inherit the original line width/dash settings from the first chunk.
        vectors='\n'.join(c['pdf'] for c in page['commands'] if c['type']=='vector')
        clip_left=source_left-2
        commands=[{'type':'vector','pdf':(
            f'q 1 0 0 1 {dx:.12g} 0 cm '
            f'{clip_left:.12g} {page_height-clip_bottom:.12g} '
            f'{page_width-source_left:.12g} {clip_bottom-clip_top:.12g} re W n\n'
            +vectors+'\nQ')}]
        rr,ll=self.resolve_runs(group,[c['run_id'] for c in current])
        for source in page['commands']:
            if source['type']=='ink':commands.append(copy.deepcopy(source))
            elif source['type']=='run' and source['run_id'] in selected:
                command=copy.deepcopy(source);command['x']+=dx;commands.append(command)
        self.resolved.update(rr);self.ledger+=ll
        return commands,next_body_baseline
    def cover(self,section,body_pages):
        pages=[]
        for i in (1,2):
            page=copy.deepcopy(self.pages[(section,i)])
            if self.fonts is not None:
                from metadata_components import resolve_metadata_components
                page['commands'],runs,audit=resolve_metadata_components(self.profile,self.metadata_path,page['commands'],self.fonts,body_pages=body_pages)
                self.resolved.update(runs);self.metadata_audit.append(audit)
            else:self.resolved.update(self.meta(page['commands'],body_pages))
            pages.append(page)
        return pages
