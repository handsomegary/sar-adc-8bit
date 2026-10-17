# Validation scope

## What passed

The historical project gate is `DECLARED_SCHEMATIC_PROTOTYPE_GATE_PASSED`, projected in `evidence/declared_gate.json`. It concerns an eight-bit schematic prototype at 0.9 V and 25 °C with ideal capacitors. It does not mean production or physical signoff.

| Evidence | Conditions | Supported conclusion |
|---|---|---|
| Five dynamic records | TT; three noiseless and two noisy coherent tones; 256 selected conversions each | Saved output-code spectra and the listed SNDR/ENOB values |
| Five static corner records | TT, SS, FF, SF, FS; noiseless; 553 validated observations per corner | All 256 codes observed; deterministic endpoint-fit bracket bounds inside declared limits |
| Reverse/tight-tolerance anchors | 70 selected points | 69 equal codes, one preserved exact-zero mismatch |
| Central boundary | ±0.05 V preceding histories; probes −100/−20/0/+20/+100 µV; reltol 0.001 and 0.0001 | Tested ±20 µV adjacent decisions agree; exact-zero decision remains history dependent |
| Historical OA/native export | Saved/reopened hierarchy, CDF/connectivity/parameter audit; eight DC conversions | Short export functionality, not the separate ADC performance qualification |

Nominal resolution is **8 bit / 256 codes**. Noisy ENOB is **7.597–7.690** using `(SNDR − 1.76)/6.02`. Noiseless, short coherent records can exceed eight in that formula. They do not establish greater physical resolution.

## FFT and power boundaries

The exported dynamic CSVs contain exactly original conversion indices 3–258 from 263 saved rows: three leading and four trailing rows are unused. The analysis removes DC and the specified coherent fundamental, retains every other AC bin including harmonics, uses one-sided Parseval scaling and applies no window. Fundamental bins are 17, 29 and 119 of 256 at 20 MS/s.

There is one noisy record per tested noisy tone, with seeds 43 and 79. The requested 1 kHz minimum noise frequency was clamped by the simulator to approximately 74.6269 kHz for the 13.4 µs transient; the maximum was 10 GHz. These records are insufficient for precise noise statistics, yield or broad noisy-PVT claims. The archived simulator logs reported no errors and duplicate scalefactor warnings; the model's last reported scalefactor was 0.9. Process-specific details are outside this export.

Core power is the saved AVDD aggregate from external testbench energy meters over adaptive internal timesteps. Signed ideal reference-high, reference-low, common-mode and clock contributions are separate. Negative values mean returned energy. Published tools check aggregate arithmetic; they do not reintegrate raw currents. No physical driver efficiency or complete system-power result is established.

## Conservative static intervals

All 255 transition brackets include an input guard. Endpoint-fit LSB uncertainty is propagated into DNL and INL. DNL applies to codes 1–254, whose widths are bounded by transitions; saturated end bins are excluded. INL uses T1/T255 endpoint fitting, which removes offset and gain. Midpoint curves are estimates, not the conservative interval bounds.

The measured selected central-history band is about [−21,+21] µV after input guards. The original forward T128 bracket extends farther positive. The final band is the **union**, approximately [−21,+485.498] µV. Original possible thresholds are retained. Other transitions keep their original forward brackets, so selected reverse anchors do not prove all transitions under all histories.

The strict 70-anchor equality remains false. At 0 V the positive preceding history yields 128 and negative history yields 127 under both tested tolerances. This is retained rather than fitted away. Acceptance is limited to the saved sequences and conservative interval budget.

## Provenance and reproducibility limits

Published JSON files are deliberate projections of original artifacts; `evidence/source_provenance.json` retains original hashes. Dynamic code CSVs are exact exports. Static CSVs retain all observed rows and saved validation flags. The originals remain unchanged in the project archive.

The tighter central-boundary result was recovered from a complete saved transient and a zero-error log after empty result files. Its original process exit code is still unknown. Recovery-time model hashes do not independently prove the historical state of external model files. The repository preserves this caveat.

`verify_release.py` validates release hashes, lightweight data consistency and reproduced mathematics. It cannot independently establish raw-waveform acquisition, process licensing, the original simulator's execution or saved input/timing flags. Those flags and reported power values remain inherited evidence. No raw-current reintegration or transistor rerun is advertised.

## Outstanding physical work

Physical capacitor mismatch and layout parasitics; physical input/reference/clock drivers; layout/DRC/LVS/PEX; voltage/temperature sweeps and yield; extensive noisy/PVT ensembles; and silicon validation remain unqualified. The exact 3 dB ERBW crossing and an ERBW-based figure of merit are unmeasured.

The release excludes process/model files, native model-parameter cards, CAD binary libraries, third-party course PDFs, connection scripts, credentials and large raw archives. No third-party source license is assigned by this repository.
