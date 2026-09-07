"""Shared N1 composition and drawing; no legacy body-coordinate reuse."""
from dataclasses import replace
import re,copy
from inline import parse,plain,measure,OPEN,CLOSE,REFERENCE_BOX_RE
from geometry import CHOICE,CLOZE_BOX,body_grid,metric,require_number
from material_primitives import MaterialPrimitives
from page_furniture import decorate

_FULLWIDTH_DIGITS=str.maketrans('0123456789','０１２３４５６７８９')
_ASCII_READING_LABEL=str.maketrans('０１２３４５６７８９（）','0123456789()')
_VERTICAL_FORMS={'、':'︑','。':'︒','「':'﹁','」':'﹂','『':'﹃','』':'﹄','（':'︵','）':'︶'}

class ComponentLayout(MaterialPrimitives):
    def __init__(self,catalog,blueprint,resources,out,reference):
        super().__init__(catalog,blueprint,resources,out)
        self.reference=reference;self.resolved=reference.resolved;self.component_audit=[];self.run_counter=0
        self.top=float(self.p.get('margin_top',62.4928));self.bottom=float(self.p.get('body_bottom',770));self.y=self.top
    def geometry(self):
        self.left,self.width=body_grid(self.section).geometry(self.n(),self.p)
    def page_left(self,page_number):
        return body_grid(self.section).left(page_number,self.p)
    def _is_cloze(self):
        return bool(self.section=='G' and self.group and self.group.get('kind')=='cloze')
    def _uses_reading_spacing(self):
        return self.section=='R' or self._is_cloze()
    @staticmethod
    def _is_note(block):
        return bool(re.match(r'^[（(]注',block.get('text','')))
    @staticmethod
    def _has_vertical(block):
        return any(child.get('type')=='vertical' for child in block.get('blocks',[]))
    def new_page(self):
        self.page={'commands':[],'bands':[],'group_ids':[]};self.pages.append(self.page);self.geometry();self.y=self.top;self.add_band()
    def add_band(self):
        if self.page is None or not self.group:return
        if self.group['id'] not in self.page['group_ids']:self.page['group_ids'].append(self.group['id'])
        side=self.gc.get('sidebar',self.bp.get('sidebar',{}))
        if side is False or side is None:return
        if isinstance(side,str):side={'text':side}
        side=copy.deepcopy(side)
        if not side.get('text'):side['text']={'V':'文字・語彙','G':'文法','R':'読解','L':'聴解'}[self.section]
        side.setdefault('section',self.section)
        if not any(b.get('text')==side['text'] for b in self.page['bands']):self.page['bands'].append(side)
    def glyph(self,ch,size,x,baseline,bold=False,color='0.13725,0.12157,0.12549',rotation=0,semantic_char=None,role=None,hscale=1):
        if ch in ' \u3000\t\n':return
        semantic=semantic_char or ch
        form='vertical' if semantic_char is not None and semantic_char!=ch else 'normal'
        if form=='vertical':fid=self.catalog.preferred(bold,self.section,role)
        else:fid,_=self.catalog.route(ch,bold,self.section,role)
        self.run_counter+=1;rid=f'composed-{self.run_counter:06}'
        if self.page.get('_ink')!=color:
            self.emit({'type':'ink','rgb':[float(s) for s in color.split(',')]});self.page['_ink']=color
        self.emit({'type':'run','run_id':rid,'font':fid,'sx':size*hscale,'sy':size,'x':x,'y':self.H-baseline,'offsets':[0],'slot_count':1,'shear':0,'forms':[form],'rotation':rotation,'role':role or ('instruction' if bold else 'body')})
        self.resolved[rid]={'glyphs':[semantic]}
        self.semantic_glyphs.append({'page_ref':id(self.page),'char':semantic,'font':fid,'size':size,'x':x,'y':baseline,'role':role})
    @staticmethod
    def tracking_units(atom):
        # A framed cloze reference is one layout object even though its
        # semantic spelling contains several characters.
        return 1 if REFERENCE_BOX_RE.fullmatch(atom.text) else max(1,len(atom.text))
    def tracking_gaps(self,atoms,rigid_blanks=False):
        if not rigid_blanks:return max(0,sum(self.tracking_units(a) for a in atoms)-1)
        gaps=0;previous_flexible=False
        for atom in atoms:
            flexible=not atom.underline and not atom.text.isspace()
            if flexible:
                if previous_flexible:gaps+=1
                gaps+=max(0,self.tracking_units(atom)-1)
            previous_flexible=flexible
        return gaps
    def line_tracking(self,atoms,width,max_negative=0,rigid_blanks=False,max_negative_blanks=None,hanging_punctuation=False):
        natural=sum(a.width for a in atoms)
        if hanging_punctuation and atoms and not atoms[-1].underline and atoms[-1].text in '、。':natural-=atoms[-1].width
        if natural<=width+1e-5:return 0.0
        gaps=self.tracking_gaps(atoms,rigid_blanks)
        if gaps<=0:return None
        if rigid_blanks and max_negative_blanks is not None and any(a.underline for a in atoms):max_negative=max_negative_blanks
        tracking=(width-natural)/gaps
        return tracking if tracking>=-max_negative-1e-6 else None
    def line(self,atoms,x,top,size,align='left',width=None,color='0.13725,0.12157,0.12549',tracking=0,rigid_blanks=False):
        tw=sum(a.width for a in atoms)+tracking*self.tracking_gaps(atoms,rigid_blanks)
        if width is not None and align=='center':x+=(width-tw)/2
        elif width is not None and align=='right':x+=width-tw
        baseline=top+size;natural_x=x;tracking_shift=0;previous_flexible=False
        for a in atoms:
            reference=REFERENCE_BOX_RE.fullmatch(a.text)
            atom_units=self.tracking_units(a)
            atom_gaps=max(0,atom_units-1)
            flexible=not rigid_blanks or (not a.underline and not a.text.isspace())
            if flexible and previous_flexible:tracking_shift+=tracking
            atom_x=natural_x+tracking_shift
            if reference:
                box=CLOZE_BOX;scale=size/box.body_size;label=reference[1]+(reference[2] or '')
                frame_width=box.frame_width(reference[2],scale)
                margin=box.margin*scale
                frame_x=atom_x+margin
                self.rect(frame_x,baseline+box.top_from_baseline*scale,frame_width,box.height*scale)
                label_width=(len(reference[1])*box.digit_advance+(len(reference[2] or '')*box.suffix_advance))*scale
                xx=frame_x+(frame_width-label_width)/2
                for ch in label:
                    self.glyph(ch,box.label_size*scale,xx,baseline+box.label_from_baseline*scale,role='question-number' if ch.isdigit() else 'body',hscale=.8 if ch.isdigit() else 1)
                    xx+=(box.digit_advance if ch.isdigit() else box.suffix_advance)*scale
                natural_x+=a.width
                if flexible:tracking_shift+=tracking*atom_gaps
                previous_flexible=flexible;continue
            glyph_widths=[self.catalog.width(c,size,a.bold,self.section) for c in a.text]
            bw=sum(glyph_widths)
            internal_tracking=tracking if flexible else 0
            effective_width=a.width+internal_tracking*atom_gaps
            effective_base=bw+internal_tracking*max(0,len(a.text)-1)
            bx=atom_x+(effective_width-effective_base)/2
            for ci,(c,glyph_width) in enumerate(zip(a.text,glyph_widths)):
                self.glyph(c,size,bx,baseline,a.bold,color);bx+=glyph_width
                if ci+1<len(a.text):bx+=internal_tracking
            if a.ruby:
                rs=5.6 if abs(size-11.3)<.01 else round(size*.5,1);rw=sum(self.catalog.width(c,rs,a.bold,self.section) for c in a.ruby)
                hscale=min(1,effective_width/rw) if rw else 1
                # Long readings are condensed over their base, never widen it.
                advance=(effective_width-rs*hscale)/(len(a.ruby)-1) if len(a.ruby)>1 else 0
                rx=atom_x if len(a.ruby)>1 else atom_x+(effective_width-rs*hscale)/2
                for c in a.ruby:self.glyph(c,rs,rx,baseline-(13.3367 if abs(size-14.2)<.01 else 10.6223),a.bold,color,hscale=hscale);rx+=advance
            annotation=getattr(a,'annotation','')
            if annotation:
                ax=atom_x
                for c in annotation:
                    self.glyph(c,6.4,ax,baseline+6.98,False,color);ax+=self.catalog.width(c,6.4,False,self.section)
            if a.underline:
                # Match the reference underlines, measured about 3 bp below baseline.
                underline_y=baseline+3.0
                self.rule(atom_x,underline_y,atom_x+effective_width,underline_y,.33)
            natural_x+=a.width
            if flexible:tracking_shift+=tracking*atom_gaps
            previous_flexible=flexible
    def ordering_atoms(self,text,size,bold=False):
        """Normalize only whitespace outside, and adjacent to, ordering slots."""
        # A starred slot is intrinsically three em wide.  Padding it inside the
        # underline would create adjacent rules and can split the slot in two.
        text=re.sub(r'__[ \u3000]*★[ \u3000]*__','__★__',text)
        source=parse(text,bold);normalized=[];i=0
        while i<len(source):
            atom=source[i]
            if not atom.underline and atom.text!='\n' and atom.text.isspace():
                j=i+1
                while j<len(source) and not source[j].underline and source[j].text!='\n' and source[j].text.isspace():j+=1
                before=normalized[-1] if normalized else None;after=source[j] if j<len(source) else None
                if (before and before.underline) or (after and after.underline):normalized.append(replace(atom,text='　'))
                else:normalized.extend(source[i:j])
                i=j;continue
            normalized.append(atom);i+=1
        return measure(normalized,self.catalog,size,self.section)
    def hanging_lines(self,text,size,first_width,rest_width,bold=False,max_negative_tracking=0,rigid_blanks=False,max_negative_blank_tracking=None,hanging_punctuation=False,atoms=None):
        atoms=measure(parse(text,bold),self.catalog,size,self.section) if atoms is None else atoms;result=[];line=[]
        def fits(candidate,width):
            return self.line_tracking(candidate,width,max_negative_tracking,rigid_blanks,max_negative_blank_tracking,hanging_punctuation) is not None
        for index,a in enumerate(atoms):
            if a.text=='\n':result.append(line);line=[];continue
            width=rest_width if result else first_width
            single_fits=fits([a],width)
            if not single_fits:raise ValueError('Indivisible cluster exceeds component width: '+a.text)
            separator=not a.underline and a.text.isspace()
            candidate_fits=fits(line+[a],width) if line else single_fits
            if separator and not candidate_fits:continue
            if line and not candidate_fits:
                # Judge a glyph together with its following hanging mark. A
                # Japanese comma/period can make the pair fit even when the
                # preceding glyph alone appears to cross the strict edge.
                if (hanging_punctuation and index+1<len(atoms) and not atoms[index+1].underline
                        and atoms[index+1].text in '、。' and fits(line+[a,atoms[index+1]],width)):
                    line.append(a);continue
                carry=[]
                if a.text and a.text[0] in CLOSE:
                    while line:
                        carry.insert(0,line.pop())
                        if carry[0].text and carry[0].text[0] not in CLOSE and not carry[0].text.isspace():break
                while line and line[-1].text and line[-1].text[-1] in OPEN:carry.insert(0,line.pop())
                if line:result.append(line)
                line=carry
            if not line and separator:continue
            line.append(a)
        if line or not result:result.append(line)
        return result
    def paragraph(self,text,x=None,width=None,size=None,leading=None,bold=False,align='left',gap=0,indent=0,reserve_after=0):
        x=self.left if x is None else x;width=self.width if width is None else width;size=size or self.fs
        leading=leading or self.leading;anchor=self.left
        ls=self.hanging_lines(text,size,width-indent,width,bold) if indent else self.get_lines(text,size,width,bold)
        for i,ln in enumerate(ls):
            # Keep the final two lines with their citation. The horizontal
            # position remains relative to the page on which each line lands.
            remaining=len(ls)-i
            need=remaining*leading+reserve_after if reserve_after and remaining<=2 else leading
            self.ensure(need if need<=self.usable else leading);xx=x+self.left-anchor+(indent if i==0 else 0)
            self.line(ln,xx,self.y,size,align,width-(indent if i==0 else 0));self.y+=leading
        self.gap(gap)
    def paragraph_height(self,text,width=None,size=None,leading=None,bold=False):
        size=size or self.fs;leading=leading or self.leading
        return len(self.get_lines(text,size,width or self.width,bold))*leading
    def paragraph_format(self,b):
        if self.section=='L' and self.group and self.group['kind']=='listening_compound':return 11.3,25.47,True
        cloze=self._is_cloze()
        in_cloze_material=cloze and getattr(self,'_cloze_material_depth',0)>0
        if in_cloze_material and b.get('type')=='heading':return 11.3,float(self.gc.get('material_title_line_height',48.12)),False
        if b.get('style')=='small':
            if self._is_note(b):return 11.3,float(self.gc.get('material_note_line_height',19.89 if cloze else 24.06)),False
            return 9.2,16.98,False
        # The compact 19.8 bp leading belongs to the framed cloze article.
        # Its unframed introduction keeps the ordinary 24.06 bp body leading.
        leading=(float(self.gc.get('material_line_height',19.8)) if in_cloze_material
                 else float(self.gc.get('material_intro_line_height',self.leading)) if cloze else self.leading)
        return self.fs,leading,b.get('type')=='heading' or b.get('style')=='bold'
    def paragraph_indent(self,b,bold,align,width):
        default=11.31 if align=='left' and b.get('style')!='small' and not bold and self.section in ('R','G') else 0
        raw=b.get('indent',default)
        if isinstance(raw,bool):raise ValueError('Paragraph indent must be a non-negative number')
        try:indent=float(raw)
        except (TypeError,ValueError) as e:raise ValueError('Paragraph indent must be a non-negative number') from e
        if indent<0 or indent>=width:raise ValueError('Paragraph indent must be smaller than its line width')
        return indent
    def reading_paragraph_gap(self,b):
        if b.get('style')!='small':return 0
        is_note=self._is_note(b)
        continuation_gap=(float(self.gc.get('material_wrapped_note_gap',3.0))
                          if getattr(self,'_last_note_wrapped',False) else 0)
        if self.section=='G':
            return (continuation_gap if getattr(self,'_last_was_note',False) else 20.96) if is_note else .25
        if is_note:
            if getattr(self,'_last_was_note',False):return continuation_gap
            # The type-size change from 9.2 to 11.3 is part of the baseline gap.
            return 19.021 if getattr(self,'_last_material_kind',None)=='box' else 18.86
        return 2.35
    def reading_sequence_height(self,blocks,width):
        saved_note=getattr(self,'_last_was_note',False)
        saved_wrapped=getattr(self,'_last_note_wrapped',False)
        saved_kind=getattr(self,'_last_material_kind',None)
        height=0
        try:
            for child in blocks:
                height+=self.estimate_block(child,width)
                is_note=self._is_note(child);self._last_was_note=is_note
                if is_note:
                    size,_,bold=self.paragraph_format(child)
                    self._last_note_wrapped=len(self.get_lines(child.get('text',''),size,width,bold))>1
                else:self._last_note_wrapped=False
                self._last_material_kind=('note' if is_note else 'citation' if child.get('style')=='small' else child.get('type'))
        finally:
            self._last_was_note=saved_note;self._last_note_wrapped=saved_wrapped;self._last_material_kind=saved_kind
        return height
    def blocks(self,blocks,x=None,width=None,tail_reserve=0):
        if not self._uses_reading_spacing():return super().blocks(blocks,x,width)
        offset=(self.left if x is None else x)-self.left
        width=self.width if width is None else width;i=0
        while i<len(blocks):
            child=blocks[i]
            # A/B labels belong to their frames. Decide the page before either
            # element is drawn; never leave a label behind after ensure().
            if child.get('type')=='heading' and i+1<len(blocks) and blocks[i+1].get('type')=='box':
                frame=dict(blocks[i+1],_reading_ab=True)
                need=19.03+self.estimate_block(frame,width)
                keep=need if need<=self.usable else 19.03+2*self.leading+16
                self.ensure(self.opening_keep_height(frame,keep,width,prefix=19.03,consume=False))
                self.line(self.get_lines(child.get('text',''),11.3,width,True)[0],self.left+offset,self.y,11.3)
                self.y+=19.03
                self.reading_box(frame,self.left+offset,width)
                i+=2;continue
            # Definitions can stay together without dragging the citation away
            # from the preceding article. Citations are reserved by its tail.
            is_note=self._is_note(child)
            if child.get('type')=='paragraph' and is_note:
                end=i+1
                while end<len(blocks) and blocks[end].get('type')=='paragraph' and self._is_note(blocks[end]):end+=1
                need=self.reading_sequence_height(blocks[i:end],width)
                if need<=self.usable:self.ensure(need)
                for note in blocks[i:end]:self.block(note,self.left+offset,width)
                i=end;continue
            prepared=dict(child)
            if child.get('type')=='paragraph':
                reserve=tail_reserve if i==len(blocks)-1 else 0
                if i+1<len(blocks) and child.get('style')!='small':
                    following=blocks[i+1]
                    if following.get('type')=='paragraph' and following.get('style')=='small' and following.get('align')=='right':
                        reserve+=self.estimate_block(following,width)
                        if i+1==len(blocks)-1:reserve+=tail_reserve
                prepared['_reserve_after']=reserve
            self.block(prepared,self.left+offset,width);i+=1
    def reading_box_padding(self,b):
        ab=b.get('_reading_ab',False)
        if self._is_cloze():
            padding=float(self.gc.get('material_box_padding',11.31))
            return padding,float(self.gc.get('material_box_top_padding',24.06)),float(self.gc.get('material_box_bottom_padding',9.117)),5.105
        inset=5.64 if ab else 8.0
        top=10.702 if ab else 8.0
        children=b.get('blocks',[])
        citation=bool(children and children[-1].get('style')=='small' and children[-1].get('align')=='right')
        bottom=(6.04 if citation else 1.31) if ab else 8.0
        return inset,top,bottom,3.729 if ab else 6.0
    def reading_box(self,b,x,width):
        children=b.get('blocks',[])
        if any(child.get('type')=='vertical' for child in children):return self.vertical_box(b,x,width)
        cloze_material=self._is_cloze()
        offset=x-self.left
        if cloze_material and not b.get('_material_box_outer'):
            outset=float(self.gc.get('material_box_outset',11.31));offset-=outset;width+=2*outset
            b=dict(b,_material_box_outer=True)
        if len(children)==1 and children[0].get('type')=='image':
            _,iw,_=self.image_geometry(children[0],width-16)
            narrow=min(width,iw+16);offset+=(width-narrow)/2;width=narrow
        inset,padtop,padbottom,after=self.reading_box_padding(b)
        previous_depth=getattr(self,'_cloze_material_depth',0)
        if cloze_material:self._cloze_material_depth=previous_depth+1
        try:est=self.estimate_block(b,width)
        finally:self._cloze_material_depth=previous_depth
        need=est if est<=self.usable else min(est,2*self.leading+padtop+padbottom)
        self.ensure(self.opening_keep_height(b,need,width))
        first=len(self.pages)-1;start_y=self.y
        self.y+=padtop
        if cloze_material:self._cloze_material_depth=previous_depth+1
        try:self.blocks(children,self.left+offset+inset,width-2*inset,tail_reserve=padbottom)
        finally:self._cloze_material_depth=previous_depth
        self.y+=padbottom
        stroke=float(self.gc.get('material_box_stroke',1.71 if cloze_material else .33))
        self.frame_segments(first,start_y,offset,width,stroke)
        self.gap(after)
        self._last_was_note=False;self._last_note_wrapped=False;self._last_material_kind='box'
    def paragraph_spec(self,b,width):
        """Return the shared measurement/drawing settings for one paragraph."""
        size,leading,bold=self.paragraph_format(b)
        is_note=self._is_note(b);small=b.get('style')=='small';kind=b['type']
        align=b.get('align','center' if self._is_cloze() and kind=='heading' else 'left')
        indent=self.paragraph_indent(b,bold,align,width)
        if self._uses_reading_spacing():before=self.reading_paragraph_gap(b)
        elif small and not is_note:before=.25
        elif is_note:
            before=((float(self.gc.get('material_wrapped_note_gap',3.0))
                     if getattr(self,'_last_note_wrapped',False) else 0)
                    if getattr(self,'_last_was_note',False) else 20.96)
        else:before=0
        return size,leading,bold,is_note,small,align,indent,before
    def paragraph_body_text(self,block):
        """Use the same below-word marker text for measurement and drawing."""
        text=block.get('text','')
        if self.section=='R' and block.get('style')!='small':
            return re.sub(r'([①②③④⑤⑥⑦⑧⑨⑩])__(.*?)__',
                          lambda match:'{{'+match[1]+'|__'+match[2]+'__}}',text)
        return text
    def block(self,b,x=None,width=None):
        x=self.left if x is None else x;width=self.width if width is None else width;t=b['type']
        if t in ('paragraph','heading'):
            size,leading,bold,is_note,small,align,indent,before=self.paragraph_spec(b,width);self.gap(before)
            body_text=self.paragraph_body_text(b)
            note_lines=len(self.get_lines(body_text,size,width,bold)) if is_note else 0
            self.paragraph(body_text,x,width,size,leading,bold,align,gap=0,indent=indent,reserve_after=b.get('_reserve_after',0))
            self._last_was_note=is_note
            self._last_note_wrapped=is_note and note_lines>1
            self._last_material_kind='note' if is_note else 'citation' if small else t
        elif t=='separator':self.gap(24.06)
        elif t=='box' and self._has_vertical(b):self.vertical_box(b,x,width)
        elif t=='box' and self._uses_reading_spacing():self.reading_box(b,x,width)
        else:super().block(b,x,width)
    def estimate_block(self,b,width=None):
        width=width or self.width;t=b.get('type')
        if t in ('paragraph','heading'):
            size,leading,bold,is_note,small,align,indent,before=self.paragraph_spec(b,width)
            ls=self.hanging_lines(b.get('text',''),size,width-indent,width,bold)
            return len(ls)*leading+before
        if t=='separator':return 24.06
        if t=='box' and self._has_vertical(b):return 335
        if t=='box' and self._uses_reading_spacing():
            if self._is_cloze() and not b.get('_material_box_outer'):width+=2*float(self.gc.get('material_box_outset',11.31))
            inset,top,bottom,after=self.reading_box_padding(b)
            return top+self.reading_sequence_height(b.get('blocks',[]),width-2*inset)+bottom+after
        return super().estimate_block(b,width)
    def configured_columns(self,item):
        overrides=self.gc.get('options_columns_by_item',{})
        if not isinstance(overrides,dict):raise ValueError('options_columns_by_item must be a mapping')
        configured=overrides.get(item.get('id'),self.gc.get('options_columns','auto'))
        if configured=='auto':return configured
        if isinstance(configured,bool) or str(configured) not in ('1','2','4'):
            raise ValueError('options_columns must be auto, 1, 2, or 4')
        return int(configured)
    def _auto_columns(self,available,option_atoms):
        for cols in (4,2,1):
            try:_,widths=CHOICE.geometry(cols,available)
            except ValueError:continue
            # Auto layout uses the repeated grid's narrowest cell. The last
            # cell reaches the page edge and must not alone make a row qualify
            # for a denser column count.
            capacity=min(first for first,_ in widths)
            if all(sum(a.width for a in atoms)<=capacity for atoms in option_atoms):return cols
        return 1
    def material_height(self, blocks, width):
        return sum(self.estimate_block(block, width) for block in blocks)

    def choice_prompt_plan(self, item, size, rigid_blanks):
        """Plan prompt rows; specialized typography may supply its own insets."""
        prompt = item.get('prompt', '')
        # Vocabulary prompts in A occasionally use about -.42 bp tracking to
        # stay on one line. Ordering slots need a more conservative limit.
        max_tracking = metric(self.gc, 'choice_prompt_max_negative_tracking',
                              .15 if rigid_blanks else .45, allow_zero=True)
        blank_tracking = metric(self.gc, 'word_order_blank_max_negative_tracking',
                                .27, allow_zero=True)
        # The first line starts one em to the right of continuation lines and
        # ends at the ordinary body edge. Japanese 、/。 may hang beyond it.
        first_prompt_width = self.width - CHOICE.prompt_inset(0)
        rest_prompt_width = self.width - CHOICE.prompt_inset(1)
        prompt_atoms = self.ordering_atoms(prompt, size) if rigid_blanks else None
        promptlines = self.hanging_lines(
            prompt, size, first_prompt_width, rest_prompt_width,
            max_negative_tracking=max_tracking, rigid_blanks=rigid_blanks,
            max_negative_blank_tracking=blank_tracking, hanging_punctuation=True,
            atoms=prompt_atoms,
        )
        prompt_tracking = [
            self.line_tracking(line, first_prompt_width if i == 0 else rest_prompt_width,
                               max_tracking, rigid_blanks, blank_tracking, True) or 0.0
            for i, line in enumerate(promptlines)
        ]
        return {'promptlines': promptlines, 'prompt_tracking': prompt_tracking}

    def choice_option_atoms(self, text, size):
        """Use the same measured atoms for automatic columns and final rows."""
        return measure(parse(text), self.catalog, size, self.section)

    def choice_option_plan(self, options, option_atoms, widths, cols, size):
        oplines = []
        for i, (text, atoms) in enumerate(zip(options, option_atoms)):
            first, rest = widths[i % cols]
            oplines.append(self.hanging_lines(text, size, first, rest, atoms=atoms))
        return oplines

    def choice_metrics(self,item):
        """Measure each field once, then share one grid/height plan with drawing."""
        options = item.get('options', [])
        if len(options) != 4:
            raise ValueError('Choice must have four options: ' + item.get('id', ''))
        size = float(self.gc.get('font_size', self.fs))
        lead = float(self.gc.get('line_height', self.leading))
        rigid_blanks = bool(self.group and self.group.get('kind') == 'word_order')
        prompt = self.choice_prompt_plan(item, size, rigid_blanks)
        configured = self.configured_columns(item)
        option_atoms = [self.choice_option_atoms(text, size) for text in options]
        cols = configured if configured != 'auto' else self._auto_columns(self.width, option_atoms)
        starts, widths = CHOICE.geometry(cols, self.width)
        oplines = self.choice_option_plan(options, option_atoms, widths, cols, size)
        row_counts = [max(len(oplines[i + j]) for j in range(min(cols, 4 - i)))
                      for i in range(0, 4, cols)]

        explicit_label = (str(item['label']) if item.get('label') is not None
                          else '例' if item.get('is_example') else None)
        label_height = (lead if explicit_label is not None
                        and not (explicit_label.isascii() and explicit_label.isdigit()) else 0)
        prompt_height = max(1, len(prompt['promptlines'])) * lead + label_height
        material_height = self.material_height(item.get('stimulus', []), self.width - CHOICE.inset)
        return {
            'size': size, 'lead': lead, **prompt, 'rigid_blanks': rigid_blanks,
            'cols': cols, 'starts': starts, 'widths': widths,
            'oplines': oplines, 'row_counts': row_counts,
            'total': (prompt_height + sum(row_counts) * lead + material_height
                      + float(self.gc.get('question_gap', 14.13))),
        }

    def prompt_line(self, atoms, x, top, size, width, final, tracking, rigid_blanks):
        self.line(atoms, x, top, size, tracking=tracking, rigid_blanks=rigid_blanks)

    def option_line(self, atoms, x, top, size, width, final):
        self.line(atoms, x, top, size)

    def choice(self,item):
        if self.section == 'L':
            return self.listening_choice(item)
        opening = getattr(self, '_opening_choice', None)
        if opening is not None and opening[0] is item:
            plan = opening[1]
            self._opening_choice = None
        else:
            plan = self.choice_metrics(item)
        size, lead = plan['size'], plan['lead']
        split_opening = (getattr(self, '_split_group_opening', False)
                         and opening is not None and opening[0] is item)
        if plan['total'] <= self.usable and not split_opening:
            self.ensure(plan['total'])
        label = self.next_label(item)
        numeric_label = label.isascii() and label.isdigit()
        # A numeric label shares the first prompt row; an explicit label such
        # as （問題例） occupies the row immediately above it. Keep that unit
        # together, then allow arbitrarily long prompts to flow line by line.
        self.ensure(lead * (1 if numeric_label else 2))
        first = len(self.pages)
        if numeric_label:
            self.rect(self.left - .105, self.y + 1.697, 16.742, 11.073)
            number_x = self.left + (4.83 if len(label) == 1 else 2.28)
            for ch in label:
                self.glyph(ch, 9.2, number_x, self.y + size - .828,
                           role='question-number', hscale=.8)
                number_x += 5.070304
        else:
            self.paragraph(label, size=size, leading=lead, bold=True)

        for i, line in enumerate(plan['promptlines']):
            if i:
                self.ensure(lead)
            inset = (plan['prompt_insets'][i] if 'prompt_insets' in plan
                     else CHOICE.prompt_inset(i))
            self.prompt_line(line, self.left + inset, self.y, size,
                             self.width - inset,
                             i + 1 == len(plan['promptlines']),
                             plan['prompt_tracking'][i], plan['rigid_blanks'])
            self.y += lead
        stimulus = item.get('stimulus', [])
        after_options = item.get('stimulus_position') == 'after_options'
        if stimulus and not after_options:
            self.blocks(stimulus, self.left + CHOICE.inset, self.width - CHOICE.inset)

        for i, count in zip(range(0, 4, plan['cols']), plan['row_counts']):
            self.ensure(count * lead)
            for j in range(min(plan['cols'], 4 - i)):
                start = plan['starts'][j]
                number = str(i + j + 1).translate(_FULLWIDTH_DIGITS)
                self.line(self.get_lines(number, size, 24)[0], self.left + start, self.y, size)
                for k, line in enumerate(plan['oplines'][i + j]):
                    self.option_line(line, self.left + start + CHOICE.answer_inset(k),
                                     self.y + k * lead, size, plan['widths'][j][bool(k)],
                                     k + 1 == len(plan['oplines'][i + j]))
            self.y += count * lead
        if stimulus and after_options:
            self.blocks(stimulus, self.left + CHOICE.inset, self.width - CHOICE.inset)
        self.gap(float(self.gc.get('question_gap', 14.13)))
        self.item_records.append({
            'id': item.get('id'), 'source_number': item.get('source_number'),
            'label': plain(label), 'pages': list(range(first, len(self.pages) + 1)),
            'options': 4, 'columns': plan['cols'],
            'prompt_tracking': [round(v, 5) for v in plan['prompt_tracking']],
        })
    def listen_label(self,label,baseline,x=None):
        x=self.left if x is None else x
        atoms=measure(parse(label,True),self.catalog,20,self.section)
        for a in atoms:
            start=x
            for c in a.text:
                role='listening-number' if c.isdigit() or c=='番' else 'heading'
                self.glyph(c,20,x,baseline,True,role=role,hscale=.8 if c.isascii() and c.isdigit() else 1)
                x+=18 if c.isascii() and c.isdigit() else 20
            if a.ruby:
                for i,c in enumerate(a.ruby):self.glyph(c,10,start+i*10,baseline-18.8077,True,role='ruby-heading')
    def listening_panel_metrics(self,item,compound=False):
        """Use one option-row plan for opening reservation and panel drawing."""
        option_width=self.width-21.96
        lines=[self.hanging_lines(text,14.2,option_width,option_width) for text in item['options']]
        if len(lines)!=4:raise ValueError('Listening choice must have four options')
        rows=sum(map(len,lines))
        advance=20+26.2283-14.2+rows*28.35
        if compound:advance=max(167.4,advance+21.9717)
        return {'option_lines':lines,'ink_height':20+26.2283+(rows-1)*28.35+14.2*.25,
                'advance':advance}
    def listening_choice(self,item):
        example=bool(item.get('is_example'));compound=self.group['kind']=='listening_compound'
        limit=self.bottom
        if not example and not compound:
            count=self.gc.get('items_per_page',2)
            if isinstance(count,bool) or not isinstance(count,int) or count<1:
                raise ValueError('items_per_page must be a positive integer')
            if not getattr(self,'_listen_on_page',0) or self._listen_on_page>=count:
                self.new_page();self._listen_on_page=0
            if count==2 and abs(self.top-61.4489)<.001 and abs(self.bottom-783)<.001:
                pitch=368.31
            else:pitch=(self.bottom-self.top)/count
            base=self.top+20+self._listen_on_page*pitch
            if self._listen_on_page+1<count:limit=min(limit,base+pitch-31)
            self._listen_on_page+=1
        else:base=self.y+20
        opening=getattr(self,'_opening_listening',None)
        if opening is not None and opening[0] is item:
            plan=opening[1];self._opening_listening=None
        else:plan=self.listening_panel_metrics(item,compound)
        option_lines=plan['option_lines']
        ink_bottom=base-20+plan['ink_height']
        if ink_bottom>limit:
            raise ValueError('Listening panel exceeds its allocated space; reduce items_per_page or shorten its options')
        label=self.next_label(item);first=len(self.pages);self.listen_label(label,base)
        self.y=base+26.2283-14.2
        for i,ls in enumerate(option_lines):
            self.glyph(str(i+1),14.2,self.left,self.y+14.2,role='listening-option',hscale=.8)
            for ln in ls:self.line(ln,self.left+21.96,self.y,14.2);self.y+=28.35
        if compound:self.y=max(base+167.4-20,self.y+21.9717)
        self.item_records.append({'id':item.get('id'),'source_number':item.get('source_number'),'label':plain(label),'pages':[first],'options':4})
    def passage(self,item):
        if self.section=='L':return self.listening_passage(item)
        if self.gc.get('layout')=='facing_pages':return self.facing(item)
        stimulus=item.get('stimulus',[]);questions=item.get('questions',[])
        if not getattr(self,'_first_group_item',False) and self.gc.get('passages_new_page',True):self.new_page()
        if item.get('label'):
            if self.section=='R':self.reading_item_label(str(item['label']))
            else:self.paragraph(str(item['label']),size=11.3,leading=24.06,gap=0)
        self._last_was_note=False;self._last_note_wrapped=False
        self._last_material_kind=None
        self.blocks(stimulus)
        if questions and self.gc.get('questions_new_page',self.group.get('kind')=='cloze'):
            self.new_page()
        else:
            material_gap=float(self.gc.get('material_question_gap',24.06))
            if self.section=='R' and self._last_material_kind=='citation':material_gap=float(self.gc.get('citation_question_gap',material_gap-5.2))
            self.gap(material_gap)
        for q in questions:self.choice(q)
    def reading_item_label(self,label):
        normalized=label.translate(_ASCII_READING_LABEL)
        m=re.fullmatch(r'\(\s*([1-9])\s*\)',normalized)
        if not m:return self.paragraph(label,size=11.3,leading=24.06,gap=0)
        self.ensure(24.06);baseline=self.y+11.3
        color='0.13725,0.12157,0.12549'
        if self.page.get('_ink')!=color:
            self.emit({'type':'ink','rgb':[float(c) for c in color.split(',')]});self.page['_ink']=color
        self.run_counter+=1;rid=f'composed-{self.run_counter:06}'
        self.emit({'type':'run','run_id':rid,'font':'R001','sx':11.3,'sy':11.3,'x':self.left,'y':self.H-baseline,'offsets':[0],'slot_count':1,'shear':0,'forms':['combined'],'role':'subitem-parentheses'})
        self.resolved[rid]={'glyphs':['( )']}
        self.semantic_glyphs.append({'page_ref':id(self.page),'char':'( )','font':'R001','size':11.3,'x':self.left,'y':baseline,'role':'subitem-parentheses'})
        self.glyph(chr(ord('０')+int(m[1])),10.6,self.left+.36,baseline-.27294,True)
        self.y+=24.06
    def facing(self,item):
        questions=item.get('questions',[]);stimulus=item.get('stimulus',[])
        if getattr(self,'facing_started',False):
            if self.y>self.top+.1:self.new_page()
            if self.n()%2==1:self.new_page()
        self.facing_started=True;left_index=len(self.pages)
        if item.get('label'):self.reading_item_label(str(item['label']))
        for question in questions:self.choice(question)
        if len(self.pages)!=left_index:raise ValueError('Facing-page questions exceed the left page; shorten them or use ordinary reading layout')
        self.new_page()
        self.reference_material(stimulus)
    def reference_material(self,stimulus):
        """Compose the right-hand material of a facing spread on one page."""
        right_index=len(self.pages)
        size,leading=self.fs,self.leading
        self.fs=float(self.gc.get('reference_font_size',9.2));self.leading=float(self.gc.get('reference_line_height',13.68))
        outset=metric(self.gc,'reference_outset',16.95,allow_zero=True)
        if self.left-outset<0 or self.left+self.width+outset>self.W:
            raise ValueError('reference_outset places material outside the page')
        try:self.blocks(stimulus,self.left-outset,self.width+2*outset)
        finally:self.fs,self.leading=size,leading
        if len(self.pages)!=right_index:raise ValueError('Reference material exceeds one page; simplify the material or supply it as one PDF/PNG asset')
    def listening_passage(self,item):
        stimulus=item.get('stimulus',[]);questions=item.get('questions',[])
        if self.group['kind']=='listening_memo':
            self._listening_blocks(stimulus);return
        if not getattr(self,'_first_group_item',False):self.new_page()
        if item.get('label'):
            self.listen_label(str(item['label']),self.y+20)
            self.y+=40.8439-11.3
        intro=bool(getattr(self,'_first_group_item',False))
        width=float(self.gc.get('compound_intro_width' if intro else 'compound_followup_width',486.34 if intro else 475.028))
        tracking=float(self.gc.get('compound_intro_first_line_tracking',-.27007)) if intro else 0
        self._listening_blocks(stimulus,min(self.width,width),tracking)
        if questions:
            self.gap(float(self.gc.get('compound_question_gap',21.606)))
            for q in questions:self.listening_choice(q)
    def _listening_instruction(self,text,width,tracking=0,size=11.3,leading=25.47):
        if size<=0 or leading<=0:raise ValueError('Listening instruction size and line height must be positive')
        indent=size*(11.31/11.3);nominal_advance=size*(11.31017/11.3)
        if width<=indent or width>self.width+1e-6:
            raise ValueError('Listening instruction width must fit inside the body width')
        ratio=(nominal_advance+tracking)/nominal_advance
        if ratio<=0:raise ValueError('Listening instruction tracking must leave positive glyph advances')
        for paragraph in (p for p in str(text).splitlines() if p.strip()):
            rows=self.hanging_lines(paragraph,size,(width-indent)/ratio,width,True)
            for row,atoms in enumerate(rows):
                self.ensure(leading);x=self.left+(indent if row==0 else 0)
                command_start=len(self.page['commands']);glyph_start=len(self.semantic_glyphs)
                self.line(atoms,x,self.y,size)
                if row==0 and ratio!=1:
                    # Source L5's opening material line is tracked slightly
                    # tighter while retaining the full original glyph shape.
                    for command in self.page['commands'][command_start:]:
                        if command['type']=='run':command['x']=x+(command['x']-x)*ratio
                        elif command['type']=='vector':command['pdf']=f'q {ratio} 0 0 1 {x*(1-ratio)} 0 cm\n'+command['pdf']+'\nQ'
                    for glyph in self.semantic_glyphs[glyph_start:]:glyph['x']=x+(glyph['x']-x)*ratio
                self.y+=leading
    def listening_memo_height(self,block):
        height=min(metric(block,'height',260),self.usable)
        size=metric(block,'font_size',14.2)
        baseline=require_number(self.gc.get('memo_baseline_gap',25.1744),
                                'memo_baseline_gap must be a finite number')
        if plain(str(block.get('label','－メモ－'))) and height<baseline+size*.25:
            raise ValueError('Listening memo height must contain its label; increase height or reduce its font size')
        return height
    def _listening_memo(self,block):
        height=self.listening_memo_height(block)
        self.ensure(height)
        text=plain(str(block.get('label','－メモ－')));size=float(block.get('font_size',14.2))
        if size<=0:raise ValueError('Listening memo font size must be positive')
        scale=size/14.2;positions=[];advance=0
        for index,ch in enumerate(text):
            positions.append(advance)
            advance+=(14.190065 if ord(ch)>=0x3000 else self.catalog.width(ch,14.2,False,self.section))*scale
            if index==0 and ch in '－―—':advance+=3.540065*scale
            if index+2==len(text) and text[-1:] in '－―—':advance+=3.540065*scale
        extent=(positions[-1]+size) if positions else 0
        x=self.left+float(self.gc.get('memo_center_offset',243.1551625))-extent/2
        baseline=self.y+float(self.gc.get('memo_baseline_gap',25.1744))
        for ch,offset in zip(text,positions):self.glyph(ch,size,x+offset,baseline)
        self.y+=height
    def _listening_blocks(self,blocks,width=None,first_tracking=0):
        width=self.width if width is None else width
        for block in blocks:
            kind=block.get('type')
            if kind in ('paragraph','heading'):
                self._listening_instruction(block.get('text',''),width,first_tracking)
            elif kind=='memo':self._listening_memo(block)
            else:self.block(block,self.left,width)
    def _listening_heading(self,group,config):
        title=config.get('title',group.get('title',''))
        if config.get('heading_layout','stacked')!='stacked':
            raise ValueError('Listening heading_layout must be stacked')
        heading_size=metric(config,'heading_size',36)
        instruction_size=metric(config,'instruction_font_size',11.3)
        instruction_leading=metric(config,'instruction_line_height',25.47)
        instruction_width=metric(config,'instruction_width',self.width)
        scale=heading_size/36
        self.glyph_text('もんだい',heading_size/2,self.left,self.top+.2312*scale,True,role='ruby-heading')
        self.glyph_text(plain(title),heading_size,self.left,self.top+34.0712*scale,True,role='heading')
        self.y=self.top+51.204*scale
        self._listening_instruction(group.get('instruction',''),instruction_width,
                                    size=instruction_size,leading=instruction_leading)
        if group['kind']!='listening_memo':self.gap(21.606)
    def vertical_box(self,b,x,width):
        # The text and its citation both use vertical columns, read right to left.
        children=b['blocks'];columns=[]
        for child in children:
            text=child.get('text','');small=child['type']!='vertical';size=9.2 if small else 11.3
            cells=30 if small else 25;col=[]
            if not small:col.append((' ',None,0))
            for atom in parse(text):
                if atom.text=='\n':
                    if col:columns.append((size,col));col=[]
                    col.append((' ',None,0));continue
                if atom.ruby and len(col)+len(atom.text)>cells:columns.append((size,col));col=[]
                for ai,ch in enumerate(atom.text):
                    if len(col)>=cells:columns.append((size,col));col=[]
                    col.append((ch,atom,ai))
            if col:columns.append((size,col))
        pitch=24.06;offset=x-self.left;distances=[]
        for ci,(size,_) in enumerate(columns):
            if ci:
                previous_size=columns[ci-1][0]
                distances.append(16.98 if previous_size==size==9.2 else 23.01 if size==9.2 else pitch)
        bw=24.039+sum(distances)+12.364;h=317.451
        if bw>width+1e-6:raise ValueError('Vertical quotation exceeds the available page width; reduce its column count or use a separate reference asset')
        self.ensure(h+6.744);left=self.left+offset+(width-bw)/2;top=self.y;self.rect(left,top,bw,h)
        xx=left+bw-24.039
        for ci,(size,column) in enumerate(columns):
            if ci:xx-=distances[ci-1]
            step=11.31018 if size==11.3 else 9.21
            start=top+16+size if size==11.3 else top+h-13.416-(len(column)-1)*step
            for ri,(ch,a,ai) in enumerate(column):
                yy=start+ri*step
                self.glyph(_VERTICAL_FORMS.get(ch,ch),size,xx,yy,a.bold if a else False,rotation=-90 if ch in 'ー―—〜～' else 0,semantic_char=ch if ch in _VERTICAL_FORMS else None)
                if a and a.ruby and ai==0:
                    rs=5.6;span=len(a.text)*11.31018;advance=span/len(a.ruby)
                    for i,c in enumerate(a.ruby):self.glyph(c,rs,xx+11.54,yy-5+i*advance,a.bold)
                if a and a.underline:self.rule(xx+size*1.1,yy-size*.9,xx+size*1.1,yy+size*.1)
        self.y+=h;self.gap(6.744)
        self._last_was_note=False;self._last_note_wrapped=False;self._last_material_kind='vertical_box'
    def template_example(self,item):
        return False
    def begin_group(self,group,config):
        if config.get('new_page',True) or self.page is None:self.new_page()
        else:self.add_band()
    def group_heading(self,group,config):
        self.dynamic_heading(group,config)
    def group_opening(self,group,config):
        """Draw the heading and return the number of items already rendered."""
        self.group_heading(group,config)
        return 0
    def render_group(self,group,config):
        self.group=group;self.gc=config;self.section=group['id'][0];self.group_number=int(config.get('number_start',1));self.fs=float(config.get('font_size',self.p['font_size']));self.leading=float(config.get('line_height',self.p['line_height']));self.facing_started=False
        self.begin_group(group,config)
        self.compose_group(group,config)
    def compose_group(self,group,config,*,reason='Custom composition configuration'):
        items=group.get('items',[])
        self.component_audit.append({'group':group['id'],'placement':'composed','reason':reason,'first_body_page':len(self.pages)})
        skip=self.group_opening(group,config)
        body_start_adjust=require_number(config.get('body_start_adjust',0),'body_start_adjust must be a number')
        if self.y+body_start_adjust<self.top or self.y+body_start_adjust>self.bottom:
            raise ValueError('body_start_adjust places content outside the usable page')
        self.y+=body_start_adjust
        self._listen_on_page=0
        for idx,item in enumerate(items[skip:],skip):
            self._first_group_item=(idx==0)
            if idx:self._split_group_opening=False
            self.render_item(item,idx)
    def render_item(self,item,index):
        if self.template_example(item):
            self.record_example(item)
        elif self.group['kind'] in ('choice','word_order','listening_choice'):self.choice(item)
        else:self.passage(item)
    def record_example(self,item):
        self.item_records.append({'id':item['id'],'source_number':None,'label':item.get('label','例'),'pages':[len(self.pages)],'options':4})
    def dynamic_heading(self,group,config):
        title=config.get('title',group.get('title',''));instruction=group.get('instruction','')
        if self.section=='L':return self._listening_heading(group,config)
        match=re.fullmatch(r'問題\s*([0-9０-９]{1,2})',plain(title))
        if match:
            self.glyph('問',12.8,self.left,self.top+12.6201,True)
            self.glyph('題',12.8,self.left+12.81024,self.top+12.6201,True)
            digits=match[1].translate(_FULLWIDTH_DIGITS)
            for i,ch in enumerate(digits):self.glyph(ch,12.8,self.left+(22.42048+i*6.38976 if len(digits)==2 else 25.62048),self.top+12.6201,True)
        else:self.glyph_text(plain(title),12.8,self.left,self.top+12.6201,True)
        ls=self.hanging_lines(instruction,11.3,self.width-50.88,self.width-39.57,True)
        for i,ln in enumerate(ls):self.line(ln,self.left+(50.88 if i==0 else 39.57),self.top+i*24.06,11.3)
        self.y=self.top+len(ls)*24.06+14.13
    def glyph_text(self,text,size,x,baseline,bold=False,role=None,hscale=1):
        for c in text:
            self.glyph(c,size,x,baseline,bold,role=role,hscale=hscale);x+=self.catalog.width(c,size,bold,self.section)*hscale
    def decorate(self):decorate(self)
