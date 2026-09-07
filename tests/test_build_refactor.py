"""Focused tests for build validation, pagination, and artifact helpers."""
import json
from contextlib import redirect_stderr
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'engine'))

from build import (
    archive_inputs,insert_facing_interleaf,prepare_group,validate_group_config,
    write_build_outputs,write_scene_inputs,parse_args,output_directory,selected_layout_mode,
)


class LayoutModeTests(unittest.TestCase):
    def test_rules_are_default_and_explicit_alias_is_equivalent(self):
        default=parse_args([])
        explicit=parse_args(['--rules'])
        self.assertEqual(vars(default),vars(explicit))
        self.assertEqual(default.layout_mode,'rules')
        self.assertTrue(default.rules)
        self.assertFalse(default.precise)
        self.assertFalse(default.recompose)
        self.assertEqual(output_directory(default),ROOT/'output/rules')

    def test_legacy_modes_require_explicit_flags_and_separate_outputs(self):
        for mode in ('precise','recompose'):
            with self.subTest(mode=mode):
                args=parse_args(['--'+mode])
                self.assertEqual(selected_layout_mode(args),mode)
                self.assertFalse(args.rules)
                self.assertEqual(output_directory(args),ROOT/'output'/mode)

    def test_mode_flags_are_mutually_exclusive(self):
        for first,second in (('rules','precise'),('rules','recompose'),('precise','recompose')):
            with self.subTest(first=first,second=second):
                with redirect_stderr(StringIO()),self.assertRaises(SystemExit):
                    parse_args(['--'+first,'--'+second])

    def test_output_override_applies_to_all_modes(self):
        for flag in ([],['--rules'],['--precise'],['--recompose']):
            args=parse_args([*flag,'--output-dir','custom-output'])
            self.assertEqual(output_directory(args),Path('custom-output'))

    def test_programmatic_namespace_also_defaults_to_rules(self):
        self.assertEqual(selected_layout_mode(SimpleNamespace()),'rules')
        self.assertEqual(selected_layout_mode(SimpleNamespace(rules=False)),'rules')
        self.assertEqual(selected_layout_mode(SimpleNamespace(precise=True)),'precise')
        self.assertEqual(selected_layout_mode(SimpleNamespace(recompose=True)),'recompose')

    def test_programmatic_modes_cannot_silently_enter_the_legacy_path(self):
        with self.assertRaisesRegex(ValueError,'Unknown layout mode'):
            selected_layout_mode(SimpleNamespace(layout_mode='unexpected'))
        for args in (SimpleNamespace(precise=True,recompose=True),
                     SimpleNamespace(rules=True,precise=True),
                     SimpleNamespace(layout_mode='rules',recompose=True)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(ValueError,'mutually exclusive'):
                    selected_layout_mode(args)


class GroupConfigValidationTests(unittest.TestCase):
    def test_number_and_page_flow_fields_have_strict_types(self):
        self.assertEqual(validate_group_config({
            'number_start':2,'items_per_page':1,'new_page':False,
            'passages_new_page':True,'questions_new_page':False,
            'example_separate_page':True,'start_on':'right',
        })['number_start'],2)
        invalid=(
            ({'number_start':0},'number_start must be a positive integer'),
            ({'items_per_page':True},'items_per_page must be a positive integer'),
            ({'new_page':1},'new_page must be true or false'),
        )
        for config,message in invalid:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError,message):
                    validate_group_config(config)


class GroupPreparationTests(unittest.TestCase):
    def setUp(self):
        self.source={
            'id':'V1','kind':'choice','title':'Original',
            'items':[{'id':'q1','options':['A']},{'id':'q2','options':['B']}],
        }
        self.blueprint={
            'page':{'width':595,'height':842},
            'sidebar':{'width':20},
            'group_defaults':{'heading_size':12,'instruction_width':300},
        }
        self.options={
            'blueprint':self.blueprint,
            'component_defaults':{'choice':{'option_gap':10}},
        }

    def test_group_preparation_does_not_mutate_source_or_inject_legacy_flags(self):
        group,config=prepare_group(self.source,{'id':'V1'},**self.options)

        self.assertIsNot(group,self.source)
        self.assertEqual(config,{'id':'V1','heading_size':12,'instruction_width':300,'option_gap':10})
        group['items'].pop()
        self.assertEqual(len(self.source['items']),2)

    def test_item_selection_title_and_style_overrides(self):
        group,config=prepare_group(
            self.source,{'id':'V1','items':['q2'],'title':'Custom','option_gap':15},**self.options,
        )

        self.assertEqual(group['title'],'Custom')
        self.assertEqual([item['id'] for item in group['items']],['q2'])
        self.assertEqual(config['option_gap'],15)


