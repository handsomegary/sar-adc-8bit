#!/usr/bin/env python3
"""Compile the same CircuitikZ inputs to standalone PDF and white-background SVG.

Requires a local LaTeX distribution (standalone, CircuitikZ, Latin Modern,
Helvetica, Times) and Poppler pdftocairo. No circuit simulator is invoked.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'report'
PREAMBLE = r'''\documentclass[border=5pt]{standalone}
\providecommand{\DoNotLoadEpstopdf}{}
\usepackage[T1]{fontenc}
\usepackage{lmodern,amsmath,amssymb,graphicx}
\usepackage{mathptmx}
\usepackage[scaled=.95]{helvet}
\usepackage[american]{circuitikz}
\usetikzlibrary{calc,positioning,arrows.meta,shapes.gates.logic.US}
\input{circuit-style}
\begin{document}
'''


def white_background(path, title):
    namespace = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', namespace)
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    tree = ET.parse(path)
    root = tree.getroot()
    root.set('role', 'img')
    root.set('aria-label', title)
    root.insert(0, ET.Element('{'+namespace+'}rect', {
        'x':'0', 'y':'0', 'width':'100%', 'height':'100%', 'fill':'#ffffff'}))
    tree.write(path, encoding='utf-8', xml_declaration=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdflatex', default='pdflatex')
    p.add_argument('--pdftocairo', default='pdftocairo')
    p.add_argument('--only', nargs='+', default=None)
    args = p.parse_args()
    figures = sorted((REPORT/'figures').glob('*.tex'))
    if args.only:
        requested = set(args.only)
        figures = [f for f in figures if f.stem in requested]
        if {f.stem for f in figures} != requested:
            p.error('Unknown drawing requested')
    if not figures:
        p.error('No editable drawings found')
    build = ROOT/'runs/figure-build'
    build.mkdir(parents=True, exist_ok=True)
    manifest_path=REPORT/'figures/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'drawings':{}}
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for source in figures:
        wrapper = build/(source.stem+'-standalone.tex')
        wrapper.write_text(PREAMBLE+'\\input{figures/'+source.stem+'}\n\\end{document}\n',encoding='utf-8')
        command = [args.pdflatex, '-no-shell-escape', '-interaction=nonstopmode',
                   '-halt-on-error', '-jobname='+source.stem, '-output-directory='+str(build), str(wrapper)]
        done = subprocess.run(command,cwd=REPORT,capture_output=True,text=True,errors='replace',timeout=120)
        if done.returncode:
            raise RuntimeError('LaTeX failed for '+source.stem+'\n'+done.stdout[-2500:])
        output = source.with_suffix('.pdf')
        shutil.copyfile(build/(source.stem+'.pdf'),output)
        svg = source.with_suffix('.svg')
        subprocess.run([args.pdftocairo,'-svg',str(output),str(svg)],check=True,timeout=60)
        white_background(svg, source.stem.replace('-',' ')+'; source-derived SAR ADC diagram')
        manifest['drawings'][source.stem]={
            'source':source.name,'source_sha256':digest(source),
            'style_sha256':digest(REPORT/'circuit-style.tex'),
            'standalone_preamble_sha256':hashlib.sha256(PREAMBLE.encode()).hexdigest(),
            'pdf':output.name,'pdf_sha256':digest(output),
            'svg':svg.name,'svg_sha256':digest(svg),
            'svg_conversion':'pdftocairo -svg from the compiled standalone PDF; explicit white background added'}
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        print(source.stem+': PDF and white-background SVG generated')


if __name__ == '__main__':
    main()
