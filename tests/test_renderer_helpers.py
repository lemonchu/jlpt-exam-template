"""Fast contracts for the calibrated renderer's orchestration helpers."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))

import calibrated_renderer as renderer


class _FakeResolver:
    def __init__(self):
        self.fonts={
            'F':SimpleNamespace(record={'family':'native'}),
            'FB':SimpleNamespace(record={'family':'fallback','user_supplied':True}),
        }
        self.used={'F','FB'}
        self.fallback_events=[]

    def use(self,font_id,text,form,run_id,index):
        return ('FB' if text=='B' else 'F'),ord(text)

    @staticmethod
    def export(out):
        (out/'fonts.tex').write_text('font definitions\n')


class InputLoadingTests(unittest.TestCase):
    def test_loads_valid_inputs_and_clears_stale_success_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'resources';resources.mkdir()
            scene=root/'scene.json';resolved=root/'resolved.json';out=root/'out';out.mkdir()
            scene.write_text(json.dumps({'sections':{'booklet':{'pages':[]}}}))
            resolved.write_text(json.dumps({'schema_version':1,'runs':{}}))
            (out/'render-report.json').write_text('stale')
            (out/'main.pdf').write_text('stale')
            args=Namespace(resources=resources,output_dir=out,scene=scene,resolved=resolved,sections='booklet',compile=False)

            inputs=renderer._load_inputs(args)

            self.assertEqual(inputs.resources,resources.resolve())
            self.assertEqual(inputs.out,out.resolve())
            self.assertEqual(inputs.sections,['booklet'])
            self.assertEqual(inputs.bindings,{})
            self.assertFalse((out/'render-report.json').exists())
            self.assertFalse((out/'main.pdf').exists())

    def test_rejects_overlapping_paths_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            resources=Path(directory)/'resources';resources.mkdir()
            output=resources/'generated'
            args=Namespace(resources=resources,output_dir=output,resolved='unused',sections='booklet',compile=False)
            with self.assertRaisesRegex(ValueError,'must be separate'):
                renderer._load_inputs(args)
            self.assertFalse(output.exists())

    def test_preserves_resolved_and_section_validation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'resources';resources.mkdir()
            scene=root/'scene.json';resolved=root/'resolved.json'
            scene.write_text(json.dumps({'sections':{'booklet':{'pages':[]}}}))
            args=Namespace(resources=resources,output_dir=root/'out',scene=scene,resolved=resolved,sections='booklet',compile=False)

            resolved.write_text(json.dumps({'schema_version':2,'runs':{}}))
            with self.assertRaisesRegex(ValueError,'Unsupported resolved schema version'):
                renderer._load_inputs(args)
            resolved.write_text(json.dumps({'schema_version':1,'runs':[]}))
            with self.assertRaisesRegex(ValueError,'resolved.runs must be a mapping'):
                renderer._load_inputs(args)
            resolved.write_text(json.dumps({'schema_version':1,'runs':{}}))
            args.sections='booklet,booklet'
            with self.assertRaisesRegex(ValueError,'Unknown or duplicated section selection'):
                renderer._load_inputs(args)


class PageRenderingTests(unittest.TestCase):
    def test_generates_stable_tex_commands_and_fallback_details(self):
        command={
            'type':'run','run_id':'r1','slot_count':2,'font':'F','offsets':[0,7.5],
            'sx':1,'sy':2,'x':3,'y':4,'shear':0,'role':'body',
        }
        layout={'sections':{'booklet':{'pages':[{'commands':[
            {'type':'vector','pdf':'q Q'},
            {'type':'ink','rgb':[0.1,0.2,0.3]},
            command,
        ]}]}}}
        inputs=renderer._RenderInputs(Path('/resources'),Path('/output'),layout,{}, {'r1':{'text':'AB'}},['booklet'])

        pages,state=renderer._render_pages(inputs,_FakeResolver())

        self.assertEqual(pages,[[
            '\\NVector{\nq Q\n}',
            '\\NInk{0.1,0.2,0.3}',
            '\\NRun{F}{1}{2}{3}{4}{0}{\\NGetText{r1-c1}}',
            '\\NRun{FB}{1}{2}{3}{4}{7.5}{\\NGetText{r1-c2}}',
        ]])
        self.assertEqual(state.contents,[
            '\\NDefineText{r1-c1}{\\NChar{65}}',
            '\\NDefineText{r1-c2}{\\NChar{66}}',
        ])
        self.assertEqual((state.run_count,state.slot_count,state.drawn),(1,2,2))
        self.assertEqual(state.fallback_glyphs,[{
            'page':1,'run_id':'r1','index':1,'text':'B','font':'FB',
            'role':'body','user_supplied':True,
        }])

    def test_preserves_page_command_errors(self):
        base=renderer._RenderInputs(Path('/resources'),Path('/output'),{}, {}, {},['booklet'])
        with self.assertRaisesRegex(renderer.NeedReflow,'Missing semantic binding for required run missing'):
            renderer._render_page({'commands':[{'type':'run','run_id':'missing'}]},1,base,_FakeResolver(),renderer._RenderState())
        with self.assertRaisesRegex(ValueError,"Unknown calibrated command 'mystery'"):
            renderer._render_page({'commands':[{'type':'mystery'}]},1,base,_FakeResolver(),renderer._RenderState())

        command={
            'type':'run','run_id':'r1','slot_count':1,'font':'F','offsets':[0],
            'sx':1,'sy':1,'x':0,'y':0,'rotation':10,'shear':1,
        }
        inputs=renderer._RenderInputs(Path('/resources'),Path('/output'),{}, {}, {'r1':{'text':'A'}},['booklet'])
        with self.assertRaisesRegex(ValueError,'Simultaneous rotation and shear is unsupported'):
            renderer._render_page({'commands':[command]},1,inputs,_FakeResolver(),renderer._RenderState())


class ProjectWritingTests(unittest.TestCase):
    def test_writes_the_existing_latex_project_format_and_replaces_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'resources';resources.mkdir();out=root/'out';out.mkdir()
            (resources/'n1-exact.sty').write_text('style\n')
            pages_dir=out/'pages';pages_dir.mkdir();(pages_dir/'page-999.tex').write_text('stale')
            inputs=renderer._RenderInputs(resources,out,{}, {}, {},['booklet'])
            state=renderer._RenderState(contents=['\\NDefineText{r1-c1}{\\NChar{65}}'])

            renderer._write_latex_project(inputs,[['\\NRun{one}'],['\\NRun{two}']],state,_FakeResolver())

            self.assertFalse((pages_dir/'page-999.tex').exists())
            self.assertEqual((pages_dir/'page-001.tex').read_text(),'\\NRun{one}\n')
            self.assertEqual((pages_dir/'page-002.tex').read_text(),'\\NRun{two}\n')
            self.assertEqual(
                (out/'content.generated.tex').read_text(),
                '% Generated only from supplied semantic slot text. No original-content fallback.\n'
                '\\NDefineText{r1-c1}{\\NChar{65}}\n',
            )
            self.assertEqual(
                (out/'main.tex').read_text(),
                '\\documentclass{article}\n\\usepackage{n1-exact}\n'
                '\\input{content.generated.tex}\n\\begin{document}\n'
                '\\NPage{pages/page-001.tex}\n\\NPage{pages/page-002.tex}\n'
                '\\end{document}\n',
            )
            self.assertEqual((out/'n1-exact.sty').read_text(),'style\n')
            self.assertEqual((out/'fonts.tex').read_text(),'font definitions\n')
            self.assertTrue((out/'build.sh').is_file())
            if os.name!='nt':
                self.assertTrue((out/'build.sh').stat().st_mode & stat.S_IXUSR)


class CompilationTests(unittest.TestCase):
    def test_validates_and_atomically_installs_the_generated_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);candidate=out/'candidate.pdf'
            with fitz.open() as document:
                document.new_page()
                document.save(candidate)
            calls=[]

            def run(command,**kwargs):
                calls.append((command,kwargs))
                if command[0]=='xdvipdfmx':shutil.copyfile(candidate,out/'main.generated.pdf')
                return SimpleNamespace(returncode=0,stdout=command[0]+' ok\n')

            with patch.object(renderer.subprocess,'run',side_effect=run):
                renderer._compile_project(out,1)

            self.assertEqual([call[0][0] for call in calls],['xelatex','xdvipdfmx'])
            self.assertTrue((out/'main.pdf').is_file())
            self.assertFalse((out/'main.generated.pdf').exists())
            self.assertEqual(
                (out/'compile-output.txt').read_text(),
                '$ xelatex -no-pdf -interaction=nonstopmode -halt-on-error main.tex\n'
                'xelatex ok\n\n'
                '$ xdvipdfmx -o main.generated.pdf main.xdv\n'
                'xdvipdfmx ok\n',
            )

    def test_rejects_missing_glyph_output_before_pdf_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            process=SimpleNamespace(returncode=0,stdout='Missing character: U+65\n')
            with patch.object(renderer.subprocess,'run',return_value=process):
                with self.assertRaisesRegex(RuntimeError,'Compilation failed: Missing character'):
                    renderer._compile_project(out,1)
            self.assertEqual(
                (out/'compile-output.txt').read_text(),
                '$ xelatex -no-pdf -interaction=nonstopmode -halt-on-error main.tex\n'
                'Missing character: U+65\n',
            )


if __name__=='__main__':
    unittest.main()