class FacingInterleafTests(unittest.TestCase):
    class Layout:
        def __init__(self,start_page):
            self.start_page=start_page;self.pages=[];self.events=[]
            self.left=54;self.width=487

        def new_page(self):
            self.events.append('new_page');self.pages.append({'commands':[]})

        def image(self,spec,left,width):
            self.events.append(('image',spec,left,width))

    def test_custom_facing_layout_gets_a_generated_interleaf(self):
        layout=self.Layout(1)

        insert_facing_interleaf(
            layout,{'assets':{'reading_interleaf':'interleaf'}},
            {'id':'R7'},{'layout':'facing_pages'},
        )

        self.assertEqual(layout.events[0],'new_page')
        self.assertEqual(layout.events[1][0],'image')
        self.assertEqual(layout.events[1][1]['asset'],'interleaf')


class BuildArtifactTests(unittest.TestCase):
    def test_scene_files_keep_compact_json_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            pages=[{'commands':[{'type':'text','text':'日本語'}]}]
            write_scene_inputs(out,pages,{'run':{'text':'語'}},{'image':'/tmp/a.png'})
            scene_text=(out/'scene.json').read_text()
            self.assertTrue(scene_text.endswith('\n'))
            self.assertNotIn(': ',scene_text)
            self.assertEqual(json.loads(scene_text)['sections']['booklet']['pages'][0]['section_page'],1)
            self.assertEqual(json.loads((out/'resolved.json').read_text())['asset_files']['image'],'/tmp/a.png')

    def test_input_archive_renames_fixed_inputs_and_removes_stale_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);content=root/'content';content.mkdir()
            out=root/'out';out.mkdir();inputs=out/'inputs';inputs.mkdir()
            (content/'V.yaml').write_text('section: V\n')
            (content/'notes.txt').write_text('not an input\n')
            blueprint=root/'source-blueprint.yaml';blueprint.write_text('groups: []\n')
            metadata=root/'source-metadata.yaml';metadata.write_text('name: test\n')
            components=root/'source-components.yaml';components.write_text('components: {}\n')
            fonts=root/'source-fonts.yaml';fonts.write_text('fonts: {}\n')
            (inputs/'stale.yaml').write_text('stale: true\n')
            (inputs/'keep.txt').write_text('unmanaged\n')

            result=archive_inputs(out,content,blueprint,metadata,components,fonts)

            self.assertEqual(result,inputs)
            self.assertEqual(
                sorted(path.name for path in inputs.iterdir()),
                ['V.yaml','blueprint.yaml','components.yaml','fonts.yaml','keep.txt','metadata.yaml'],
            )
            self.assertEqual((inputs/'blueprint.yaml').read_text(),blueprint.read_text())
            archive_inputs(out,content,blueprint,metadata,components,inputs/'fonts.yaml')
            self.assertEqual((inputs/'fonts.yaml').read_text(),'fonts: {}\n')

    def test_explicit_metadata_snapshot_wins_over_content_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);content=root/'content';content.mkdir()
            out=root/'out';out.mkdir()
            (content/'metadata.yaml').write_text('source: content\n')
            blueprint=root/'blueprint.yaml';blueprint.write_text('groups: []\n')
            metadata=root/'metadata.yaml';metadata.write_text('source: explicit\n')

            archive_inputs(out,content,blueprint,metadata,None,None)

            self.assertEqual((out/'inputs/metadata.yaml').read_text(),'source: explicit\n')

    def test_report_helpers_preserve_hashes_and_sorted_font_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);inputs=out/'inputs';inputs.mkdir()
            (inputs/'blueprint.yaml').write_text('groups: []\n')
            args=SimpleNamespace(paper='paper-test',booklet='written',no_compile=True)
            layout=SimpleNamespace(component_audit={'choice':1},item_records=[{'id':'q1'}])
            reference=SimpleNamespace(ledger={'used':[]},metadata_audit={'status':'PASS'})
            resolver=SimpleNamespace(resolved_codes={'F001':{66,65}})
            fonts=SimpleNamespace(resolver=resolver)

            write_build_outputs(
                out=out,args=args,body_pages=1,pages=[{},{}],layout=layout,
                reference=reference,fonts=fonts,inputs=inputs,
                selected_data=[{'id':'V1'}],
            )

            report=json.loads((out/'build-report.json').read_text())
            self.assertFalse(report['compiled'])
            self.assertEqual(report['layout_mode'],'rules')
            self.assertFalse(report['deprecated_layout'])
            self.assertEqual(report['page_count'],2)
            self.assertEqual(list(report['inputs']),['blueprint.yaml'])
            usage=json.loads((out/'composition-font-usage.json').read_text())
            self.assertEqual(usage['fonts']['F001'],[65,66])


if __name__=='__main__':
    unittest.main()
