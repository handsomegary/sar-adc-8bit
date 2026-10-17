#!/usr/bin/env python3
"""Recompute exported ADC code FFTs, deterministic brackets and topology.

Standard-library Python3.9+. No model loading, simulator, raw waveform reader,
network, external process or connection to the original test environment.
Power is a saved reported aggregate, not independently reintegrated here.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import sar_analysis
import adc_topology


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def close(a, b, tolerance=1e-9):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= tolerance


def reproduce():
    dynamic = []
    for record in read(ROOT / 'data/dynamic/records.json')['records']:
        with (ROOT / record['csv']).open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 256:
            raise ValueError('Expected exact256 selected conversions')
        codes = [int(row['code']) for row in rows]
        times = [float(row['sample_time_s']) for row in rows]
        reference = record['reported_dynamic']
        result = sar_analysis.analyze_dynamic(codes, reference['fundamental_bin'], reference['fs_hz'],
                                             bits=8, sample_times=times)
        for key in ('sndr_db', 'enob', 'sfdr_db', 'spectrum_power_code2'):
            if not close(result[key], reference[key]):
                raise ValueError('Dynamic result differs: ' + record['run'] + ' ' + key)
        if any(not 0 <= code <= 255 for code in codes):
            raise ValueError('Invalid8bit code')
        if not close(sum(record['reported_source_power_W'].values()), record['reported_signed_five_source_total_W'], 1e-15):
            raise ValueError('Reported signed five-source aggregate differs')
        dynamic.append({'run': record['run'], 'noise_enabled': record['noise_enabled'],
                        'sndr_db': result['sndr_db'], 'enob': result['enob'],
                        'spectrum_power_code2': result['spectrum_power_code2'],
                        'reported_AVDD_W': record['reported_source_power_W']['AVDD'],
                        'power_reintegrated': False})
    static, brackets_by_corner = [], {}
    for corner in ('tt', 'ss', 'ff', 'sf', 'fs'):
        record = read(ROOT / ('data/static/static_' + corner + '_brackets.json'))
        with (ROOT / record['observation_csv']).open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 553 or {int(row['code']) for row in rows} != set(range(256)):
            raise ValueError('Actual static code coverage differs')
        by_id = {int(row['observation_id']): row for row in rows}
        if len(by_id) != 553:
            raise ValueError('Static observation IDs not unique')
        for row in rows:
            if any(row[key] != 'True' for key in ('sampled_input_verified', 'ramp_inside_actual_track', 'held_after_ramp')):
                raise ValueError('A saved input/timing-validation flag is false')
            if abs(float(row['input_diff_V']) - float(row['requested_input_diff_V'])) > float(row['input_uncertainty_guard_V']):
                raise ValueError('Saved applied input outside guard')
        brackets = []
        for k in range(1, 256):
            bound = record['threshold_bounds'][str(k)]
            lo, hi = by_id[bound['low_observation_id']], by_id[bound['high_observation_id']]
            if not int(lo['code']) < k <= int(hi['code']):
                raise ValueError('Threshold observation codes do not bracket transition')
            if not (float(lo['input_diff_V']) == bound['low_V'] and float(hi['input_diff_V']) == bound['high_V']):
                raise ValueError('Threshold input provenance differs')
            brackets.append([bound['guarded_low_V'], bound['guarded_high_V']])
        analysis = sar_analysis.analyze_transition_brackets(brackets)
        reported = record['reported_interval_static_analysis']
        for key in ('dnl_lsb_bounds', 'inl_lsb_bounds', 'fitted_lsb_voltage_bounds'):
            if not close(analysis[key], reported[key], 1e-10):
                raise ValueError('Static interval analysis differs')
        if not analysis['dnl_proved_within_brackets'] or not analysis['inl_proved_within_brackets']:
            raise ValueError('Declared finite static limits failed')
        brackets_by_corner[corner] = brackets
        static.append({'corner': corner, 'observations': len(rows), 'observed_codes': 256,
                       'DNL_bound_LSB': analysis['worst_dnl_bound_magnitude_lsb'],
                       'INL_bound_LSB': analysis['worst_inl_bound_magnitude_lsb'],
                       'status': analysis['qualification_status']})
    history = read(ROOT / 'data/history/zero_boundary.json')
    anchors = read(ROOT / 'data/history/reverse_70_anchors.json')['comparison']
    matched = sum(row['code_matches'] for row in anchors)
    if len(anchors) != 70 or matched != 69 or history['original_reverse_check']['strict_all70_identical_gate'] is not False:
        raise ValueError('Original failed strict70-anchor diagnostic was lost')
    if [row['voltage_V'] for row in anchors if not row['code_matches']] != [0.0]:
        raise ValueError('Reverse mismatch is not the preserved zero boundary')
    for test in history['history_tests']:
        for case in test['history_cases']:
            probes = {row['probe_V']: row['code'] for row in case['probe_sequence']}
            if probes[-20e-6] != 127 or probes[20e-6] != 128:
                raise ValueError('Tested adjacent-code boundary not retained')
            if probes[0.] != (128 if case['history_V'] > 0 else 127):
                raise ValueError('Exact-zero history-dependent codes were changed')
    old = history['original_guarded_T128_interval_V']
    band = history['new_measured_history_tolerance_union_band_V']
    union = [min(old[0], band[0]), max(old[1], band[1])]
    if union != history['final_conservative_T128_union_V']:
        raise ValueError('Original possible threshold range was narrowed')
    revised = list(brackets_by_corner['tt'])
    revised[127] = union
    zero_static = sar_analysis.analyze_transition_brackets(revised)
    ref = history['recomputed_conservative_DNL_INL']
    if not close(zero_static['dnl_lsb_bounds'], ref['DNL_LSB_intervals_codes1_to254'], 1e-10) or not close(zero_static['inl_lsb_bounds'], ref['INL_LSB_intervals_transitions1_to255'], 1e-10):
        raise ValueError('Conservative history/tolerance union analysis differs')
    topology = adc_topology.describe(adc_topology.generate_core())
    if topology['expanded_MOS_counts'] != {'ADC': 769, 'sar_control': 424, 'sar_cdac': 314, 'sar_comparator': 27} or topology['active_hierarchy_cell_count'] != 16:
        raise ValueError('Authored nominal topology differs')
    return {'status': 'EXPORTED_DATA_ANALYSIS_REPRODUCED_NOT_TRANSISTOR_SIMULATION_RERUN',
            'dynamic': dynamic, 'static': static,
            'history': {'matched_reverse_anchors': matched, 'total_reverse_anchors': 70,
                        'strict70_equality': False, 'T128_union_V': union,
                        'DNL_bound_LSB': zero_static['worst_dnl_bound_magnitude_lsb'],
                        'INL_bound_LSB': zero_static['worst_inl_bound_magnitude_lsb']},
            'topology_counts': topology['expanded_MOS_counts'],
            'saved_input_timing_flags_rederived_from_raw': False,
            'power_reintegrated': False, 'simulations_launched': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', default='reproduced')
    args = parser.parse_args()
    result = reproduce()
    target = Path(args.outdir)
    target.mkdir(parents=True, exist_ok=False)
    (target / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (target / 'adc_topology.scs').write_text(adc_topology.generate_core(), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'outdir': str(target), 'dynamic_records': len(result['dynamic']),
                      'static_corners': len(result['static']), 'simulations_launched': 0}, indent=2))


if __name__ == '__main__':
    main()
