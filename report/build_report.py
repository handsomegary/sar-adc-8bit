#!/usr/bin/env python3
"""Build the editable IEEE-style report; no simulator or process models are used."""
import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdflatex', default='pdflatex', help='Installed pdflatex executable')
    args = parser.parse_args()
    report = Path(__file__).resolve().parent
    root = report.parent
    executable = shutil.which(args.pdflatex)
    if executable is None:
        raise SystemExit('Install a TeX distribution with IEEEtran and CircuitikZ, or supply --pdflatex.')
    build = root/'runs'/'report-build'
    build.mkdir(parents=True, exist_ok=True)
    command = [executable, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error',
               '-jobname=sar-adc-8bit', '-output-directory='+str(build), 'main.tex']
    for pass_number in (1, 2):
        print('LaTeX pass '+str(pass_number), flush=True)
        result = subprocess.run(command, cwd=report, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace')
        (build/('pass'+str(pass_number)+'.txt')).write_text(result.stdout, encoding='utf-8')
        if result.returncode:
            print(result.stdout[-6000:])
            raise SystemExit('LaTeX failed; inspect runs/report-build for the compilation log.')
    output = build/'sar-adc-8bit.pdf'
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit('LaTeX did not produce a report PDF.')
    shutil.copyfile(output, report/'sar-adc-8bit.pdf')
    print('Built report/sar-adc-8bit.pdf; simulations launched: 0')


if __name__ == '__main__':
    main()
