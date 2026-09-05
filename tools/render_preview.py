#!/usr/bin/env python3
"""Render every PDF page for visual checking: PDF path, output directory, [dpi]."""
import sys,math
from pathlib import Path
import fitz
from PIL import Image,ImageDraw
pdf=Path(sys.argv[1]);out=Path(sys.argv[2]);dpi=int(sys.argv[3]) if len(sys.argv)>3 else 144
out.mkdir(parents=True,exist_ok=True);doc=fitz.open(pdf);cols=4;cw=240;ch=365
sheet=Image.new('RGB',(cols*cw,math.ceil(len(doc)/cols)*ch),'#dddddd');draw=ImageDraw.Draw(sheet)
for i,page in enumerate(doc):
    pix=page.get_pixmap(dpi=dpi,alpha=False);path=out/f'page-{i+1:02}.png';pix.save(path)
    with Image.open(path) as im:
        im.load();im.thumbnail((cw-16,ch-28));x=(i%cols)*cw+8;y=(i//cols)*ch+8;sheet.paste(im,(x,y));draw.text((x,y+ch-28),str(i+1),fill='black')
sheet.save(out/'contact.png')
print(out/'contact.png')
