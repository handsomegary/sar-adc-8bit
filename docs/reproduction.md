# Reproduce the published analysis

Use Python 3.9+ with the standard library. No package installation, simulator or process model is needed for these commands, run from the repository root:

```sh
python tools/verify_release.py
python tools/reproduce_all.py --outdir reproduced
```

The output directory must not already exist. Choose another name for a subsequent run. Generated outputs are ignored by Git.

`verify_release.py` checks the SHA256/size manifest, file-size limits, prohibited artifact types, private-environment markers and manifest completeness. It then recomputes all five code FFTs, all five conservative static interval analyses, reverse/history consistency, the T128 interval union and the nominal hierarchy count. It checks the failed reverse-history diagnostic remains visible.

`reproduce_all.py` writes `analysis.json` and the symbolic `adc_topology.scs` into the requested directory. FFT powers, SNDR, ENOB and deterministic bracket intervals must agree with the exported references. The comparison tolerances apply to recomputed arithmetic, not a relaxation of stored physical inputs or timing windows. No code values or histories are interpolated or fitted.

The data retain acquisition and output-read timestamps. Do not treat both as independent samples, and do not treat raw transient solver points as uniformly sampled ADC codes. The current code CSVs have already been selected from the documented original conversion indices.

For an analysis-library mathematics check, `python src/sar_analysis.py selftest` uses synthetic reference signals. Those reference checks are not ADC simulation evidence.

## A new transistor simulation is separate work

The repository has no licensed process-model binding or native parameter cards. `src/sar_logic*.py` and `src/sar_frontend.py` accept a MOS callback so authorized users can provide their own complete process instances. `src/adc_topology.py` uses undefined symbolic models for public connectivity export. Replacing these names with an arbitrary generic model does not reproduce the archived results.

A genuine rerun requires an authorized compatible PDK, the correct native instance parameters and model options, and a separately reviewed supply/reference/input/clock fixture, timing extraction, transient-noise setup and power meters. No such rerun is launched by the published tools. No HSPICE, layout or extracted-circuit equivalence is claimed.
