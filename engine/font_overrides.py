"""Optional complete fonts and one strict font policy for composition and rendering.

Call ``install_overrides`` on every Resolver, including when config_path is None.
Native source glyphs stay first, then other source subsets of the same face,
then the bundled sample subset of that face. A configured complete font is used
only for a missing glyph; a different source face is never substituted.

Configuration paths are relative to project_root; absolute font paths also work.
User fonts remain at their configured paths. Generated LaTeX projects reference
those paths while xdvipdfmx embeds the required glyphs in the final PDF, so no
standalone copy or subset of a user-supplied font is left in the output.
"""
from pathlib import Path
import hashlib
import sys

import yaml
from fontTools.ttLib import TTFont, TTLibError

TEXT_ROLES = ('mincho_regular', 'mincho_bold', 'gothic_regular', 'gothic_bold')
COVER_ROLES = {
    # The reference uses Gothic MB101 R with a modest synthetic embolden.
    'cover_session': {'id': 'CF001', 'family': 'cover-session', 'fontspec_features': ['FakeBold=1.5']},
    'cover_symbol': {'id': 'CF002', 'family': 'cover-symbol', 'fontspec_features': []},
}
ROLES = TEXT_ROLES + tuple(COVER_ROLES)


def font_role(record):
    """Return a body mincho/gothic role; custom and cover fonts have none."""
    family = record.get('fallback_family') if record.get('family') == 'fallback' else record.get('family')
    if family not in ('mincho', 'gothic'):
        return None
    return family + ('_bold' if record.get('bold', False) else '_regular')


def _fallback_family(record):
    if record.get('fallback_family') in ('mincho', 'gothic'):
        return record['fallback_family']
    name = (record.get('name', '') + ' ' + record.get('file', '')).lower()
    if any(s in name for s in ('notoserif', 'sourcehanserif', 'ryumin')):
        return 'mincho'
    if any(s in name for s in ('notosans', 'sourcehansans', 'droidsans', 'shingo', 'gothic')):
        return 'gothic'
    return None


def _font_name(record):
    # The extracted source catalog uses the same face name across V/G/R/L.
    return record.get('name', '').lower()


def _validate_tex_path(path, role):
    unsafe = sorted(set(path.as_posix()) & set('#%{}\\$&^~'))
    if unsafe or any(ord(char) < 32 for char in path.as_posix()):
        detail = ''.join(unsafe) or 'control character'
        raise ValueError(f'Font path for {role} contains TeX-special characters ({detail}); rename or move the file')


def _cover_warnings(role, font_name, weight):
    normalized = ''.join(char for char in font_name.lower() if char.isalnum())
    if role == 'cover_session':
        if weight is not None and weight >= 500:
            raise ValueError('fonts.cover_session must use Gothic MB101 Pro R; a medium or bold face would also receive FakeBold')
        return ([] if 'gothicmb101' in normalized and 'regular' in normalized else
                [f'cover_session: expected GothicMB101Pro-Regular, got {font_name}'])
    if role == 'cover_symbol':
        expected = ('newcenturyschlbkroman' in normalized or 'c059roman' in normalized)
        return [] if expected else [f'cover_symbol: expected NewCenturySchlbk-Roman or C059-Roman, got {font_name}']
    return []


