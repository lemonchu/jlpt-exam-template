"""Fast regression tests for the build planner's pure helpers."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'engine'))

from build import renumber_group,select_items,validate_blueprint
from calibrated_renderer import Font,Resolver
from component_fonts import ComponentFonts
from font_overrides import COVER_ROLES,_config,_cover_warnings,_validate_tex_path
from reference_components import ReferenceComponents
from semantic_bindings import iter_questions,pointer


class PointerTests(unittest.TestCase):
    def test_root_lists_and_escaped_keys(self):
        data={'a/b':{'~key':['zero','one']}}
        self.assertIs(pointer(data,''),data)
        self.assertEqual(pointer(data,'/a~1b/~0key/1'),'one')


class QuestionTraversalTests(unittest.TestCase):
    def test_nested_questions_exclude_examples_and_option_values(self):
        example={'id':'example','is_example':True,'options':['a','b','c','d']}
        direct={'id':'direct','options':['a','b','c','d']}
        nested={'id':'passage','questions':[{'id':'nested','options':['a','b','c','d']}]}
        self.assertEqual(
            [question['id'] for question in iter_questions([example,direct,nested])],
            ['direct','nested'],
        )


class FontConfigurationTests(unittest.TestCase):
    def test_cover_roles_and_session_embolden_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fonts.yaml'
            path.write_text('schema_version: 1\nfonts:\n  cover_session: null\n  cover_symbol: null\n')
            _,fonts,faces,_=_config(path,ROOT)
        self.assertEqual(set(fonts),{'cover_session','cover_symbol'})
        self.assertEqual(faces,{})
        self.assertEqual(COVER_ROLES['cover_session']['fontspec_features'],['FakeBold=1.5'])

    def test_cover_font_identity_and_tex_path_guards(self):
        self.assertEqual(_cover_warnings('cover_session','GothicMB101Pro-Regular',400),[])
        self.assertEqual(_cover_warnings('cover_symbol','NewCenturySchlbk-Roman',500),[])
        with self.assertRaisesRegex(ValueError,'also receive FakeBold'):
            _cover_warnings('cover_session','GothicMB101Pro-Medium',505)
        with self.assertRaisesRegex(ValueError,'also receive FakeBold'):
            _cover_warnings('cover_session','GothicMB101Pro-Bold',700)
        with self.assertRaisesRegex(ValueError,'TeX-special'):
            _validate_tex_path(Path('/tmp/font#bad.otf'),'cover_symbol')

    def test_empty_cover_metadata_needs_no_cover_fonts(self):
        reference=ReferenceComponents(ROOT/'profiles/n1-original',ROOT/'content/common/metadata.yaml')
        self.assertEqual(reference._cover_marks('written'),([],{}))

    def test_enabled_cover_reports_missing_role(self):
        profile=ROOT/'profiles/n1-original'
        reference=ReferenceComponents(profile,ROOT/'content/paper-2014-12/metadata.yaml')
        reference.fonts=ComponentFonts(profile,None,ROOT)
        with self.assertRaisesRegex(ValueError,r'fonts\.cover_session'):
            reference._cover_marks('written')

    def test_user_font_export_references_source_without_copying_it(self):
        source=(ROOT/'profiles/n1-original/fonts/V/N1V-Ryumin-regular.otf').resolve()
        record={'file':str(source),'family':'cover-session','user_supplied':True,
                'fontspec_features':['FakeBold=1.5']}
        resolver=object.__new__(Resolver)
        resolver.resources=ROOT/'profiles/n1-original'
        resolver.fonts={'CF001':Font('CF001',record,{},[])}
        resolver.used={'CF001'};resolver.used_codes={'CF001':{ord('A')}}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);resolver.export(output)
            definition=(output/'fonts.tex').read_text()
            self.assertFalse((output/'fonts').exists())
            self.assertIn(f'Path={{{source.parent.as_posix()}/}}',definition)
            self.assertIn('FakeBold=1.5',definition)


class BuildPlannerTests(unittest.TestCase):
    def test_non_a4_blueprint_fails_before_layout(self):
        blueprint={'groups':[],'page':{'width':612,'height':792}}
        with self.assertRaisesRegex(ValueError,'supports only 595 x 842'):
            validate_blueprint(blueprint,'custom.yaml')

    def test_item_selection_is_ordered_and_rejects_duplicates(self):
        group={'id':'V1','items':[{'id':'one'},{'id':'two'}]}
        selected=select_items(copy.deepcopy(group),['two','one'])
        self.assertEqual([item['id'] for item in selected['items']],['two','one'])
        with self.assertRaisesRegex(ValueError,'Duplicate item selection'):
            select_items(copy.deepcopy(group),['one','one'])

    def test_cloze_renumbering_only_rewrites_printed_content(self):
        group={
            'id':'G〔41〕',
            'kind':'cloze',
            'items':[{
                'id':'passage-〔41〕',
                'stimulus':[
                    {'type':'paragraph','text':'本文〔41〕'},
                    {'type':'image','asset':'assets/〔41〕.pdf','alt':'説明〔41〕'},
                ],
                'questions':[{
                    'id':'question-〔41〕',
                    'source_number':41,
                    'prompt':'〔41〕',
                    'options':['a〔41-a〕','b','c','d'],
                }],
            }],
        }
        result=renumber_group(copy.deepcopy(group),{},'continuous',7)
        passage=result['items'][0]
        question=passage['questions'][0]
        self.assertEqual(result['id'],'G〔41〕')
        self.assertEqual(passage['id'],'passage-〔41〕')
        self.assertEqual(passage['stimulus'][0]['text'],'本文〔7〕')
        self.assertEqual(passage['stimulus'][1]['asset'],'assets/〔41〕.pdf')
        self.assertEqual(passage['stimulus'][1]['alt'],'説明〔41〕')
        self.assertEqual(question['id'],'question-〔41〕')
        self.assertEqual(question['source_number'],7)
        self.assertEqual(question['prompt'],'〔7〕')
        self.assertEqual(question['options'][0],'a〔7-a〕')

    def test_unknown_numbering_mode_fails_early(self):
        group={'id':'V1','kind':'choice','items':[]}
        with self.assertRaisesRegex(ValueError,'Unknown numbering mode'):
            renumber_group(group,{},'mystery',1)


if __name__=='__main__':
    unittest.main()
