"""Font catalog and metrics shared by layout and fixed templates."""
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from fontTools.ttLib import TTFont
from calibrated_renderer import Resolver
from font_overrides import install_overrides, font_role

@dataclass
class Face:
    widths:dict
    upm:int

class ComponentFonts:
    def __init__(self,profile,font_config=None,project_root=None):
        self.compress_ruby=True;profile=Path(profile);self.resolver=Resolver(profile);self.faces={}
        self.font_config_report=install_overrides(self.resolver,font_config,project_root)
        for fid,source in self.resolver.fonts.items():
            tt=TTFont(profile/source.record['file']);cmap=tt.getBestCmap() or {}
            self.faces[fid]=Face({cp:tt['hmtx'].metrics[g][0] for cp,g in cmap.items()},tt['head'].unitsPerEm);tt.close()
    def preferred(self,bold,section,role=None):
        if role in ('heading','listening-number'):return 'L021'
        if role=='listening-option':return 'L003'
        if role=='question-number':return 'V002'
        if role=='footer':return 'L022' if section=='L' else 'V008'
        if role=='title':return 'V011'
        if role=='sidebar':return 'V012'
        if role=='ruby-heading':return 'L020'
        if section=='L':return 'L020' if bold else 'L024'
        return {'V':('V007','V010'),'G':('G007','G009'),'R':('R028','R031')}.get(section,('V007','V010'))[0 if bold else 1]
    def configured(self,role):
        matches=[fid for fid,font in self.resolver.fonts.items() if font.record.get('font_role')==role]
        if len(matches)!=1:
            raise ValueError(f'Optional cover marks require fonts.{role} in fonts.yaml')
        return matches[0]
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
    def width(self,ch,size,bold=False,section='',role=None):
        if ch==' ':return size*.5
        if ch=='\u3000':return size
        fid,cp=self.route(ch,bold,section,role)
        f=self.faces[fid]
        preferred=self.preferred(bold,section,role)
        # Every available source Ryumin ASCII digit advances exactly 0.5 em.
        # Its absent 4/6/7 must not acquire proportional Noto digit advances.
        # Dedicated question numbers, footer numbers and Gothic roles keep their metrics.
        if ch.isascii() and ch.isdigit() and font_role(self.resolver.fonts[preferred].record)=='mincho_regular':
            return size*.5
        return f.widths[cp]/f.upm*size + (size*.0009 if ord(ch)>127 else 0)