def _config(config_path, project_root):
    if config_path is None:
        return None, {}, {}, None
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f'Font configuration does not exist: {path}')
    try:
        raw = path.read_text(encoding='utf-8')
        data = yaml.safe_load(raw)
    except (OSError, UnicodeError, yaml.YAMLError) as e:
        raise ValueError(f'Cannot read font configuration {path}: {e}') from e
    if not isinstance(data, dict):
        raise ValueError(f'Font configuration {path} must be a mapping with schema_version, fonts, and/or faces')
    unknown_top = set(data) - {'schema_version', 'fonts', 'faces'}
    if unknown_top:
        raise ValueError(f'Unknown font configuration keys in {path}: {sorted(unknown_top)}')
    if data.get('schema_version', 1) != 1:
        raise ValueError(f'Unsupported font configuration schema_version in {path}; expected 1')
    fonts = data.get('fonts', {})
    if not isinstance(fonts, dict):
        raise ValueError(f'fonts must be a mapping in {path}')
    unknown = set(fonts) - set(ROLES)
    if unknown:
        raise ValueError(f'Unknown font roles in {path}: {sorted(unknown)}. Supported roles: {", ".join(ROLES)}')
    for role, value in fonts.items():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f'{path}: fonts.{role} must be an OTF/TTF file path or null')
    faces = data.get('faces', {})
    if not isinstance(faces, dict):
        raise ValueError(f'faces must be a mapping in {path}')
    for name, value in faces.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'{path}: faces keys must be exact source font names')
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f'{path}: faces.{name} must be an OTF/TTF file path or null')
    return path, fonts, faces, hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _register(resolver, role, value, project_root, *, fid=None, source_face=None):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    _validate_tex_path(path, role)
    if not path.is_file():
        raise ValueError(f'Font for {role} does not exist: {path}. Relative font paths are resolved from {project_root}')
    if path.suffix.lower() not in ('.otf', '.ttf'):
        raise ValueError(f'Font for {role} must be an individual .otf or .ttf face: {path}. Export a single face from a collection before using it here')
    try:
        tt = TTFont(path)
        cmap = {cp: glyph for cp, glyph in (tt.getBestCmap() or {}).items() if glyph != '.notdef'}
        if not cmap or 'head' not in tt or 'hmtx' not in tt:
            raise ValueError('font has no usable Unicode cmap or horizontal metrics')
        postscript_name = tt['name'].getDebugName(6) if 'name' in tt else path.stem
        weight = int(tt['OS/2'].usWeightClass) if 'OS/2' in tt else None
        tt.close()
    except (OSError, TTLibError, ValueError, KeyError) as e:
        raise ValueError(f'Cannot load font for {role} from {path}: {e}') from e
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    fid = fid or 'UF%03d' % (ROLES.index(role) + 1)
    cover = COVER_ROLES.get(role)
    if cover:
        family = cover['family']
        bold = False
    else:
        family, weight_role = role.rsplit('_', 1)
        bold = weight_role == 'bold'
    record = {
        'file': str(path), 'name': postscript_name or path.stem,
        'family': family if cover else 'fallback', 'bold': bold,
        'section': '', 'priority': -100, 'font_role': role, 'user_supplied': True,
        'sha256': digest, 'weight_class': weight,
    }
    if cover:
        record['fontspec_features'] = cover['fontspec_features']
    else:
        record['fallback_family'] = family
    if source_face is not None:
        record['source_face'] = source_face
    warnings = _cover_warnings(role, record['name'], weight) if cover else []
    font_type = type(next(iter(resolver.fonts.values())))
    resolver.fonts[fid] = font_type(fid, record, cmap, [])
    if not cover and weight is not None and ((weight_role == 'bold' and weight < 600) or (weight_role == 'regular' and weight >= 600)):
        warnings.append(f'{role}: selected font reports OS/2 weight {weight}; verify that this is the intended face')
    return {'id': fid, 'role': role, 'source_face': source_face,
            'source': str(path),
            'font_name': record['name'], 'sha256': digest, 'unicode_count': len(cmap),
            'weight_class': weight, 'fontspec_features': record.get('fontspec_features', []),
            'warnings': warnings}


def _glyph_error(resolver, message):
    # Works both when calibrated_renderer is imported and run as __main__.
    module = sys.modules.get(type(resolver).__module__)
    error_type = getattr(module, 'GlyphError', ValueError)
    return error_type(message)


def _validate_text(resolver, text):
    if not isinstance(text, str) or not text:
        raise _glyph_error(resolver, 'Every semantic slot must supply non-empty text')
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD:
            raise _glyph_error(resolver, 'Private-use codepoints are not accepted as semantic text; supply the character and generic form')
        if cp < 32 and ch not in ' \t':
            raise _glyph_error(resolver, f'Control code U+{cp:04X} is not semantic text')


def _resolve(resolver, fontid, text, form='normal'):
    _validate_text(resolver, text)
    if text.isspace():
        return None, None
    if fontid not in resolver.fonts:
        raise _glyph_error(resolver, f'Unknown font id {fontid}; use the same font configuration for composition and scene rendering')
    original = resolver.fonts[fontid]
    code = resolver.native(original, text, form)
    if code is not None:
        resolver.resolved_codes.setdefault(fontid, set()).add(code)
        return fontid, code
    role = font_role(original.record)
    # A composed scene can already name an XF font. Retain its source identity
    # when resolving a later missing glyph rather than treating its file name as
    # a new source face.
    source_face = original.record.get('source_face', original.record.get('name', ''))
    pool = [f for f in resolver.fonts.values() if f.id != fontid]
    pool = [f for f in pool if not f.record.get('source_face')
            or f.record['source_face'] == source_face]
    if role is None:
        # EdiF symbols/digits remain in their semantic, visually checked font pool.
        pool = [f for f in pool if f.record.get('family') == original.record.get('family')
                and f.record.get('bold', False) == original.record.get('bold', False)]
    else:
        # The public exact profile never fills a missing character with a
        # different original face, even when the family and weight match.
        pool = [f for f in pool if font_role(f.record) == role
                and (f.record.get('source_face') == source_face
                     or (f.record.get('family') != 'fallback'
                         and _font_name(f.record) == source_face.lower()))]

    def rank(font):
        record = font.record
        native = record.get('family') != 'fallback'
        same_face = native and _font_name(record) == source_face.lower()
        targeted = record.get('user_supplied') and record.get('source_face') == source_face
        tier = (0 if same_face else 1 if record.get('bundled_sample') else 2 if targeted
                else 3 if record.get('user_supplied') else 4 if native else 5)
        return (tier, record.get('section') != original.record.get('section'), record.get('priority', 1), font.id)

    for candidate in sorted(pool, key=rank):
        code = resolver.native(candidate, text, form)
        if code is not None:
            resolver.resolved_codes.setdefault(candidate.id, set()).add(code)
            return candidate.id, code
    configured_role = original.record.get('font_role')
    if configured_role in COVER_ROLES:
        raise _glyph_error(resolver, f'Configured fonts.{configured_role} does not cover {text!r} with form={form!r}')
    wanted = role or original.record.get('family', 'unknown')
    raise _glyph_error(resolver, f'No glyph covers {text!r} with form={form!r} in font role {wanted}; '
                     f'original font was {fontid} ({source_face}). Configure its matching complete font '
                     'under faces in fonts.yaml; a different typeface will not be substituted')


