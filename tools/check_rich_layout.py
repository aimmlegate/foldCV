"""Internal converter QA; the product exports DOCX without this tool."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from packages.resume_core.rendering.rich_docx import render_rich_docx,RENDERER_VERSION
from packages.resume_core.storage import atomic_write,private_directory
from tests.render.rich_layout_fixtures import fixture


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.output.resolve();private_directory(root)
    import pymupdf
    results={}
    for name in ['short','long','matrix']:
        document,images=fixture(name);target=root/(name+'.docx');atomic_write(target,render_rich_docx(document,images))
        result=subprocess.run([str(ROOT/'.tools/LibreOffice.app/Contents/MacOS/soffice'),'-env:UserInstallation='+(root/('profile-'+name)).as_uri(),
            '--headless','--convert-to','pdf','--outdir',str(root),str(target)],capture_output=True,text=True,timeout=60)
        pdf=root/(name+'.pdf')
        if result.returncode or not pdf.is_file():raise RuntimeError('QA_CONVERSION_FAILED')
        pdf.chmod(0o600);pages=[];all_text=''
        with pymupdf.open(pdf) as rendered:
            for index,page in enumerate(rendered):
                spans=[span for block in page.get_text('dict')['blocks'] if block['type']==0 for line in block['lines'] for span in line['spans']]
                all_text+=page.get_text()
                png=root/f'{name}-{index+1}.png';page.get_pixmap(matrix=pymupdf.Matrix(1.25,1.25)).save(png);png.chmod(0o600)
                pages.append({'page':index+1,'width':page.rect.width,'height':page.rect.height,
                    'fonts':sorted({span['font'] for span in spans}),
                    'textOutsidePage':[span['text'][:40] for span in spans if not page.rect.contains(pymupdf.Rect(span['bbox']))],
                    'firstOrigins':[{'text':span['text'][:30],'origin':span['origin'],'size':span['size']} for span in spans if span['text'].strip()][:8],
                    'footerOrigins':[span['origin'] for span in spans if span['size'] == 12 and span['origin'][1] > 780],
                    'drawings':[list(drawing['rect']) for drawing in page.get_drawings() if drawing['rect'].width>400],
                    'images':[info['bbox'] for info in page.get_image_info()]})
        expected=['FINAL_MARKER']+[f'JOB_END_{i+1}' for i in range(5 if name=='long' else 1)]
        if name=='matrix':expected+=['TOGGLE_CHILD','CODE_END','DEPTH_END','IMAGE_CAPTION','MATRIX_END']
        results[name]={'pages':pages,'missingMarkers':[marker for marker in expected if marker not in all_text],
            'rendererVersion':RENDERER_VERSION,'fontLimit':'Converter substitutes some real Word family names; verify native use manually in Word.'}
    atomic_write(root/'measurements.json',json.dumps(results,indent=2).encode())
    print(json.dumps({name:{'pages':len(result['pages']),'missingMarkers':result['missingMarkers'],
        'outsidePage':sum(len(page['textOutsidePage']) for page in result['pages'])} for name,result in results.items()}))
    if any(result['missingMarkers'] or any(page['textOutsidePage'] for page in result['pages']) for result in results.values()):
        raise SystemExit('QA_CONTENT_OR_PAGE_BOUNDS_FAILED')


if __name__=='__main__':main()
