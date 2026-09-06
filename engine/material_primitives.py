"""Shared material primitives: boxes, images, tables, page flow, and numbering.

All text is emitted by ComponentLayout through the common scene renderer.
"""
from pathlib import Path
import shutil
import fitz
from inline import lines,parse

DEFAULT_PAGE={'width':595,'height':842,'margin_left':78.96,'margin_right':63.63,'margin_top':62.4928,'margin_bottom':59,'font_size':11.3,'line_height':24.05996}
VERTICAL_FORMS={'、':'︑','。':'︒','「':'﹁','」':'﹂','『':'﹃','』':'﹄','（':'︵','）':'︶','(':'︵',')':'︶'}
VERTICAL_ROTATED='ー—―〜～'

class MaterialPrimitives:
    def __init__(self,catalog,blueprint,resources,out):
        self.catalog=catalog;self.bp=blueprint;self.resources=Path(resources);self.out=Path(out)
        self.p=dict(DEFAULT_PAGE,**blueprint.get('page',{}));self.W=float(self.p['width']);self.H=float(self.p['height'])
        self.left=float(self.p['margin_left']);right=self.W-float(self.p['margin_right']);self.width=right-self.left
        self.top=float(self.p['margin_top']);self.bottom=self.H-float(self.p['margin_bottom']);self.fs=float(self.p['font_size']);self.leading=float(self.p['line_height'])
        if self.width<80 or self.bottom-self.top<100:raise ValueError('Page margins leave insufficient usable space')
        self.pages=[];self.page=None;self.y=self.top;self.section='';self.group=None;self.gc={}
        self.number=int(blueprint.get('numbering',{}).get('start',1));self.group_number=1;self.item_records=[];self.assets=set();self.image_sizes={};self.semantic_glyphs=[]
        self.start_page=int(blueprint.get('page_number_start',1))

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
            shutil.copyfile(src,dest);self.assets.add(str(target))
        return target.as_posix()

    def image_geometry(self,b,width):
        name=self.asset(b['asset'])
        if name not in self.image_sizes:
            with fitz.open(self.out/name) as source:rect=source[0].rect
            self.image_sizes[name]=(rect.width,rect.height)
        intrinsic_width,intrinsic_height=self.image_sizes[name];ratio=intrinsic_width/intrinsic_height
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
            _,_,h=self.image_geometry(b,width);return min(h,self.usable)+4
        if t=='table':
            _,table_width=self.table_geometry(b,0,width)
            return sum(self.table_rows(b,table_width)[1])+6
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
            narrow=self.box_width(b,width);x+=(width-narrow)/2;width=narrow
            est=self.estimate_block(b,width)
            if est<=self.usable:self.ensure(est)
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
        widths=[width*w/sum(weights) for w in weights]
        def metric(name,default,allow_zero=False):
            raw=b.get(name,self.gc.get(name,default))
            if isinstance(raw,bool):raise ValueError(f'{name} must be a number')
            try:value=float(raw)
            except (TypeError,ValueError) as e:raise ValueError(f'{name} must be a number') from e
            if value<0 or (not allow_zero and value==0):raise ValueError(f'{name} must be positive')
            return value
        size=metric('table_font_size',self.fs*.91)
        lead=metric('table_line_height',max(size*1.8,18))
        pad_x=metric('table_cell_padding_x',5,True)
        pad_top=metric('table_cell_padding_top',4,True)
        pad_bottom=metric('table_cell_padding_bottom',6,True)
        if any(w<=2*pad_x for w in widths):raise ValueError('Table cell padding leaves no text width')
        configured_alignments=self.gc.get('table_column_alignments',{})
        if not isinstance(configured_alignments,dict):raise ValueError('table_column_alignments must map column counts to alignment lists')
        alignments=b.get('column_alignments',configured_alignments.get(n,configured_alignments.get(str(n),['left']*n)))
        if not isinstance(alignments,list) or len(alignments)!=n or any(a not in ('left','center','right') for a in alignments):
            raise ValueError('Table column alignments must provide left, center, or right for every column')
        headers=int(b.get('header_rows',0))
        header_bold=b.get('header_bold',True)
        if not isinstance(header_bold,bool):raise ValueError('Table header_bold must be true or false')
        header_alignments=b.get('header_alignments',alignments)
        if not isinstance(header_alignments,list) or len(header_alignments)!=n or any(a not in ('left','center','right') for a in header_alignments):
            raise ValueError('Table header alignments must provide left, center, or right for every column')
        prepared=[];heights=[]
        for i,row in enumerate(rows):
            cells=[self.get_lines(str(s),size,w-2*pad_x,bold=header_bold and i<headers) for s,w in zip(row,widths)]
            prepared.append(cells);heights.append(max(len(c) for c in cells)*lead+pad_top+pad_bottom)
        return (widths,heights,prepared,size,lead,alignments,header_alignments,pad_x,pad_top)

    def table_geometry(self,b,x,width):
        configured=b.get('width',width)
        if isinstance(configured,bool):raise ValueError('Table width must be a positive number')
        try:table_width=float(configured)
        except (TypeError,ValueError) as e:raise ValueError('Table width must be a positive number') from e
        if table_width<=0 or table_width>width+1e-6:raise ValueError('Table width must fit within the available space')
        align=b.get('align','left')
        if align not in ('left','center','right'):raise ValueError('Table align must be left, center, or right')
        offset=0 if align=='left' else (width-table_width)/2 if align=='center' else width-table_width
        return x+offset,table_width

    def table(self,b,x,width):
        x,width=self.table_geometry(b,x,width)
        borders=b.get('borders',True)
        if not isinstance(borders,bool):raise ValueError('Table borders must be true or false')
        widths,heights,prepared,size,lead,alignments,header_alignments,pad_x,pad_top=self.table_rows(b,width);headers=int(b.get('header_rows',0))
        header_fill=b.get('header_fill',True)
        if not isinstance(header_fill,bool):raise ValueError('Table header_fill must be true or false')
        def drawrow(i):
            h=heights[i];self.ensure(h);xx=x
            row_alignments=header_alignments if i<headers else alignments
            for ls,w,alignment in zip(prepared[i],widths,row_alignments):
                fill='.94 .94 .94' if header_fill and i<headers else None
                if fill or borders:self.rect(xx,self.y,w,h,fill=fill,stroke=borders)
                for j,ln in enumerate(ls):self.line(ln,xx+pad_x,self.y+pad_top+j*lead,size,alignment,w-2*pad_x)
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
                    yy=self.y+size*1.15+ri*size*1.04
                    drawn=VERTICAL_FORMS.get(ch,ch)
                    rotation=-90 if ch in VERTICAL_ROTATED else 0
                    self.glyph(drawn,size,xx,yy,a.bold,rotation=rotation,semantic_char=ch)
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
