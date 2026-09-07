"""Reusable written/listening covers, independent of body calibration.

The dedicated template contains only four cover pages, their metadata bindings,
and field fitting regions. Every visible string still comes from current YAML.
Body layouts, semantic question bindings and calibration contracts are never
loaded by this provider.
"""
from pathlib import Path
import copy
import json
import re

from metadata_bindings import load_metadata, resolve_loaded
from metadata_components import resolve_metadata_components


class CoverTemplates:
    def __init__(self, profile, metadata_path):
        self.profile = Path(profile)
        self.metadata_path = Path(metadata_path)
        self.cover_template = json.loads((self.profile / 'cover-template.json').read_text())
        if self.cover_template.get('schema_version') != 1:
            raise ValueError('Cover template schema_version must be 1')
        self.asset_bindings = self.cover_template['assets']
        self.layout = {'paper': copy.deepcopy(self.cover_template['paper'])}
        self.metadata_bindings = self.cover_template['bindings']
        self.metadata = load_metadata(self.metadata_path, self.metadata_bindings)
        self.fonts = None
        self.resolved = {}
        self.ledger = []
        self.metadata_audit = []

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


    def cover(self, section, body_pages):
        """Resolve the fixed two-page design using current metadata and fonts."""
        if section not in ('V', 'L'):
            raise ValueError('Cover section must be V (written) or L (listening)')
        booklet = 'listening' if section == 'L' else 'written'
        mark_commands, mark_runs = self._cover_marks(booklet)
        pages = copy.deepcopy(self.cover_template['sections'][section]['pages'])
        bindings = self.cover_template['bindings']
        for index, page in enumerate(pages):
            if self.fonts is not None:
                page['commands'], runs, audit = resolve_metadata_components(
                    self.profile, self.metadata_path, page['commands'], self.fonts,
                    body_pages=body_pages, template=self.cover_template,
                )
                self.metadata_audit.append(audit)
            else:
                metadata = load_metadata(self.metadata_path, bindings, body_pages)
                run_ids = [command['run_id'] for command in page['commands']
                           if command['type'] == 'run']
                runs = resolve_loaded(metadata, bindings, self.metadata_path.name,
                                      run_ids=run_ids)['runs']
            self.resolved.update(runs)
            if index == 0:
                page['commands'].extend(copy.deepcopy(mark_commands))
                self.resolved.update(mark_runs)
        return pages
