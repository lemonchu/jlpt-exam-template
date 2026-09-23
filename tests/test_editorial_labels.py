"""Numbered notes and omission labels are indivisible editorial references."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from inline import parse,plain,lines

class Catalog:
    def width(self,char,size,*args):return size

class EditorialLabelTests(unittest.TestCase):
    def test_literal_markers_do_not_break_inside_parentheses(self):
        for marker in ['（注2）','（注１２）','(注3)','（注）','（中略）','（後略）']:
            with self.subTest(marker=marker):
                text='本文の続き'+marker+'以下'
                rows=lines(text,Catalog(),10,70)
                self.assertIn(marker,[a.text for row in rows for a in row])
                self.assertEqual(''.join(a.text for row in rows for a in row),text)

    def test_under_word_annotations_and_ordinary_parentheses_remain_distinct(self):
        atoms=parse('{{注1|単語}}（参考になる説明）')
        self.assertEqual(atoms[0].annotation,'（注1）')
        self.assertEqual(plain('{{注1|単語}}（参考になる説明）'),'単語（参考になる説明）')
        self.assertNotIn('（参考になる説明）',[a.text for a in atoms])

    def test_marker_too_wide_fails_instead_of_splitting_it(self):
        with self.assertRaises(ValueError):lines('（注1）',Catalog(),10,30)
