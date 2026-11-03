# Circuit implementation report

[Read the PDF](sar-adc-8bit.pdf). The editable source is [main.tex](main.tex), with a shared [CircuitikZ profile](circuit-style.tex) and individual figures in [figures/](figures/).

The report uses a two-column IEEE-style layout, Times body text, American CircuitikZ symbols, and bold sans-serif circuit labels. The shared profile sets the requested MOS arrows and symbol scales. Figure inputs are the same editable sources used for the standalone PDF and white-background SVG previews. These are authored, netlist-derived drawings; they are not screenshots of a CAD schematic or a layout.

## Build

Install a TeX distribution containing `IEEEtran`, `circuitikz`, `pgf/tikz`, `booktabs`, `hyperref`, `lmodern`, and the Times/Helvetica font packages. From the repository root:

```sh
python report/build_report.py
python tools/build_figures.py
```

Use `--pdflatex` to select another installed executable. The helper runs two LaTeX passes with shell escape disabled. Intermediate files stay in `runs/report-build/`; the final PDF is copied to `report/sar-adc-8bit.pdf`. It neither invokes a simulator nor loads device models.

The figure builder also needs Poppler's `pdftocairo` (select it with
`--pdftocairo`). It compiles each picture from the shared CircuitikZ profile,
converts that same standalone PDF to SVG, and adds an explicit white background.
Intermediate files stay in `runs/figure-build/`. The generated
[figure manifest](figures/manifest.json) binds the drawing source, style, PDF
and SVG hashes. It verifies file correspondence, not electrical equivalence of
arbitrary edited drawings. After editing sources and rebuilding artifacts,
the release manifest must also be regenerated before release verification.

| Drawing | Editable source | Vector PDF | GitHub SVG |
| --- | --- | --- | --- |
| Signal path and power-on reset | [TeX](figures/system.tex) | [PDF](figures/system.pdf) | [SVG](figures/system.svg) |
| Differential capacitor arrays | [TeX](figures/cdac.tex) | [PDF](figures/cdac.pdf) | [SVG](figures/cdac.svg) |
| Sampling and reference switches | [TeX](figures/cdac-switch.tex) | [PDF](figures/cdac-switch.pdf) | [SVG](figures/cdac-switch.svg) |
| Dynamic comparator and SR hold | [TeX](figures/comparator.tex) | [PDF](figures/comparator.pdf) | [SVG](figures/comparator.svg) |
| Native CMOS cells | [TeX](figures/logic-cells.tex) | [PDF](figures/logic-cells.pdf) | [SVG](figures/logic-cells.svg) |
| Reset latch and DFF hierarchy | [TeX](figures/logic-latch.tex) | [PDF](figures/logic-latch.pdf) | [SVG](figures/logic-latch.svg) |
| Five-stage Johnson controller | [TeX](figures/controller.tex) | [PDF](figures/controller.pdf) | [SVG](figures/controller.svg) |

## Read the circuits

| Editable drawing | Scope |
| --- | --- |
| [system.tex](figures/system.tex) | CDAC, comparator and native SAR-controller signal flow |
| [cdac.tex](figures/cdac.tex) | Complete positive and negative binary capacitor arrays |
| [cdac-switch.tex](figures/cdac-switch.tex) | Input sampling pairs and complementary reference selection |
| [comparator.tex](figures/comparator.tex) | Regenerative core, reset, isolation and static decision storage |
| [logic_modules.tex](logic_modules.tex) | Controller and its native storage/clock primitives |

The drawings use the unchanged [symbolic netlist](../design/adc_topology.scs). Its MOS names and requested geometry expose connectivity without supplying process models or native parameter cards. Shared labels identify connected nets. Control arrows, functional blocks and abbreviated repeated cells are explained in the captions; they do not imply extra implemented circuitry.

## Evidence boundary

All numerical results are the existing saved ADC results. Creating this report launches no new electrical test. Nominal resolution remains eight bits; the two short transient-noise records give 7.597-7.690 ENOB. The strict reverse-history comparison remains false at 69/70. Ideal capacitors, ideal external drivers and the documented power scope remain explicit. Layout, capacitor mismatch, extracted parasitics and silicon performance are not qualified.

See [validation scope](../docs/validation-scope.md) and [analysis reproduction](../docs/reproduction.md) for the measurement and provenance limits. Neither the report format nor the circuit drawing style denotes IEEE publication or endorsement.
