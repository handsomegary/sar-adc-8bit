"""Authored nominal geometry/connectivity export; no process model parameters.

NMOS_CORE/PMOS_CORE are deliberately undefined symbolic model names. Output
is a connectivity artifact, not a standalone transistor simulation deck.
Each MOS callback call is a separate physical instance. PDK fingers, native
macro parameters and model coefficients are not reconstructed here.
"""
import re
from sar_logic_compact import generate_sar_logic
from sar_frontend import generate_frontend


def nominal_mos(name, d, g, s, b, pmos=False, w=.5e-6, l=30e-9):
    return '%s (%s %s %s %s) %s w=%.16g l=%.16g' % (
        name, d, g, s, b, 'PMOS_CORE' if pmos else 'NMOS_CORE', w, l)


def generate_core(mos=nominal_mos, unit_cap=5e-15):
    logic = generate_sar_logic(mos)
    analog = generate_frontend(mos, unit_cap=unit_cap)
    bits = ' '.join('b%d' % i for i in range(7, -1, -1))
    valid = ' '.join('v%d' % i for i in range(7, -1, -1))
    outputs = ' '.join('D%d' % i for i in range(7, -1, -1))
    lines = ['subckt ADC AVDD AVSS VREFP VREFN VCM VIP VIN ' + outputs + ' CLK',
             '// Power-on reset requires an actual VDD ramp in a simulation fixture.',
             'CPOR (AVDD por) capacitor c=1p',
             'RPOR (por AVSS) resistor r=100k',
             'XPI0 (AVDD AVSS por porb) sar_inv',
             'XPI1 (AVDD AVSS porb rst) sar_inv',
             'XCTL (AVDD AVSS CLK rst cmpQ track cmpclk q0 ' + bits + ' ' + valid + ' ' + outputs + ') sar_control',
             'XCDAC (AVDD AVSS VREFP VREFN VCM VIP VIN track ' + bits + ' ' + valid + ' vp vn) sar_cdac',
             'XCMP (AVDD AVSS cmpclk vp vn cmpQ cmpQB) sar_comparator',
             'ends ADC']
    return '// SYMBOLIC CONNECTIVITY ONLY: supply authorized process models separately.\n' + logic + '\n' + analog + '\n' + '\n'.join(lines) + '\n'


def describe(text):
    cells, current = {}, None
    instance = re.compile(r'^(\S+)\s+\(([^)]*)\)\s+(\S+)(?:\s+(.*))?$')
    for line in text.splitlines():
        if not line or line.startswith('//'):
            continue
        if line.startswith('subckt '):
            fields = line.split()
            if fields[1] in cells:
                raise ValueError('Duplicate cell')
            current = {'ports': fields[2:], 'mos': [], 'instances': [], 'passives': []}
            cells[fields[1]] = current
            continue
        if line.startswith('ends '):
            current = None
            continue
        match = instance.match(line)
        if current is None or not match:
            raise ValueError('Unrecognized topology line: ' + line)
        name, nodes, kind, params = match.groups()
        row = {'instance': name, 'nodes': nodes.split()}
        if kind in ('NMOS_CORE', 'PMOS_CORE'):
            values = dict(item.split('=', 1) for item in params.split())
            row.update(polarity='PMOS' if kind.startswith('P') else 'NMOS',
                       nominal_width_m=float(values['w']), nominal_length_m=float(values['l']),
                       instance_multiplicity=1, fingers=None)
            current['mos'].append(row)
        elif name.startswith('X'):
            row['cell'] = kind
            current['instances'].append(row)
        elif kind in ('capacitor', 'resistor'):
            row.update(kind=kind, nominal_schematic_parameters=params)
            current['passives'].append(row)
        else:
            raise ValueError('Unsupported primitive: ' + kind)
    active = set()
    def count(cell, stack=()):
        if cell in stack:
            raise ValueError('Hierarchy cycle')
        active.add(cell)
        return len(cells[cell]['mos']) + sum(count(r['cell'], stack + (cell,)) for r in cells[cell]['instances'])
    total = count('ADC')
    counts = {'ADC': total}
    for name in ('sar_control', 'sar_cdac', 'sar_comparator'):
        counts[name] = count(name)
    return {'scope': 'Nominal authored geometry and connectivity. Symbolic models; no analog or native-CDF parameter equivalence claim for this export.',
            'fingers_scope': 'Fingers and native macro parameters are not exported; null is not a claim of one finger.',
            'active_hierarchy_cell_count': len(active), 'active_cells': sorted(active),
            'expanded_MOS_counts': counts, 'cells': {key: cells[key] for key in sorted(active)},
            'die_area_inferred_from_width_length': False}
