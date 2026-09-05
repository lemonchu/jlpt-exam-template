"""N1 components using the same measured typography for arbitrary semantic text."""
from pathlib import Path
from dataclasses import replace
import re,copy,json
from inline import lines,parse,plain,measure,OPEN,CLOSE
from material_primitives import MaterialPrimitives
from semantic_bindings import CalibrationMismatch
from page_furniture import decorate

class ComponentLayout(MaterialPrimitives):
    def __init__(self,catalog,blueprint,resources,out,reference):
        super().__init__(catalog,blueprint,resources,out)
        self.reference=reference;self.resolved=reference.resolved;self.component_audit=[];self.run_counter=0
        self.top=float(self.p.get('margin_top',62.4928));self.bottom=float(self.p.get('body_bottom',770));self.y=self.top
    def geometry(self):
        odd=self.n()%2==1
        if self.section=='L':left=63.45 if odd else 45.21;width=513.6
        else:left=78.96 if odd else 63.63;width=452.41
        self.left=float(self.p.get('left_odd' if odd else 'left_even',left));self.width=float(self.p.get('body_width',width));self.right=self.left+self.width
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
    def emit(self,cmd):
        if isinstance(cmd,dict):self.page['commands'].append(cmd);return
        if cmd.startswith('\\FlowVector{'):self.page['commands'].append({'type':'vector','pdf':cmd[len('\\FlowVector{'):-1]});return
        m=re.fullmatch(r'\\FlowImage\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}',cmd)
        if m:
            asset,w,h,x,y=m.groups();self.page['commands'].append({'type':'image','asset':asset,'width':float(w),'height':float(h),'x':float(x),'y':float(y)});return
        raise ValueError('Non-scene command in component renderer: '+cmd[:60])
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
    def line(self,atoms,x,top,size,align='left',width=None,color='0.13725,0.12157,0.12549'):
        tw=sum(a.width for a in atoms)
        if width is not None and align=='center':x+=(width-tw)/2
        elif width is not None and align=='right':x+=width-tw
        baseline=top+size
        for a in atoms:
            reference=re.fullmatch(r'〔([0-9]+)(-[A-Za-z])?〕',a.text)
            if reference:
                scale=size/11.3;label=reference[1]+(reference[2] or '')
                self.rect(x,baseline-12.655*scale,a.width,16.742*scale)
                label_width=(len(reference[1])*5.070304+(len(reference[2] or '')*4.6))*scale
                xx=x+(a.width-label_width)/2
                for ch in label:
                    self.glyph(ch,9.2*scale,xx,baseline-.798*scale,role='question-number' if ch.isdigit() else 'body',hscale=.8 if ch.isdigit() else 1)
                    xx+=(5.070304 if ch.isdigit() else 4.6)*scale
                x+=a.width;continue
            bw=sum(self.catalog.width(c,size,a.bold,self.section) for c in a.text)
            bx=x+(a.width-bw)/2
            for c in a.text:
                self.glyph(c,size,bx,baseline,a.bold,color);bx+=self.catalog.width(c,size,a.bold,self.section)
            if a.ruby:
                rs=5.6 if abs(size-11.3)<.01 else round(size*.5,1);rw=sum(self.catalog.width(c,rs,a.bold,self.section) for c in a.ruby)
                hscale=min(1,a.width/rw) if rw else 1
                # Long readings are condensed over their base, never widen it.
                advance=(a.width-rs*hscale)/(len(a.ruby)-1) if len(a.ruby)>1 else 0
                rx=x if len(a.ruby)>1 else x+(a.width-rs)/2
                for c in a.ruby:self.glyph(c,rs,rx,baseline-(13.3367 if abs(size-14.2)<.01 else 10.6223),a.bold,color,hscale=hscale);rx+=advance
            annotation=getattr(a,'annotation','')
            if annotation:
                ax=x
                for c in annotation:
                    self.glyph(c,6.4,ax,baseline+6.98,False,color);ax+=self.catalog.width(c,6.4,False,self.section)
            if a.underline:
                # Match the reference underlines, measured about 3 bp below baseline.
                underline_y=baseline+3.0
                self.rule(x,underline_y,x+a.width,underline_y,.33)
            x+=a.width
    def hanging_lines(self,text,size,first_width,rest_width,bold=False):
        atoms=measure(parse(text,bold),self.catalog,size,self.section);result=[];line=[];used=0
        for a in atoms:
            if a.text=='\n':result.append(line);line=[];used=0;continue
            width=rest_width if result else first_width
            if a.width>width+1e-5:raise ValueError('Indivisible cluster exceeds component width: '+a.text)
            if a.text==' ' and not a.underline and used+a.width>width:continue
            if line and used+a.width>width+1e-5:
                carry=[]
                if a.text and a.text[0] in CLOSE:
                    while line:
                        carry.insert(0,line.pop())
                        if carry[0].text and carry[0].text[0] not in CLOSE and not carry[0].text.isspace():break
                while line and line[-1].text and line[-1].text[-1] in OPEN:carry.insert(0,line.pop())
                if line:result.append(line)
                line=carry;used=sum(z.width for z in line)
            if not line and a.text==' ':continue
            line.append(a);used+=a.width
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
        cloze=bool(self.section=='G' and self.group and self.group.get('kind')=='cloze')
        if cloze and b.get('type')=='heading':return 11.3,float(self.gc.get('material_title_line_height',48.12)),False
        if b.get('style')=='small':
            if re.match(r'^[（(]注',b.get('text','')):return 11.3,float(self.gc.get('material_note_line_height',19.89 if cloze else 24.06)),False
            return 9.2,16.98,False
        leading=float(self.gc.get('material_line_height',19.8 if cloze else self.leading))
        return self.fs,leading,b.get('type')=='heading' or b.get('style')=='bold'
    def reading_paragraph_gap(self,b):
        if b.get('style')!='small':return 0
        if self.section=='G':
            return 20.96 if re.match(r'^[（(]注',b.get('text','')) and not getattr(self,'_last_was_note',False) else 0 if re.match(r'^[（(]注',b.get('text','')) else .25
        if re.match(r'^[（(]注',b.get('text','')):
            if getattr(self,'_last_was_note',False):return 0
            # The type-size change from 9.2 to 11.3 is part of the baseline gap.
            return 19.021 if getattr(self,'_last_material_kind',None)=='box' else 18.86
        return 2.35
    def reading_sequence_height(self,blocks,width):
        saved_note=getattr(self,'_last_was_note',False)
        saved_kind=getattr(self,'_last_material_kind',None)
        height=0
        try:
            for child in blocks:
                height+=self.estimate_block(child,width)
                self._last_was_note=bool(re.match(r'^[（(]注',child.get('text','')))
                self._last_material_kind=('note' if self._last_was_note else 'citation' if child.get('style')=='small' else child.get('type'))
        finally:self._last_was_note=saved_note;self._last_material_kind=saved_kind
        return height
    def blocks(self,blocks,x=None,width=None,tail_reserve=0):
        if self.section!='R' and not (self.section=='G' and self.group and self.group.get('kind')=='cloze'):return super().blocks(blocks,x,width)
        offset=(self.left if x is None else x)-self.left
        width=self.width if width is None else width;i=0
        while i<len(blocks):
            child=blocks[i]
            # A/B labels belong to their frames. Decide the page before either
            # element is drawn; never leave a label behind after ensure().
            if child.get('type')=='heading' and i+1<len(blocks) and blocks[i+1].get('type')=='box':
                frame=dict(blocks[i+1],_reading_ab=True)
                need=19.03+self.estimate_block(frame,width)
                self.ensure(need if need<=self.usable else 19.03+2*self.leading+16)
                self.line(self.get_lines(child.get('text',''),11.3,width,True)[0],self.left+offset,self.y,11.3)
                self.y+=19.03
                self.reading_box(frame,self.left+offset,width)
                i+=2;continue
            # Definitions can stay together without dragging the citation away
            # from the preceding article. Citations are reserved by its tail.
            is_note=bool(re.match(r'^[（(]注',child.get('text','')))
            if child.get('type')=='paragraph' and is_note:
                end=i+1
                while end<len(blocks) and blocks[end].get('type')=='paragraph' and re.match(r'^[（(]注',blocks[end].get('text','')):end+=1
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
        if self.section=='G' and self.group and self.group.get('kind')=='cloze':
            padding=float(self.gc.get('material_box_padding',11.31))
            return padding,float(self.gc.get('material_box_top_padding',24.153)),float(self.gc.get('material_box_bottom_padding',9.117)),5.105
        inset=5.64 if ab else 8.0
        top=10.702 if ab else 8.0
        children=b.get('blocks',[])
        citation=bool(children and children[-1].get('style')=='small' and children[-1].get('align')=='right')
        bottom=(6.04 if citation else 1.31) if ab else 8.0
        return inset,top,bottom,3.729 if ab else 6.0
    def reading_box(self,b,x,width):
        if any(z.get('type')=='vertical' for z in b.get('blocks',[])):return self.vertical_box(b,x,width)
        offset=x-self.left
        if self.section=='G' and self.group and self.group.get('kind')=='cloze' and not b.get('_material_box_outer'):
            outset=float(self.gc.get('material_box_outset',11.31));offset-=outset;width+=2*outset
            b=dict(b,_material_box_outer=True)
        if len(b.get('blocks',[]))==1 and b['blocks'][0].get('type')=='image':
            _,iw,_=self.image_geometry(b['blocks'][0],width-16)
            narrow=min(width,iw+16);offset+=(width-narrow)/2;width=narrow
        inset,padtop,padbottom,after=self.reading_box_padding(b)
        est=self.estimate_block(b,width)
        self.ensure(est if est<=self.usable else min(est,2*self.leading+padtop+padbottom))
        first=len(self.pages)-1;start_y=self.y
        self.y+=padtop
        self.blocks(b.get('blocks',[]),self.left+offset+inset,width-2*inset,tail_reserve=padbottom)
        self.y+=padbottom;last=len(self.pages)-1;current=self.page
        for pi in range(first,last+1):
            odd=(self.start_page+pi)%2==1
            page_left=float(self.p.get('left_odd' if odd else 'left_even',78.96 if odd else 63.63))
            top=start_y if pi==first else self.top
            bottom=self.y if pi==last else self.bottom
            self.page=self.pages[pi]
            stroke=float(self.gc.get('material_box_stroke',1.71 if self.section=='G' and self.group and self.group.get('kind')=='cloze' else .33))
            self.emit({'type':'vector','pdf':f'q .13725 .12157 .12549 RG {stroke:.5f} w {page_left+offset:.5f} {self.H-bottom:.5f} {width:.5f} {max(0,bottom-top):.5f} re S Q'})
        self.page=current;self.gap(after)
        self._last_was_note=False;self._last_material_kind='box'
    def block(self,b,x=None,width=None):
        x=self.left if x is None else x;width=self.width if width is None else width;t=b['type']
        if t in ('paragraph','heading'):
            size,leading,bold=self.paragraph_format(b)
            is_note=bool(re.match(r'^[（(]注',b.get('text','')))
            small=b.get('style')=='small'
            if self.section=='R' or (self.section=='G' and self.group and self.group.get('kind')=='cloze'):self.gap(self.reading_paragraph_gap(b))
            elif small and not is_note:self.gap(0.25)
            elif is_note and not getattr(self,'_last_was_note',False):self.gap(20.96)
            indent=11.31 if not small and not bold and self.section in ('R','G') else 0
            cloze_heading=bool(self.section=='G' and self.group and self.group.get('kind')=='cloze' and t=='heading')
            if cloze_heading:indent=0
            body_text=b.get('text','')
            if self.section=='R' and not small:body_text=re.sub(r'([①②③④⑤⑥⑦⑧⑨⑩])__(.*?)__',lambda m:'{{'+m[1]+'|__'+m[2]+'__}}',body_text)
            self.paragraph(body_text,x,width,size,leading,bold,b.get('align','center' if cloze_heading else 'left'),gap=0,indent=indent,reserve_after=b.get('_reserve_after',0))
            self._last_was_note=is_note
            self._last_material_kind='note' if is_note else 'citation' if small else t
        elif t=='separator':self.gap(24.06)
        elif t=='box' and any(z.get('type')=='vertical' for z in b.get('blocks',[])):self.vertical_box(b,x,width)
        elif t=='box' and (self.section=='R' or (self.section=='G' and self.group and self.group.get('kind')=='cloze')):self.reading_box(b,x,width)
        else:super().block(b,x,width)
    def estimate_block(self,b,width=None):
        width=width or self.width;t=b.get('type')
        if t in ('paragraph','heading'):
            size,leading,bold=self.paragraph_format(b)
            indent=11.31 if b.get('style')!='small' and not bold and self.section in ('G','R') else 0
            if self.section=='G' and self.group and self.group.get('kind')=='cloze' and t=='heading':indent=0
            ls=self.hanging_lines(b.get('text',''),size,width-indent,width,bold)
            before=self.reading_paragraph_gap(b) if self.section=='R' or (self.section=='G' and self.group and self.group.get('kind')=='cloze') else (20.96 if re.match(r'^[（(]注',b.get('text','')) and not getattr(self,'_last_was_note',False) else .25 if b.get('style')=='small' else 0)
            return len(ls)*leading+before
        if t=='separator':return 24.06
        if t=='box' and any(z.get('type')=='vertical' for z in b.get('blocks',[])):return 335
        if t=='box' and (self.section=='R' or (self.section=='G' and self.group and self.group.get('kind')=='cloze')):
            if self.section=='G' and not b.get('_material_box_outer'):width+=2*float(self.gc.get('material_box_outset',11.31))
            inset,top,bottom,after=self.reading_box_padding(b)
            return top+self.reading_sequence_height(b.get('blocks',[]),width-2*inset)+bottom+after
        return super().estimate_block(b,width)
    def chosen_columns(self,item,available,size):
        configured=self.gc.get('options_columns','auto')
        if configured!='auto':return int(configured)
        opts=item.get('options',[])
        for cols in (4,2,1):
            starts=self.option_starts(cols)
            fits=True
            for i,t in enumerate(opts):
                j=i%cols;end=starts[j+1]-11.31 if j+1<cols else self.width
                w=end-starts[j]-22.62
                if sum(a.width for a in measure(parse(t),self.catalog,size,self.section))>w:fits=False;break
            if fits:return cols
        return 1
    def option_starts(self,cols):
        if cols==4:return [16.95,118.74,243.14,367.53]
        if cols==2:return [16.95,243.14]
        return [16.95]
    def choice_metrics(self,item):
        if len(item.get('options',[]))!=4:raise ValueError('Choice must have four options: '+item.get('id',''))
        size=float(self.gc.get('font_size',self.fs));lead=float(self.gc.get('line_height',self.leading));prompt=item.get('prompt','')
        promptlines=self.hanging_lines(prompt,size,self.width-28.26,self.width-16.95)
        cols=self.chosen_columns(item,self.width,size);starts=self.option_starts(cols);oplines=[]
        for i,t in enumerate(item['options']):
            j=i%cols;end=starts[j+1]-11.31 if j+1<cols else self.width
            oplines.append(self.hanging_lines(t,size,end-starts[j]-22.62,end-starts[j]-11.31))
        rows=[max(len(oplines[i+j]) for j in range(min(cols,4-i)))*lead for i in range(0,4,cols)]
        ph=max(1,len(promptlines))*lead
        material_height=sum(self.estimate_block(b,self.width-16.95) for b in item.get('stimulus',[]))
        return {'size':size,'lead':lead,'prompt':prompt,'promptlines':promptlines,'cols':cols,'starts':starts,'oplines':oplines,'rows':rows,'ph':ph,'total':ph+sum(rows)+material_height+float(self.gc.get('question_gap',14.13))}
    def choice(self,item):
        if self.section=='L':return self.listening_choice(item)
        m=self.choice_metrics(item);self.ensure(min(m['total'],self.usable));m=self.choice_metrics(item)
        first=len(self.pages);label=self.next_label(item);b=self.y+m['size']
        if label.isascii() and label.isdigit():
            self.rect(self.left-.105,self.y+1.697,16.742,11.073)
            xx=self.left+(4.83 if len(label)==1 else 2.28)
            for ch in label:self.glyph(ch,9.2,xx,b-.828,role='question-number',hscale=.8);xx+=5.070304
        else:self.paragraph(label,size=m['size'],leading=m['lead'],bold=True)
        for i,ln in enumerate(m['promptlines']):
            self.line(ln,self.left+(28.26 if i==0 else 16.95),self.y,m['size']);self.y+=m['lead']
        if item.get('stimulus') and item.get('stimulus_position')!='after_options':self.blocks(item['stimulus'],self.left+16.95,self.width-16.95)
        for i in range(0,4,m['cols']):
            count=max(len(m['oplines'][i+j]) for j in range(min(m['cols'],4-i)));self.ensure(count*m['lead'])
            for j in range(min(m['cols'],4-i)):
                start=m['starts'][j]
                self.line(self.get_lines(str(i+j+1).translate(str.maketrans('1234','１２３４')),m['size'],24)[0],self.left+start,self.y,m['size'])
                for k,ln in enumerate(m['oplines'][i+j]):self.line(ln,self.left+start+(22.62 if k==0 else 11.31),self.y+k*m['lead'],m['size'])
            self.y+=count*m['lead']
        if item.get('stimulus') and item.get('stimulus_position')=='after_options':self.blocks(item['stimulus'],self.left+16.95,self.width-16.95)
        self.gap(float(self.gc.get('question_gap',14.13)))
        self.item_records.append({'id':item.get('id'),'source_number':item.get('source_number'),'label':plain(label),'pages':list(range(first,len(self.pages)+1)),'options':4})
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
        elif compound:base=self.y+20
        else:base=self.y+20
        option_lines=[self.hanging_lines(text,14.2,self.width-21.96,self.width-21.96) for text in item['options']]
        ink_bottom=base+26.2283+(sum(map(len,option_lines))-1)*28.35+14.2*.25
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
        if not getattr(self,'_first_group_item',False) and self.gc.get('passages_new_page',True):self.new_page()
        if item.get('label'):
            if self.section=='R':self.reading_item_label(str(item['label']))
            else:self.paragraph(str(item['label']),size=11.3,leading=24.06,gap=0)
        self._last_was_note=False
        self._last_material_kind=None
        self.blocks(item.get('stimulus',[]))
        if item.get('questions') and self.gc.get('questions_new_page',self.group.get('kind')=='cloze'):
            self.new_page()
        else:
            material_gap=float(self.gc.get('material_question_gap',24.06))
            if self.section=='R' and self._last_material_kind=='citation':material_gap=float(self.gc.get('citation_question_gap',material_gap-5.2))
            self.gap(material_gap)
        for q in item.get('questions',[]):self.choice(q)
    def reading_item_label(self,label):
        normalized=label.translate(str.maketrans('０１２３４５６７８９（）','0123456789()'))
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
        if getattr(self,'facing_started',False):
            if self.y>self.top+.1:self.new_page()
            if self.n()%2==1:self.new_page()
        self.facing_started=True;left_index=len(self.pages)
        if item.get('label'):self.reading_item_label(str(item['label']))
        for question in item.get('questions',[]):self.choice(question)
        if len(self.pages)!=left_index:raise ValueError('Facing-page questions exceed the left page; shorten them or use ordinary reading layout')
        self.new_page();right_index=len(self.pages)
        if self.gc.get('use_measured') and self.group['id'] in self.reference.components:
            try:
                page=self.reference.take_page(self.group,self.reference.components[self.group['id']]['pages'][-1],self.n(),self.gc.get('_refresh_furniture',False))
                if page.get('measured_body'):page['bands']=[copy.deepcopy(self.gc['sidebar'])] if self.gc.get('sidebar') else []
                self.pages[-1]=page;self.page=page;self.y=self.bottom
                self.component_audit[-1]['shared_reference_page']=True
                return
            except CalibrationMismatch:pass
        size,leading=self.fs,self.leading
        self.fs=float(self.gc.get('reference_font_size',9.2));self.leading=float(self.gc.get('reference_line_height',13.68))
        try:self.blocks(item.get('stimulus',[]))
        finally:self.fs,self.leading=size,leading
        if len(self.pages)!=right_index:raise ValueError('Reference material exceeds one page; simplify the material or supply it as one PDF/PNG asset')
    def listening_passage(self,item):
        if self.group['kind']=='listening_memo':
            self._listening_blocks(item.get('stimulus',[]));return
        if not getattr(self,'_first_group_item',False):self.new_page();self.y=self.top
        if item.get('label'):
            self.listen_label(str(item['label']),self.y+20)
            self.y+=40.8439-11.3
        intro=bool(getattr(self,'_first_group_item',False))
        width=float(self.gc.get('compound_intro_width' if intro else 'compound_followup_width',486.34 if intro else 475.028))
        tracking=float(self.gc.get('compound_intro_first_line_tracking',-.27007)) if intro else 0
        self._listening_blocks(item.get('stimulus',[]),min(self.width,width),tracking)
        if item.get('questions'):
            self.gap(float(self.gc.get('compound_question_gap',21.606)))
            for q in item['questions']:self.listening_choice(q)
    def _listening_instruction(self,text,width,tracking=0):
        size=11.3;indent=11.31;ratio=(11.31017+tracking)/11.31017
        if ratio<=0:raise ValueError('Listening instruction tracking must leave positive glyph advances')
        for paragraph in (p for p in str(text).splitlines() if p.strip()):
            rows=self.hanging_lines(paragraph,size,(width-indent)/ratio,width,True)
            for row,atoms in enumerate(rows):
                self.ensure(25.47);x=self.left+(indent if row==0 else 0)
                command_start=len(self.page['commands']);glyph_start=len(self.semantic_glyphs)
                self.line(atoms,x,self.y,size)
                if row==0 and ratio!=1:
                    # Source L5's opening material line is tracked slightly
                    # tighter while retaining the full original glyph shape.
                    for command in self.page['commands'][command_start:]:
                        if command['type']=='run':command['x']=x+(command['x']-x)*ratio
                        elif command['type']=='vector':command['pdf']=f'q {ratio} 0 0 1 {x*(1-ratio)} 0 cm\n'+command['pdf']+'\nQ'
                    for glyph in self.semantic_glyphs[glyph_start:]:glyph['x']=x+(glyph['x']-x)*ratio
                self.y+=25.47
    def _listening_memo(self,block):
        height=min(float(block.get('height',260)),self.usable)
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
            if block.get('type') in ('paragraph','heading'):
                self._listening_instruction(block.get('text',''),width,first_tracking)
            elif block.get('type')=='memo':self._listening_memo(block)
            else:self.block(block,self.left,width)
    def _listening_heading(self,group,config):
        title=config.get('title',group.get('title',''))
        self.glyph_text('もんだい',18,self.left,61.6801,True,role='ruby-heading')
        self.glyph_text(plain(title),36,self.left,95.5201,True,role='heading')
        self.y=112.6529
        self._listening_instruction(group.get('instruction',''),float(config.get('instruction_width',self.width)))
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
        for ci,(size,column) in enumerate(columns):
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
                vf={'、':'︑','。':'︒','「':'﹁','」':'﹂','『':'﹃','』':'﹄','（':'︵','）':'︶'}
                self.glyph(vf.get(ch,ch),size,xx,yy,a.bold if a else False,rotation=-90 if ch in 'ー―—〜～' else 0,semantic_char=ch if ch in vf else None)
                if a and a.ruby and ai==0:
                    rs=5.6;span=len(a.text)*11.31018;advance=span/len(a.ruby)
                    for i,c in enumerate(a.ruby):self.glyph(c,rs,xx+11.54,yy-5+i*advance,a.bold)
                if a and a.underline:self.rule(xx+size*1.1,yy-size*.9,xx+size*1.1,yy+size*.1)
        self.y+=h;self.gap(6.744)
        self._last_was_note=False;self._last_material_kind='vertical_box'
    def render_group(self,group,config):
        self.group=group;self.gc=config;self.section=group['id'][0];self.group_number=int(config.get('number_start',1));self.fs=float(config.get('font_size',self.p['font_size']));self.leading=float(config.get('line_height',self.p['line_height']));self.facing_started=False
        if config.get('new_page',True) or self.page is None:self.new_page()
        else:self.add_band()
        start=len(self.pages);ref=self.reference;can_measure=config.get('use_measured',True)
        # The same component resolver is called for every content set.
        if can_measure:
            try:
                current=ref.take_group(group,self.n(),config.get('_refresh_furniture',False))
                for page in current:
                    if page.get('measured_body'):
                        side=config.get('sidebar')
                        page['bands']=[copy.deepcopy(side)] if side else []
                self.pages.pop();self.pages.extend(current);self.page=self.pages[-1];self.geometry();self.y=self.bottom
                self.component_audit.append({'group':group['id'],'placement':'measured','body_pages':list(range(start,len(self.pages)+1))})
                def count(obj):
                    if isinstance(obj,dict):return (int('options' in obj and not obj.get('is_example',False)))+sum(count(v) for k,v in obj.items() if k!='options')
                    if isinstance(obj,list):return sum(count(v) for v in obj)
                    return 0
                self.number+=count(group)
                return
            except CalibrationMismatch as e:reason=str(e)
        else:reason='Custom composition configuration'
        items=group.get('items',[])
        if config.get('items') is not None:
            table={i['id']:i for i in items};items=[table[k] for k in config['items']]
        self.component_audit.append({'group':group['id'],'placement':'composed','reason':reason,'first_body_page':start})
        skip=0
        if can_measure and group['kind']=='listening_choice' and items and items[0].get('is_example'):
            try:
                page=ref.take_page(group,ref.components[group['id']]['pages'][0],self.n())
                self.pages[-1]=page;self.page=page;skip=1;self.y=self.bottom
                self.item_records.append({'id':items[0]['id'],'source_number':None,'label':'例','pages':[len(self.pages)],'options':4})
                self.component_audit[-1]['shared_intro_page']=True
            except CalibrationMismatch:pass
        if not skip:
            effective=copy.deepcopy(group)
            if config.get('title') is not None:effective['title']=config['title']
            try:
                if not can_measure:raise CalibrationMismatch('Heading configuration changed')
                commands,spec=ref.heading(effective,self.n(),self.left);self.page['commands']+=commands;self.page['_ink']=None
                if self.section=='L':
                    if group['kind']=='listening_memo':self.y=spec['first_item_baseline']-25.1744
                    else:self.y=spec['first_item_baseline']+18.8077-20
                elif group['kind'] in ('choice','word_order'):self.y=spec['first_item_baseline']+.828-self.fs
                else:self.y=spec['first_item_baseline']-self.fs
            except CalibrationMismatch:
                if self.section=='L':self._listening_heading(effective,config)
                else:self.dynamic_heading(effective,config)
        self._listen_on_page=0
        for idx,item in enumerate(items[skip:],skip):
            self._first_group_item=(idx==0)
            if group['kind']=='word_order' and item.get('is_example') and can_measure:
                try:
                    commands,baseline=ref.slice_item(group,idx,self.n(),self.left)
                    self.page['commands']+=commands;self.page['_ink']=None;self.y=baseline-self.fs
                    self.component_audit[-1]['shared_example_component']=True
                    self.item_records.append({'id':item['id'],'source_number':None,'label':item.get('label','例'),'pages':[len(self.pages)],'options':4})
                    continue
                except CalibrationMismatch:pass
            if group['kind'] in ('choice','word_order','listening_choice'):self.choice(item)
            else:self.passage(item)
    def dynamic_heading(self,group,config):
        title=config.get('title',group.get('title',''));instruction=group.get('instruction','')
        if self.section=='L':
            self.glyph_text('もんだい',18,self.left,61.6801,True,role='ruby-heading')
            self.glyph_text(plain(title),36,self.left,95.5201,True,role='heading')
            self.y=112.6529
            self.paragraph(instruction,self.left,self.width,size=11.3,leading=25.47,bold=True,indent=11.31)
            self.y+=35.606
        else:
            match=re.fullmatch(r'問題\s*([0-9０-９]{1,2})',plain(title))
            if match:
                self.glyph('問',12.8,self.left,75.1129,True)
                self.glyph('題',12.8,self.left+12.81024,75.1129,True)
                digits=match[1].translate(str.maketrans('0123456789','０１２３４５６７８９'))
                for i,ch in enumerate(digits):self.glyph(ch,12.8,self.left+(22.42048+i*6.38976 if len(digits)==2 else 25.62048),75.1129,True)
            else:self.glyph_text(plain(title),12.8,self.left,75.1129,True)
            ls=self.hanging_lines(instruction,11.3,self.width-50.88,self.width-39.57,True)
            for i,ln in enumerate(ls):self.line(ln,self.left+(50.88 if i==0 else 39.57),62.4928+i*24.06,11.3)
            self.y=62.4928+len(ls)*24.06+14.13
    def glyph_text(self,text,size,x,baseline,bold=False,role=None,hscale=1):
        for c in text:
            self.glyph(c,size,x,baseline,bold,role=role,hscale=hscale);x+=self.catalog.width(c,size,bold,self.section)*hscale
    def decorate(self):decorate(self)