def install_overrides(resolver, config_path=None, project_root=None):
    """Install strict routing and optional full fonts on an existing Resolver.

    Returns a JSON-serializable report. Call once immediately after constructing
    Resolver, before glyph use. This same entry point is used by ComponentFonts
    and must also be called by the final scene renderer. It does not change the
    source font catalog or any original font file. With config_path=None, strict
    family/weight fallback is still installed; no config file is auto-loaded.
    """
    root = Path(project_root).resolve() if project_root is not None else resolver.resources.resolve().parents[1]
    config, values, faces, config_sha = _config(config_path, root)
    key = (str(root), str(config) if config else None, config_sha)
    if getattr(resolver, '_font_override_key', None) == key:
        return resolver.font_override_report
    if getattr(resolver, 'used', None):
        raise ValueError('Install font configuration before resolving/emitting glyphs; an in-use font catalog cannot be replaced')
    # Remove entries from an earlier installation on an unused Resolver.
    for fid in list(resolver.fonts):
        if resolver.fonts[fid].record.get('user_supplied'):
            del resolver.fonts[fid]
    for font in resolver.fonts.values():
        if font.record.get('family') == 'fallback':
            font.record['fallback_family'] = _fallback_family(font.record)
    native_faces = {}
    for font in resolver.fonts.values():
        if font.record.get('family') != 'fallback':
            native_faces.setdefault(font.record.get('name', ''), set()).add(font_role(font.record))
    unknown_faces = set(faces) - set(native_faces)
    if unknown_faces:
        raise ValueError(f'Unknown source font names in {config}: {sorted(unknown_faces)}; '
                         'faces keys must exactly match native font-catalog names')
    for name in faces:
        roles = native_faces[name]
        if len(roles) != 1 or None in roles:
            raise ValueError(f'Source face {name!r} has incompatible or unsupported font roles: '
                             f'{sorted(str(role) for role in roles)}; '
                             'targeted complete fonts require one mincho/gothic family and weight')
    registered = [_register(resolver, role, values[role], root,
                            fid=COVER_ROLES[role]['id'] if role in COVER_ROLES else None)
                  for role in ROLES if values.get(role)]
    for index, name in enumerate(sorted(faces), 1):
        if faces[name]:
            role = next(iter(native_faces[name]))
            registered.append(_register(resolver, role, faces[name], root,
                                        fid=f'XF{index:03d}', source_face=name))
    resolver.resolved_codes = {}
    resolver._resolve_impl = lambda fontid, text, form='normal': _resolve(resolver, fontid, text, form)
    resolver.resolve.cache_clear()
    available = {}
    for role in TEXT_ROLES:
        available[role] = [fid for fid, font in resolver.fonts.items()
                           if font.record.get('family') == 'fallback' and font_role(font.record) == role]
    report = {'schema_version': 1, 'policy': 'native-then-same-face-then-sample-subset-then-targeted-font',
              'config': str(config) if config else None, 'config_sha256': config_sha,
              'project_root': str(root), 'registered_fonts': registered,
              'fallback_fonts_by_role': available, 'cross_family_fallback': False,
              'cross_weight_fallback': False, 'source_catalog_modified': False,
              'bundled_sample_fonts': [fid for fid, f in resolver.fonts.items() if f.record.get('bundled_sample')],
              'warnings': [w for r in registered for w in r['warnings']]}
    resolver._font_override_key = key
    resolver.font_override_report = report
    return report
