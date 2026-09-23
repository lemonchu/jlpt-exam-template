"""Focused tests for low-level material and inline helpers."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))

from inline import measure,parse
from component_layout import ComponentLayout
from geometry import CLOZE_BOX
from material_primitives import MaterialPrimitives


class FixedCatalog:
    compress_ruby=True

    @staticmethod
    def width(char,size,bold=False,section=''):
        return size


class MaterialPrimitiveTests(unittest.TestCase):
    def test_image_geometry_stages_and_measures_asset_with_one_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'resources';output=root/'output'
            (resources/'assets').mkdir(parents=True);output.mkdir()
            source=resources/'assets'/'diagram.pdf'
            with fitz.open() as document:
                document.new_page(width=120,height=60)
                document.save(source)

            primitive=object.__new__(MaterialPrimitives)
            primitive.resources=resources;primitive.out=output
            primitive.assets=set();primitive.image_sizes={};primitive.gc={}
            original_open=fitz.open
            with patch('material_primitives.fitz.open',wraps=original_open) as open_pdf:
                geometry=primitive.image_geometry({'asset':'diagram.pdf','width':80},100)
                repeated=primitive.image_geometry({'asset':'diagram.pdf','width':60},100)

            self.assertEqual(geometry,('assets/diagram.pdf',80.0,40.0))
            self.assertEqual(repeated,('assets/diagram.pdf',60.0,30.0))
            self.assertEqual(open_pdf.call_count,1)
            self.assertTrue((output/'assets'/'diagram.pdf').is_file())
            self.assertEqual(primitive.assets,{'assets/diagram.pdf'})


class InlineReferenceTests(unittest.TestCase):
    def test_reference_box_token_is_shared_by_parse_and_measure(self):
        atoms=parse('前〔12-A〕。後')
        self.assertEqual([atom.text for atom in atoms],['前','〔12-A〕','。','後'])

        measured=measure(atoms,FixedCatalog(),11.3)
        expected=(CLOZE_BOX.width+CLOZE_BOX.suffix_width
                  +CLOZE_BOX.margin+CLOZE_BOX.closing_margin)
        self.assertAlmostEqual(measured[1].width,expected)

    def test_split_reference_suffix_clears_the_last_digit_cell_at_each_scale(self):
        class LabelCatalog(FixedCatalog):
            @staticmethod
            def width(char,size,bold=False,section='',role=None):
                return size

        def draw(text,size):
            layout=object.__new__(ComponentLayout)
            layout.catalog=LabelCatalog();layout.section='G'
            drawn=[];frames=[]
            def glyph(char,glyph_size,x,baseline,*args,role=None,hscale=1,**kwargs):
                drawn.append((char,x,x+glyph_size*hscale))
            layout.glyph=glyph;layout.rect=lambda *args:frames.append(args)
            layout.line(measure(parse(text),layout.catalog,size),0,0,size)
            return drawn,frames

        for size in (8.475,11.3,16.95):
            for label in ('43-a','43-b','45-a','45-b','7-A','123-Z'):
                with self.subTest(size=size,label=label):
                    drawn,frames=draw('〔'+label+'〕',size)
                    suffix=next(i for i,g in enumerate(drawn) if g[0]=='-')
                    self.assertGreaterEqual(drawn[suffix][1]-drawn[suffix-1][2],size/11.3-.000001)
                    frame_x,_,frame_width,_=frames[0]
                    self.assertGreater(drawn[0][1],frame_x)
                    self.assertLess(drawn[-1][2],frame_x+frame_width)

        # Ordinary number-only frames retain their calibrated positions.
        drawn,frames=draw('〔43〕',11.3)
        self.assertAlmostEqual(frames[0][2],33.75)
        self.assertAlmostEqual(drawn[0][1],17.459696)
        self.assertAlmostEqual(drawn[1][1]-drawn[0][1],5.070304)


if __name__=='__main__':
    unittest.main()
