#!/usr/bin/env python3
"""Build and inspect the editable V/G example in a temporary, PDF-free project."""
from argparse import ArgumentParser
from contextlib import redirect_stdout
from pathlib import Path
import hashlib,io,json,os,runpy,shutil,sys,tempfile,unicodedata
import fitz,yaml
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def compact(text):return ''.join(c for c in unicodedata.normalize('NFKC',str(text)) if not c.isspace())
def write_png(im,path):
    buffer=io.BytesIO();im.save(buffer,format='PNG')
    with path.open('wb') as f:f.write(buffer.getvalue());f.flush();os.fsync(f.fileno())
    with Image.open(path) as test:test.load()

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--with-cover',action='store_true',help='Also verify a cover advertising the actual four body pages.')
    args=parser.parse_args();output=args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):parser.error('Use a new or empty output directory.')
    output.mkdir(parents=True,exist_ok=True)
    example=ROOT/'examples/functional-check'
    opens=[];native_processes=[]
    with tempfile.TemporaryDirectory(prefix='n1-functional-') as temporary:
        project=Path(temporary)/'template';project.mkdir()
        for name in ('engine','profiles','resources'):
            shutil.copytree(ROOT/name,project/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pdf'))
        shutil.copyfile(ROOT/'build.py',project/'build.py')
        if (ROOT/'fonts.yaml').is_file():
            shutil.copyfile(ROOT/'fonts.yaml',project/'fonts.yaml')
        shutil.copytree(ROOT/'content/common',project/'content/common')
        # The unrelated name is deliberate: both source data and output start fresh.
        paper='studio-sandbox';shutil.copytree(example/'content',project/'content'/paper)
        (project/'blueprints').mkdir()
        bp=yaml.safe_load((example/'blueprint.yaml').read_text());bp['cover']=args.with_cover
        (project/'blueprints/check.yaml').write_text(yaml.safe_dump(bp,allow_unicode=True,sort_keys=False))
        shutil.copyfile(example/'components.yaml',project/'blueprints/components.yaml')
        assert not list(project.rglob('*.pdf'))
        assert not (project/'output').exists()
        snapshot={str(p.relative_to(project)):digest(p) for p in sorted(project.rglob('*')) if p.is_file()}
        (output/'input-hashes.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
        recorder=Path(temporary)/'bin';recorder.mkdir()
        latex=shutil.which('xelatex');assert latex,'XeLaTeX is required.'
        wrapper=recorder/'xelatex'
        wrapper.write_text('#!/usr/bin/env python3\nimport os,sys\nos.execv('+repr(latex)+','+repr([latex,'-recorder'])+'+sys.argv[1:])\n')
        wrapper.chmod(0o755)
        def audit(event,values):
            if event=='open' and isinstance(values[0],(str,bytes,os.PathLike)):
                opens.append({'path':os.fsdecode(values[0]),'mode':values[1]})
            elif event=='subprocess.Popen':native_processes.append({'command':values[1],'cwd':str(values[2])})
        sys.addaudithook(audit)
        saved_path=os.environ.get('PATH','');saved_argv=sys.argv
        try:
            os.environ['PATH']=str(recorder)+os.pathsep+saved_path
            sys.argv=[str(project/'build.py'),'--paper',paper,'--booklet','written','--blueprint',str(project/'blueprints/check.yaml')]
            with (output/'build-output.txt').open('w') as stream,redirect_stdout(stream):
                runpy.run_path(str(project/'build.py'),run_name='__main__')
        finally:
            os.environ['PATH']=saved_path;sys.argv=saved_argv
        generated=project/'output'/f'{paper}-written'
        scene=json.loads((generated/'scene.json').read_text())['sections']['booklet']['pages']
        resolved=json.loads((generated/'resolved.json').read_text())['runs']
        from inline import parse
        def plain(text):return ''.join(c for a in parse(str(text)) for c in a.text if not c.isspace())
        groups={g['id']:g for section in ('V','G') for g in yaml.safe_load((project/'content'/paper/f'{section}.yaml').read_text())['groups']}
        report={'status':'PASS','paper_name':paper,'initial_input_pdf_count':0,'initial_output_absent':True,
                'body_pages':4,'with_cover':args.with_cover,'pages':[]}
        cover_count=2 if args.with_cover else 0
        assert len(scene)==4+cover_count
        all_numbers=[];all_items=[];pictures=[];body_glyphs=0
        with fitz.open(generated/'main.pdf') as doc:
            assert not doc.is_repaired and len(doc)==len(scene)
            if args.with_cover:
                cover_text=compact(doc[0].get_text())
                assert 'この問題用紙は、全部で4ページあります。' in cover_text,cover_text
                assert 'Thisquestionbooklethas4pages.' in cover_text,cover_text
                report['cover_declares_actual_page_count']=True
            for body_index,(page,entry) in enumerate(zip(scene[cover_count:],bp['groups']),1):
                group=groups[entry['id']];by_id={q['id']:q for q in group['items']}
                chosen=[by_id[k] for k in entry['items']] if entry.get('items') else list(by_id.values())
                expected=''.join(plain(q['prompt'])+''.join(str(i+1).translate(str.maketrans('1234','１２３４'))+plain(option) for i,option in enumerate(q['options'])) for q in chosen)
                runs=[c for c in page['commands'] if c['type']=='run']
                content=''.join(''.join(resolved[c['run_id']]['glyphs']) for c in runs if c.get('role')=='body' and abs(c['sy']-11.3)<1e-5)
                assert content==expected,(body_index,content,expected)
                actual_page=doc[body_index+cover_count-1]
                drawn=''.join(chr(g[0]) for trace in actual_page.get_texttrace() for g in trace['chars'])
                expected_drawn=''.join(''.join(resolved[c['run_id']]['glyphs']) for c in runs)
                assert drawn==expected_drawn,(body_index,'PDF Unicode differs from scene')
                body_glyphs+=len(drawn)
                labels=[c for c in runs if c.get('role')=='question-number']
                numbers=[int(''.join(resolved[c['run_id']]['glyphs'])) for c in labels]
                all_numbers+=numbers;all_items.extend(q['id'] for q in chosen)
                x=83.79 if body_index%2 else 68.46
                assert all(abs(c['x']-x)<.001 for c in labels)
                footer=''.join(''.join(resolved[c['run_id']]['glyphs']) for c in runs if c.get('role')=='footer')
                assert footer==str(body_index)
                sidebar=''.join(''.join(resolved[c['run_id']]['glyphs']) for c in runs if c.get('role')=='sidebar')
                assert sidebar==('文法検証' if body_index==4 else '編集確認')
                fills=[d for d in actual_page.get_drawings() if d['fill']]
                expected_rect=((565.,300.,595.,412.) if body_index%2 else (0.,300.,30.,412.)) if body_index!=4 else (0.,420.,30.,532.)
                assert len(fills)==1 and tuple(round(v,4) for v in fills[0]['rect'])==expected_rect
                if body_index==2:
                    expected_ruby=''.join(a.ruby for a in parse(chosen[0]['prompt']) if a.ruby)
                    ruby=''.join(''.join(resolved[c['run_id']]['glyphs']) for c in runs if c.get('role')=='body' and abs(c['sy']-5.6)<.001)
                    assert ruby==expected_ruby
                    report['long_prompt']={'characters':len(plain(chosen[0]['prompt'])),'ruby':ruby,'complete':True}
                report['pages'].append({'body_page':body_index,'pdf_page':body_index+cover_count,'group':group['id'],'items':[q['id'] for q in chosen],'question_numbers':numbers,'question_x':x,'footer':footer,'sidebar':sidebar,'content_matches_yaml':True,'pdf_unicode_matches_scene':True})
            for index,page in enumerate(doc,1):
                pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                write_png(im,output/f'page-{index:02}.png');pictures.append(im)
        assert all_numbers==list(range(1,9)),all_numbers
        assert all_items==['V-07','V-08','V-01','V-03','studio-choice-1','studio-choice-2','G27','G30'],all_items
        report['body_glyphs']=body_glyphs;assert body_glyphs==828
        pdf_opens=[r for r in opens if r['path'].lower().endswith('.pdf')]
        assert all(Path(r['path']).resolve().is_relative_to(project/'output') for r in pdf_opens),pdf_opens
        fls=generated/'main.fls';assert fls.is_file()
        tex_inputs=sorted({line[6:] for line in fls.read_text().splitlines() if line.startswith('INPUT ')})
        assert not [p for p in tex_inputs if p.lower().endswith('.pdf')]
        report['dependency_audit']={'scope':'Python open hook and XeLaTeX -recorder; no operating-system tracing','python_pdf_opens':pdf_opens,'external_pdf_inputs':[],'tex_pdf_inputs':[],'subprocesses':native_processes}
        shutil.copyfile(generated/'main.pdf',output/'functional-check.pdf')
        shutil.copyfile(fls,output/'xelatex-inputs.fls')
        for name in ('scene.json','resolved.json','build-report.json','render-report.json'):
            shutil.copyfile(generated/name,output/name)
        report['pdf_sha256']=digest(output/'functional-check.pdf')
        columns=min(6,len(pictures));width=250;height=354;rows=(len(pictures)+columns-1)//columns
        contact=Image.new('RGB',(columns*(width+16)+16,rows*(height+32)+16),'#d5d5d5');draw=ImageDraw.Draw(contact)
        for index,im in enumerate(pictures):
            preview=im.copy();preview.thumbnail((width,height));x=16+(index%columns)*(width+16);y=16+(index//columns)*(height+32)
            contact.paste(preview,(x,y));draw.text((x,y+height+4),f'PDF page {index+1}',fill='black')
        write_png(contact,output/'contact.png')
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','pages':4+cover_count,'questions':8,'body_glyphs':828,'input_pdf_count':0,'output':str(output)},indent=2))

if __name__=='__main__':main()
