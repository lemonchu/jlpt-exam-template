"""Measured component constraints: geometry and semantic field references only."""
from pathlib import Path
import json,copy,re
from semantic_bindings import shape,skeleton,layout_fingerprint,field_value,chars_for,normal,CalibrationMismatch
from metadata_bindings import load_metadata, resolve_loaded

BODY_MARGINS = {'L': (63.45, 45.21), 'written': (78.96, 63.63)}


def _integer_at_least(value, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _body_left(section, printed_page):
    margins = BODY_MARGINS['L' if section == 'L' else 'written']
    return margins[0 if printed_page % 2 else 1]


class ReferenceComponents:
    def __init__(self,profile,metadata_path):
        self.profile=Path(profile);self.metadata_path=Path(metadata_path)
        self.metadata_bindings=json.loads((self.profile/'metadata-bindings.json').read_text())
        self.metadata=load_metadata(self.metadata_path,self.metadata_bindings)
        self._metadata_cache={None:self.metadata}
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
        self.fonts=None
        self.metadata_audit=[]
        self.resolved={};self.ledger=[]
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
    def meta(self,commands,body_pages=None):
        runs=[c['run_id'] for c in commands if c['type']=='run' and c['run_id'] not in self.bindings['runs']]
        if body_pages not in self._metadata_cache:
            self._metadata_cache[body_pages]=load_metadata(self.metadata_path,self.metadata_bindings,body_pages)
        return resolve_loaded(self._metadata_cache[body_pages],self.metadata_bindings,
                              self.metadata_path.name,run_ids=runs)['runs']
    def _relocated_body(self,page,section,source_number,printed_page,group_id):
        """Move measured body geometry; the caller supplies fresh page furniture."""
        if not _integer_at_least(printed_page,1):
            raise CalibrationMismatch('Printed page must be a positive integer')
        source_left=_body_left(section,source_number)
        target_left=_body_left(section,printed_page)
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
        source_left=_body_left(group['id'][0],first['printed_page'])
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
        source_left=_body_left(sec,source_info['printed_page'])
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
    def _cover_marks(self, booklet):
        """Build optional first-page identifiers from validated metadata only."""
        booklet_data=self.metadata.get('booklets',{}).get(booklet,{})
        session=booklet_data.get('session_label')
        symbol=booklet_data.get('form_symbol')
        if session=='':session=None
        if symbol=='':symbol=None
        if session is not None:
            unsafe=lambda ch: (not ch.isprintable() or ch.isspace() or
                0xE000<=ord(ch)<=0xF8FF or 0xF0000<=ord(ch)<=0xFFFFD or 0x100000<=ord(ch)<=0x10FFFD)
            if not isinstance(session,str) or len(session)>16 or any(unsafe(ch) for ch in session):
                raise ValueError(f'booklets.{booklet}.session_label must be null, empty, or a short printable label without whitespace')
        if symbol is not None and (not isinstance(symbol,str) or not re.fullmatch(r'[A-Z]',symbol)):
            raise ValueError(f'booklets.{booklet}.form_symbol must be null or one uppercase ASCII letter')
        if session is None and symbol is None:
            return [],{}
        if self.fonts is None:
            raise ValueError('Optional cover marks require the configured component font resolver')

        def centered_run(text,font,sx,sy,center_x,baseline,run_id,role,max_width=None):
            offsets=[];advance=0.0
            for char in text:
                offsets.append(advance)
                fid,code=self.fonts.resolver.resolve(font,char,'normal')
                face=self.fonts.faces[fid]
                advance+=face.widths[code]/face.upm*sy
            width=advance*sx/sy
            if max_width is not None and width>max_width+1e-7:
                raise ValueError(f'booklets.{booklet}.session_label is {width:.2f}bp wide; maximum is {max_width:.0f}bp')
            x=center_x-width/2
            command={'type':'run','run_id':run_id,'font':font,'sx':sx,'sy':sy,
                     'x':x,'y':baseline,'offsets':offsets,'slot_count':len(text),
                     'shear':0,'forms':['normal']*len(text),'role':role}
            return command,{run_id:{'glyphs':list(text)}}

        commands=[];resolved={}
        if session is not None:
            command,runs=centered_run(session,self.fonts.configured('cover_session'),25.0,25.0,297.5,719.2,
                                      f'cover-{booklet}-session-label','cover-session-label',220.0)
            commands.append(command);resolved.update(runs)
        if symbol is not None:
            center_x=42.36;center_y=self.layout['paper']['height']-27.33
            radius=29.3/2;k=radius*.552284749831
            circle=(f'q 0.65 w 0.13725 0.12157 0.12549 RG '
                    f'{center_x+radius:.12g} {center_y:.12g} m '
                    f'{center_x+radius:.12g} {center_y+k:.12g} {center_x+k:.12g} {center_y+radius:.12g} {center_x:.12g} {center_y+radius:.12g} c '
                    f'{center_x-k:.12g} {center_y+radius:.12g} {center_x-radius:.12g} {center_y+k:.12g} {center_x-radius:.12g} {center_y:.12g} c '
                    f'{center_x-radius:.12g} {center_y-k:.12g} {center_x-k:.12g} {center_y-radius:.12g} {center_x:.12g} {center_y-radius:.12g} c '
                    f'{center_x+k:.12g} {center_y-radius:.12g} {center_x+radius:.12g} {center_y-k:.12g} {center_x+radius:.12g} {center_y:.12g} c S Q')
            commands.append({'type':'vector','pdf':circle})
            # The official A/B marks are optically, not merely advance-width,
            # centered. Other letters retain the neutral placement.
            dx,dy={'A':(0.0,1.15),'B':(0.25,-0.3)}.get(symbol,(0.0,0.0))
            command,runs=centered_run(symbol,self.fonts.configured('cover_symbol'),23.6,23.6,center_x+dx,806.1+dy,
                                      f'cover-{booklet}-form-symbol','cover-form-symbol')
            commands.append(command);resolved.update(runs)
        return commands,resolved

    def cover(self,section,body_pages):
        booklet='listening' if section=='L' else 'written'
        mark_commands,mark_runs=self._cover_marks(booklet)
        pages=[]
        for i in (1,2):
            page=copy.deepcopy(self.pages[(section,i)])
            if self.fonts is not None:
                from metadata_components import resolve_metadata_components
                page['commands'],runs,audit=resolve_metadata_components(self.profile,self.metadata_path,page['commands'],self.fonts,body_pages=body_pages)
                self.resolved.update(runs);self.metadata_audit.append(audit)
            else:self.resolved.update(self.meta(page['commands'],body_pages))
            if i==1:
                page['commands'].extend(copy.deepcopy(mark_commands))
                self.resolved.update(mark_runs)
            pages.append(page)
        return pages
