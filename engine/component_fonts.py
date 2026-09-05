"""One font catalog for measured and newly composed components."""
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from fontTools.ttLib import TTFont
from calibrated_renderer import Resolver
from font_overrides import install_overrides, font_role

@dataclass
class Face:
    id:str
    path:Path
    cmap:dict
    widths:dict
    upm:int
    fallback:bool
    style:str
    section:str

class ComponentFonts:
    def __init__(self,profile,font_config=None,project_root=None):
        self.compress_ruby=True;self.profile=Path(profile);self.resolver=Resolver(profile);self.fonts=[];self.faces={};self.role=None
        self.font_config_report=install_overrides(self.resolver,font_config,project_root)
        self.used=set();self.fallback_usage={};self.overrides={};self.glyphs=[]
        for fid,source in self.resolver.fonts.items():
            p=self.profile/source.record['file'];tt=TTFont(p);cm=tt.getBestCmap() or {}
            face=Face(fid,p,cm,{cp:tt['hmtx'].metrics[g][0] for cp,g in cm.items()},tt['head'].unitsPerEm,source.record.get('family')=='fallback','bold' if source.record.get('bold') else 'regular',source.record.get('section',''))
            self.fonts.append(face);self.faces[fid]=face;tt.close()
    def preferred(self,bold,section,role=None):
        role=role or self.role
        if role in ('heading','listening-number'):return 'L021'
        if role=='listening-option':return 'L003'
        if role=='question-number':return 'V002'
        if role=='footer':return 'L022' if section=='L' else 'V008'
        if role=='title':return 'V011'
        if role=='sidebar':return 'V012'
        if role=='ruby-heading':return 'L020'
        if section=='L':return 'L020' if bold else 'L024'
        return {'V':('V007','V010'),'G':('G007','G009'),'R':('R028','R031')}.get(section,('V007','V010'))[0 if bold else 1]
    @lru_cache(maxsize=None)
    def route(self,ch,bold=False,section='',role=None):
        fid=self.preferred(bold,section,role)
        if role=='question-number':
            for candidate in ['V002','V003','V004','V005','V006']:
                code=self.resolver.native(self.resolver.fonts[candidate],ch,'normal')
                if code is not None:return candidate,code
        if role=='listening-number' and ch.isascii() and ch.isdigit():
            for candidate in ['L004','L006','L008','L016']:
                code=self.resolver.native(self.resolver.fonts[candidate],ch,'normal')
                if code is not None:return candidate,code
        return self.resolver.resolve(fid,ch,'normal')
    def resolve(self,ch,bold=False,section=''):
        fid,_=self.route(ch,bold,section,self.role);return self.faces[fid]
    def width(self,ch,size,bold=False,section=''):
        if ch==' ':return size*.5
        if ch=='\u3000':return size
        fid,cp=self.route(ch,bold,section,self.role)
        f=self.faces[fid]
        preferred=self.preferred(bold,section,self.role)
        # Every available source Ryumin ASCII digit advances exactly 0.5 em.
        # Its absent 4/6/7 must not acquire proportional Noto digit advances.
        # Dedicated question numbers, footer numbers and Gothic roles keep their metrics.
        if ch.isascii() and ch.isdigit() and font_role(self.resolver.fonts[preferred].record)=='mincho_regular':
            return size*.5
        return f.widths[cp]/f.upm*size + (size*.0009 if ord(ch)>127 else 0)
    def use(self,ch,bold=False,section=''):
        f=self.resolve(ch,bold,section);self.used.add(f.id)
        if f.fallback:self.fallback_usage[ch]=self.fallback_usage.get(ch,0)+1
        return f
