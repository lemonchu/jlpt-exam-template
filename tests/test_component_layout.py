"""Focused unit tests for composed-layout calculations."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))

from component_layout import ComponentLayout
from inline import Atom


class CountingCatalog:
    compress_ruby=False

    def __init__(self):self.width_calls=[]

    def width(self,char,size,bold=False,section='',role=None):
        self.width_calls.append((char,size,bold,section,role))
        return size/2


class ChoiceLayoutDouble(ComponentLayout):
    def __init__(self):
        self.section='G';self.top=0;self.bottom=500;self.left=0;self.width=400;self.y=0
        self.gc={};self.pages=[{}];self.item_records=[];self.metric_calls=0;self.ensure_calls=[]

    def choice_metrics(self,item):
        self.metric_calls+=1
        return {'size':10,'lead':20,'promptlines':[],'prompt_tracking':[],
                'rigid_blanks':False,'cols':4,'starts':[10,110,210,310],
                'oplines':[[[]],[[]],[[]],[[]]],'row_counts':[1],'total':40}

    def ensure(self,height):self.ensure_calls.append(height)
    def next_label(self,item):return '1'
    def rect(self,*args,**kwargs):pass
    def glyph(self,*args,**kwargs):pass
    def paragraph(self,*args,**kwargs):pass
    def line(self,*args,**kwargs):pass
    def blocks(self,*args,**kwargs):pass
    def gap(self,*args,**kwargs):pass
    def get_lines(self,*args,**kwargs):return [[]]


class ChoiceLayoutTests(unittest.TestCase):
    def test_choice_calculates_metrics_once(self):
        layout=ChoiceLayoutDouble()
        layout.choice({'id':'q','options':['a','b','c','d']})
        self.assertEqual(layout.metric_calls,1)

    def test_choice_metrics_measure_each_option_once(self):
        layout=object.__new__(ComponentLayout)
        layout.catalog=CountingCatalog();layout.section='V';layout.group={'kind':'choice'}
        layout.gc={};layout.fs=11.3;layout.leading=24.06;layout.width=452.41
        metrics=layout.choice_metrics({'id':'q','prompt':'','options':['aa','bb','cc','dd']})
        self.assertEqual(metrics['cols'],4)
        self.assertEqual([call[0] for call in layout.catalog.width_calls],list('aabbccdd'))

    def test_line_reuses_measured_glyph_widths(self):
        layout=object.__new__(ComponentLayout)
        layout.catalog=CountingCatalog();layout.section='V'
        layout.glyph=lambda *args,**kwargs:None
        layout.rule=lambda *args,**kwargs:None
        layout.line([Atom('abc',width=15)],0,0,10)
        self.assertEqual([call[0] for call in layout.catalog.width_calls],list('abc'))


if __name__=='__main__':
    unittest.main()
