"""Shared material primitives: boxes, images, tables, page flow, and numbering.

All text is emitted by ComponentLayout through the common scene renderer.
"""
from pathlib import Path
from math import ceil
import json, shutil, hashlib, copy, re
import fitz
from inline import lines,parse,plain,measure

DEFAULT_PAGE={'width':595,'height':842,'margin_left':78.96,'margin_right':63.63,'margin_top':62.4928,'margin_bottom':59,'font_size':11.3,'line_height':24.05996}

class MaterialPrimitives:
    def __init__(self,catalog,blueprint,resources,out):
        self.catalog=catalog;self.bp=blueprint;self.resources=Path(resources);self.out=Path(out)
        self.p=dict(DEFAULT_PAGE,**blueprint.get('page',{}));self.W=float(self.p['width']);self.H=float(self.p['height'])
        self.left=float(self.p['margin_left']);self.right=self.W-float(self.p['margin_right']);self.width=self.right-self.left
        self.top=float(self.p['margin_top']);self.bottom=self.H-float(self.p['margin_bottom']);self.fs=float(self.p['font_size']);self.leading=float(self.p['line_height'])
        if self.width<80 or self.bottom-self.top<100:raise ValueError('Page margins leave insufficient usable space')
        self.pages=[];self.page=None;self.y=self.top;self.section='';self.group=None;self.gc={};self.bands=[]
        self.number=int(blueprint.get('numbering',{}).get('start',1));self.group_number=1;self.item_records=[];self.assets={};self.warnings=[];self.semantic_glyphs=[]
        self.components=blueprint.get('components',{});self.start_page=int(blueprint.get('page_number_start',1))

    @property
    def usable(self):return self.bottom-self.top

    def n(self):return self.start_page+len(self.pages)-1

    def ensure(self,height):
        if height>self.usable+1e-6:raise ValueError(f'An unbreakable element is {height:.1f} bp tall; usable page height is {self.usable:.1f} bp')
        if self.page is None:self.new_page()
        elif self.y+height>self.bottom+1e-6:self.new_page()

    def gap(self,height):
        if self.page is None:self.new_page()
        self.y=min(self.y+height,self.bottom)

    def rule(self,x1,y1,x2,y2,width=.33,color='.13725 .12157 .12549'):
        self.emit('\\FlowVector{q %s RG %.5f w %.5f %.5f m %.5f %.5f l S Q}'%(color,width,x1,self.H-y1,x2,self.H-y2))

    def rect(self,x,y,w,h,fill=None,stroke=True):
        ops='q .13725 .12157 .12549 RG .33 w '
        if fill:ops+=fill+' rg '
        ops+='%.5f %.5f %.5f %.5f re %s Q'%(x,self.H-y-h,w,h,'B' if fill and stroke else 'f' if fill else 'S')
        self.emit('\\FlowVector{'+ops+'}')

    def get_lines(self,text,size=None,width=None,bold=False):
        return lines(text,self.catalog,size or self.fs,width or self.width,self.section,bold)

    def asset(self,name):
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError(f'Unsafe asset path: {name}')
        if rel.parts and rel.parts[0]=='assets':rel=Path(*rel.parts[1:])
        src=(self.resources/'assets'/rel).resolve()
        if not src.is_relative_to((self.resources/'assets').resolve()) or not src.is_file():raise FileNotFoundError(f'Asset unavailable: {name}')
        target=Path('assets')/rel;dest=self.out/target;dest.parent.mkdir(parents=True,exist_ok=True)
        if str(target) not in self.assets:
            shutil.copyfile(src,dest);self.assets[str(target)]=hashlib.sha256(src.read_bytes()).hexdigest()
        with fitz.open(src) as doc:r=doc[0].rect
        return target.as_posix(),r.width/r.height

    def image_geometry(self,b,width):
        name,ratio=self.asset(b['asset'])
        with fitz.open(self.out/name) as source:intrinsic_width=source[0].rect.width
        w=min(width,float(b.get('width',self.gc.get('image_max_width',intrinsic_width))))
        h=float(b.get('height',w/ratio))
        return name,w,h

    def image(self,b,x,width):
        name,w,h=self.image_geometry(b,width)
        if h>self.usable:w*=self.usable/h;h=self.usable
        self.ensure(h+4);left=x+(width-w)/2
        self.emit('\\FlowImage{%s}{%.5f}{%.5f}{%.5f}{%.5f}'%(name,w,h,left,self.H-self.y-h));self.y+=h+4

    def box_width(self,b,width):
        children=b.get('blocks',[])
        if any(child.get('type')=='vertical' for child in children):return min(width,float(self.gc.get('vertical_width',245)))
        if len(children)==1 and children[0].get('type')=='image':
            _,iw,_=self.image_geometry(children[0],width-16);return min(width,iw+16)
        return width

    def blocks(self,blocks,x=None,width=None):
        x=self.left if x is None else x;width=self.width if width is None else width;i=0
        while i<len(blocks):
            b=blocks[i]
            if b.get('type')=='paragraph' and b.get('style')=='small':
                end=i+1
                while end<len(blocks) and blocks[end].get('type')=='paragraph' and blocks[end].get('style')=='small':end+=1
                height=sum(self.estimate_block(z,width) for z in blocks[i:end])
                if height<=self.usable:self.ensure(height)
                for child in blocks[i:end]:self.block(child,x,width)
                i=end
            else:self.block(b,x,width);i+=1

    def estimate_block(self,b,width=None):
        width=width or self.width;t=b.get('type')
        if t in ('paragraph','heading'):
            size,leading,bold=self.paragraph_format(b)
            return self.paragraph_height(b.get('text',''),width,size,leading,bold)+4
        if t=='box':return sum(self.estimate_block(z,self.box_width(b,width)-16) for z in b.get('blocks',[]))+22
        if t=='memo':return min(float(b.get('height',260)),self.usable)
        if t=='image':
            _,w,h=self.image_geometry(b,width);return min(h,self.usable)+4
        if t=='table':return sum(self.table_rows(b,width)[1])+6
        if t=='vertical':return min(float(b.get('column_height',self.gc.get('vertical_column_height',280))),self.usable)+18
        if t=='separator':return 16
        raise ValueError(f'Unknown stimulus block type {t!r}')

    def block(self,b,x=None,width=None):
        x=self.left if x is None else x;width=self.width if width is None else width;t=b.get('type')
        if t in ('paragraph','heading'):
            size,leading,bold=self.paragraph_format(b)
            if b.get('label'):self.paragraph(str(b['label']),x,width,bold=True,gap=1)
            self.paragraph(b.get('text',''),x,width,size=size,leading=leading,bold=bold,align=b.get('align','left'),gap=4)
        elif t=='image':self.image(b,x,width)
        elif t=='separator':self.ensure(16);self.rule(x,self.y+8,x+width,self.y+8);self.y+=16
        elif t=='memo':
            h=min(float(b.get('height',260)),self.usable)
            self.ensure(h);self.paragraph(b.get('label','－メモ－'),x,width,align='center');self.y+=max(0,h-max(self.leading,self.fs*1.82))
        elif t=='box':
            if any(child.get('type')=='vertical' for child in b.get('blocks',[])):
                narrow=min(width,float(self.gc.get('vertical_width',245)))
                x+=(width-narrow)/2;width=narrow
            elif len(b.get('blocks',[]))==1 and b['blocks'][0].get('type')=='image':
                _,image_width,_=self.image_geometry(b['blocks'][0],width-16)
                narrow=min(width,image_width+16);x+=(width-narrow)/2;width=narrow
            est=self.estimate_block(b,width)
            under_heading=getattr(self,'_flow_initial_page_ref',None)==id(self.page)
            # The first passage may start below its group heading and continue
            # on the next page. Do not let its enclosing box undo that decision.
            if est<=self.usable and not (under_heading and est>self.bottom-self.y):self.ensure(est)
            else:self.ensure(min(est,2*self.leading+16))
            starts={len(self.pages)-1:self.y};self.y+=8
            self.blocks(b.get('blocks',[]),x+8,width-16)
            self.y+=8;last=len(self.pages)-1
            # Every page segment has its own enclosing rectangle; text may continue naturally.
            current=self.page
            for pi in range(min(starts),last+1):
                top=starts.get(pi,self.top);bottom=self.y if pi==last else self.bottom
                self.page=self.pages[pi];self.rect(x,top,width,max(0,bottom-top))
            self.page=current;self.gap(6)
        elif t=='table':self.table(b,x,width)
        elif t=='vertical':self.vertical(b,x,width)
        else:raise ValueError(f'Unknown stimulus block type {t!r}')

    def table_rows(self,b,width):
        rows=b.get('rows',[])
        if not rows or not all(isinstance(r,list) for r in rows):raise ValueError('Table rows must be a non-empty list of lists')
        n=max(map(len,rows))
        if any(len(r)!=n for r in rows):raise ValueError('All table rows must contain the same number of cells')
        configured=self.gc.get('table_column_widths',{})
        if not isinstance(configured,dict):raise ValueError('table_column_widths must map column counts to weight lists')
        weights=b.get('column_widths',configured.get(n,configured.get(str(n),[1]*n)))
        if len(weights)!=n or min(weights)<=0:raise ValueError('Invalid table column widths')
        widths=[width*w/sum(weights) for w in weights];size=self.fs*.91;lead=max(size*1.8,18)
        prepared=[];heights=[]
        for i,row in enumerate(rows):
            cells=[self.get_lines(str(s),size,w-10,bold=i<int(b.get('header_rows',0))) for s,w in zip(row,widths)]
            prepared.append(cells);heights.append(max(len(c) for c in cells)*lead+10)
        return (widths,heights,prepared,size,lead)

    def table(self,b,x,width):
        widths,heights,prepared,size,lead=self.table_rows(b,width);headers=int(b.get('header_rows',0))
        def drawrow(i):
            h=heights[i];self.ensure(h);xx=x
            for ls,w in zip(prepared[i],widths):
                self.rect(xx,self.y,w,h,fill='.94 .94 .94' if i<headers else None)
                for j,ln in enumerate(ls):self.line(ln,xx+5,self.y+4+j*lead,size)
                xx+=w
            self.y+=h
        for i in range(len(prepared)):
            if self.page is None:self.new_page()
            if self.y+heights[i]>self.bottom and i>=headers:
                self.new_page()
                if sum(heights[:headers])+heights[i]>self.usable:raise ValueError('Table header plus row exceeds page')
                for hi in range(headers):drawrow(hi)
            drawrow(i)
        self.gap(6)

    def vertical(self,b,x,width):
        size=float(b.get('font_size',self.fs));pitch=size*1.75;column_height=min(float(b.get('column_height',self.gc.get('vertical_column_height',280))),self.usable-12)
        cells=max(1,int(column_height/(size*1.04)));maxcols=max(1,int(width/pitch));atoms=parse(b.get('text',''))
        cols=[];col=[]
        for atom in atoms:
            if atom.text=='\n':
                if col:cols.append(col);col=[]
                continue
            if atom.ruby and len(col)+len(atom.text)>cells and col:cols.append(col);col=[]
            # Ruby bases remain adjacent within a column; readings follow along its right edge.
            for i,ch in enumerate(atom.text):
                if len(col)>=cells:cols.append(col);col=[]
                col.append((ch,atom,i))
        if col:cols.append(col)
        for start in range(0,len(cols),maxcols):
            batch=cols[start:start+maxcols];h=max(map(len,batch))*size*1.04+12
            self.ensure(h)
            for ci,column in enumerate(batch):
                xx=x+(width+len(batch)*pitch)/2-size-(ci*pitch)
                for ri,(ch,a,ai) in enumerate(column):
                    yy=self.y+size*1.15+ri*size*1.04;dx=0;dy=0;rot=0
                    vertical_forms={'、':'︑','。':'︒','「':'﹁','」':'﹂','『':'﹃','』':'﹄','（':'︵','）':'︶','(':'︵',')':'︶'}
                    drawn=vertical_forms.get(ch,ch)
                    if ch in 'ー—―〜～':rot=-90
                    self.glyph(drawn,size,xx+dx,yy+dy,a.bold,rotation=rot,semantic_char=ch)
                    if a.underline:self.rule(xx+size*1.13,yy-size*.9,xx+size*1.13,yy+size*.05)
                    if a.ruby and ai==0:
                        span=len(a.text)*size*1.04;rs=size*.48
                        for rj,rc in enumerate(a.ruby):self.glyph(rc,rs,xx+size*1.1,yy-size*.65+rj*span/max(len(a.ruby),1),a.bold)
            self.y+=h;self.gap(6)

    def next_label(self,item):
        if item.get('label') is not None:return str(item['label'])
        if item.get('is_example'):return '例'
        mode=self.gc.get('numbering',self.bp.get('numbering',{}).get('mode','continuous'))
        if self.group['kind'].startswith('listening_'):mode='per_group'
        if mode=='source':num=item.get('source_number',self.number)
        elif mode=='per_group':num=self.group_number
        elif mode=='continuous':num=self.number
        else:raise ValueError(f'Unknown numbering mode {mode!r}')
        self.number+=1;self.group_number+=1
        return str(num)+'｜番《ばん》' if self.group['kind'].startswith('listening_') else str(num)
