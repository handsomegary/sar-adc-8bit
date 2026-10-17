#!/usr/bin/env python3
"""Analyze measured/simulated ADC output codes without third-party packages.

Python 3.6+; all voltage, time, and code data must come from the actual simulation.
Dynamic analysis expects one settled output code per conversion, a uniformly
spaced record, and a coherent sine (fin / fs = m / N). It removes only DC and
the fundamental from the noise-plus-distortion sum. In particular, harmonics
are included in SNDR. No window or harmonic exclusions are silently applied.

Examples:
  python sar_analysis.py selftest
  python sar_analysis.py dynamic samples.csv --bin 17 --n 256 --fs 20e6
  python sar_analysis.py dynamic transient.csv --bin 17 --n 256 --fs 20e6 \
      --clock eoc --threshold 0.45 --delay 1e-9 --skip 10
  python sar_analysis.py ramp ramp.csv --threshold 0.45

CSV accepts a decimal/hex ``code`` column or d7,...,d0 for an 8-bit ADC. Analog
bit waveforms require an explicit threshold. Sampling a clock/EOC edge also
requires a marker threshold (``--clock-threshold`` or ``--threshold``). Positive
``--delay`` selects the first recorded point at/after edge + delay, so the user
can allow output transitions to settle. Without a clock column, every CSV row
is treated as an already sampled code; raw transient solver points are not
uniform ADC samples and must not be analyzed that way.

Static endpoint-fit INL uses transitions T1 and T(2**bits-1) to remove offset and
gain. DNL covers only bounded interior bins (codes 1 through 2**bits-2), since
the two saturated end bins have no finite width unless input limits are defined.
Skipped codes in a finite ramp are *unresolved*, not proof of missing codes.
"""

import argparse
import bisect
import cmath
import csv
import json
import math
import sys


def _finite(value, label):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("{} must be finite".format(label))
    return result


def _validate_codes(codes, bits):
    if not isinstance(bits, int) or not 1 <= bits <= 32:
        raise ValueError("bits must be an integer from 1 through 32")
    maximum = (1 << bits) - 1
    result = []
    for index, value in enumerate(codes):
        numeric = _finite(value, "code[{}]".format(index))
        if numeric != int(numeric) or not 0 <= numeric <= maximum:
            raise ValueError("code[{}]={} is not an unsigned {}-bit code".format(
                index, value, bits))
        result.append(int(numeric))
    if not result:
        raise ValueError("no codes supplied")
    return result


def _fft_radix2(values):
    """Unnormalized forward FFT, matching the usual exp(-j*2*pi*k*n/N)."""
    n = len(values)
    if n < 2 or (n & (n - 1)):
        raise ValueError("FFT record length must be a power of two, at least 2")
    data = [complex(value) for value in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    span = 2
    while span <= n:
        step = cmath.exp(-2j * math.pi / span)
        half = span >> 1
        for start in range(0, n, span):
            phase = 1.0 + 0j
            for offset in range(half):
                even = data[start + offset]
                odd = phase * data[start + offset + half]
                data[start + offset] = even + odd
                data[start + offset + half] = even - odd
                phase *= step
        span <<= 1
    return data


def _db_ratio(numerator, denominator):
    if numerator <= 0:
        return float("-inf")
    if denominator <= 0:
        return float("inf")
    return 10.0 * math.log10(numerator / denominator)


def analyze_dynamic(codes, fundamental_bin=None, fs=None, bits=8,
                    fin=None, sample_times=None):
    """Return coherent FFT SNDR and ENOB from unsigned integer output codes.

    ``fundamental_bin`` is m in fin = m*fs/N, not an arbitrary FFT search width.
    If fin and fs are both supplied, exact coherence is checked. If no bin or
    frequency is supplied, the strongest AC bin is selected and flagged. An
    optional ``sample_times`` sequence checks that these are actual uniformly
    spaced conversion samples. Output ``spectrum_power_code2`` contains N/2+1
    one-sided powers whose sum equals the mean-square record (after DC removal).
    """
    values = _validate_codes(codes, bits)
    n = len(values)
    warnings = []
    if fs is not None:
        fs = _finite(fs, "fs")
        if fs <= 0:
            raise ValueError("fs must be positive")
    if sample_times is not None:
        times = [_finite(t, "sample time") for t in sample_times]
        if len(times) != n:
            raise ValueError("sample_times and codes must have equal lengths")
        steps = [times[i] - times[i - 1] for i in range(1, n)]
        if not steps or min(steps) <= 0:
            raise ValueError("sample times must strictly increase")
        period = sum(steps) / len(steps)
        if max(abs(step - period) for step in steps) > period * 0.01:
            raise ValueError("sample times are not uniform to within 1%; extract one code per conversion")
        if fs is not None and abs(period * fs - 1.0) > 0.01:
            raise ValueError("sample interval is inconsistent with fs by more than 1%")
        if fs is None:
            fs = 1.0 / period
    if fin is not None:
        if fs is None:
            raise ValueError("fin requires fs")
        cycles = _finite(fin, "fin") * n / fs
        nearest = int(round(cycles))
        if abs(cycles - nearest) > 1e-7:
            raise ValueError("noncoherent record: fin/fs*N={}; use an exact coherent tone".format(cycles))
        if fundamental_bin is not None and nearest != fundamental_bin:
            raise ValueError("fin disagrees with fundamental_bin")
        fundamental_bin = nearest
    average = sum(values) / float(n)
    centered = [value - average for value in values]
    spectrum = _fft_radix2(centered)
    scale = float(n * n)
    powers = []
    for k in range(n // 2 + 1):
        weight = 1.0 if k in (0, n // 2) else 2.0
        powers.append(weight * abs(spectrum[k]) ** 2 / scale)
    powers[0] = 0.0
    if fundamental_bin is None:
        fundamental_bin = max(range(1, len(powers)), key=lambda k: powers[k])
        warnings.append("Fundamental selected as strongest AC bin; verify it matches the applied coherent tone.")
    if (not isinstance(fundamental_bin, int) or
            not 1 <= fundamental_bin <= n // 2):
        raise ValueError("fundamental_bin must be an integer from 1 through N/2")
    if math.gcd(fundamental_bin, n) != 1:
        warnings.append("Tone bin and record length are not relatively prime; the record repeats a smaller set of phases.")
    signal = powers[fundamental_bin]
    if signal <= 0:
        raise ValueError("record has no power in the specified fundamental bin")
    noise_distortion = math.fsum(powers[k] for k in range(1, len(powers))
                                  if k != fundamental_bin)
    total = math.fsum(powers[1:])
    sndr = _db_ratio(signal, noise_distortion)
    spur_bins = [k for k in range(1, len(powers)) if k != fundamental_bin]
    spur_bin = max(spur_bins, key=lambda k: powers[k]) if spur_bins else None
    spur_power = powers[spur_bin] if spur_bin is not None else 0.0
    if n <= 256:
        warnings.append("N<=256 is a short record: SNDR is tone/phase dependent and is insufficient for precise noise statistics or yield claims.")
    warnings.append("SNDR includes harmonics and all other AC bins; a noiseless transient run mainly measures quantization and deterministic distortion, not full transistor noise.")
    result = {
        "bits_nominal": bits,
        "n": n,
        "fundamental_bin": fundamental_bin,
        "fs_hz": fs,
        "fin_hz": (fundamental_bin * fs / n) if fs is not None else None,
        "mean_code": average,
        "min_code": min(values),
        "max_code": max(values),
        "signal_power_code2": signal,
        "noise_distortion_power_code2": noise_distortion,
        "total_ac_power_code2": total,
        "sndr_db": sndr,
        "enob": (sndr - 1.76) / 6.02,
        "sfdr_db": _db_ratio(signal, spur_power),
        "largest_spur_bin": spur_bin,
        "spectrum_power_code2": powers,
        "warnings": warnings,
    }
    return result


def analyze_transitions(transition_voltages, bits=8):
    """Endpoint-fit static DNL/INL from independently obtained transitions.

    Supply a list [T1,...,T255] for 8 bits, or a dict keyed by transition number
    1,...,255. Repeated transitions mean zero-width/missing interior codes;
    descending transitions are invalid for a monotonic ADC transfer function.
    Offset and gain are excluded. Values are in the same input voltage unit.
    """
    if not isinstance(bits, int) or not 2 <= bits <= 32:
        raise ValueError("static bits must be an integer from 2 through 32")
    count = 1 << bits
    if isinstance(transition_voltages, dict):
        normalized = {int(key): value for key, value in transition_voltages.items()}
        absent = [k for k in range(1, count) if k not in normalized]
        if absent:
            raise ValueError("missing/unresolved transition numbers: {}".format(absent))
        transitions = [_finite(normalized[k], "T{}".format(k)) for k in range(1, count)]
    else:
        transitions = [_finite(value, "transition") for value in transition_voltages]
        if len(transitions) != count - 1:
            raise ValueError("expected {} transition voltages, got {}".format(count - 1, len(transitions)))
    if any(transitions[i] < transitions[i - 1] for i in range(1, len(transitions))):
        raise ValueError("transitions descend; this is not a monotonic transfer curve")
    lsb = (transitions[-1] - transitions[0]) / float(count - 2)
    if lsb <= 0:
        raise ValueError("transition span must be positive")
    inl = [(value - (transitions[0] + (k - 1) * lsb)) / lsb
           for k, value in enumerate(transitions, 1)]
    widths = [transitions[k] - transitions[k - 1] for k in range(1, count - 1)]
    dnl = [width / lsb - 1.0 for width in widths]
    return {
        "bits_nominal": bits,
        "fit_method": "endpoint transition fit (T1 and T{})".format(count - 1),
        "lsb_voltage": lsb,
        "t1_voltage": transitions[0],
        "offset_fit_voltage": transitions[0] - lsb,
        "dnl_code_numbers": list(range(1, count - 1)),
        "dnl_lsb": dnl,
        "dnl_min_lsb": min(dnl),
        "dnl_max_lsb": max(dnl),
        "inl_transition_numbers": list(range(1, count)),
        "inl_lsb": inl,
        "inl_min_lsb": min(inl),
        "inl_max_lsb": max(inl),
        "missing_interior_codes": [k for k, width in enumerate(widths, 1) if width == 0.0],
        "warnings": ["DNL excludes saturated end bins 0 and {}; offset and gain are removed by endpoint fit.".format(count - 1)],
    }


def analyze_ramp(input_voltages, codes, bits=8):
    """Bracket transition voltages using a settled, monotonically sampled ramp.

    Input may increase or decrease. Its direction is reversed for analysis;
    arbitrary sorting is not performed, since sorting can conceal hysteresis
    or output timing errors. A transition is estimated at the midpoint of the
    two adjacent input samples bracketing it. The uncertainty is half that
    interval. A code jump larger than one is left unresolved. Capture enough
    voltage range to observe codes 0 and full-scale, and use a ramp step much
    smaller than one LSB (preferably <=1/16 LSB).
    """
    output = _validate_codes(codes, bits)
    voltages = [_finite(value, "ramp input") for value in input_voltages]
    if len(voltages) != len(output) or len(output) < 2:
        raise ValueError("ramp voltages and codes must have equal lengths >=2")
    if voltages[-1] < voltages[0]:
        voltages.reverse()
        output.reverse()
    if any(voltages[i] <= voltages[i - 1] for i in range(1, len(voltages))):
        raise ValueError("ramp input must be strictly monotonic")
    if any(output[i] < output[i - 1] for i in range(1, len(output))):
        raise ValueError("ramp output decreases with increasing input; check settling, bit ordering, noise, or hysteresis")
    transitions = {}
    uncertainties = {}
    unresolved_jumps = []
    for i in range(1, len(output)):
        prior, current = output[i - 1], output[i]
        if current == prior + 1:
            transitions[current] = (voltages[i - 1] + voltages[i]) * 0.5
            uncertainties[current] = (voltages[i] - voltages[i - 1]) * 0.5
        elif current > prior + 1:
            unresolved_jumps.append({
                "from_code": prior, "to_code": current,
                "v_low": voltages[i - 1], "v_high": voltages[i],
                "unresolved_transition_numbers": list(range(prior + 1, current + 1)),
            })
    count = 1 << bits
    missing_transitions = [k for k in range(1, count) if k not in transitions]
    result = {
        "n_ramp_points": len(output),
        "min_observed_code": min(output),
        "max_observed_code": max(output),
        "observed_code_count": len(set(output)),
        "unobserved_codes": [k for k in range(count) if k not in set(output)],
        "transition_voltages": transitions,
        "transition_bracket_halfwidth_voltage": uncertainties,
        "unresolved_jumps": unresolved_jumps,
        "unresolved_transition_numbers": missing_transitions,
        "complete_transfer": not missing_transitions,
        "static": None,
        "warnings": [],
    }
    if missing_transitions:
        result["warnings"].append("Transfer is incomplete/unresolved; unobserved codes may be due to coarse ramp steps or insufficient span. They are not proof of missing codes.")
    else:
        result["static"] = analyze_transitions(transitions, bits)
        lsb = result["static"]["lsb_voltage"]
        halfwidth = max(uncertainties.values())
        result["max_transition_uncertainty_lsb"] = halfwidth / lsb
        result["bin_width_bracket_uncertainty_lsb"] = 2.0 * halfwidth / lsb
        result["fit_lsb_endpoint_uncertainty_voltage"] = (
            uncertainties[1] + uncertainties[count - 1]) / (count - 2)
        result["warnings"].append("Transition and bin-width uncertainty fields describe finite ramp brackets; fitted endpoint uncertainty is reported separately, not a statistical confidence interval.")
        if 2.0 * halfwidth > lsb / 16.0:
            result["warnings"].append("Ramp step exceeds 1/16 fitted LSB; use finer steps for accurate DNL/INL.")
    return result


def analyze_transition_brackets(brackets, bits=8, dnl_limit=0.5,
                                inl_limit=1.0):
    """Conservative deterministic DNL/INL bounds from threshold brackets.

    Each (low, high) must contain a *repeatable, actual* input transition Tk.
    Supply all 2**bits-1 intervals, or a dict keyed by transition number. These
    may come from a fine ramp or from complete-conversion threshold searches.
    Bounds include uncertainty in the endpoint-fit LSB. Shared endpoint
    correlations are ignored conservatively, except endpoint INL is exactly 0.
    This is not a confidence interval for transistor noise or mismatch yield.
    """
    count = 1 << bits
    if isinstance(brackets, dict):
        normalized = {int(key): value for key, value in brackets.items()}
        if any(k not in normalized for k in range(1, count)):
            raise ValueError("all transition brackets are required")
        intervals = [normalized[k] for k in range(1, count)]
    else:
        intervals = list(brackets)
    if len(intervals) != count - 1:
        raise ValueError("expected {} transition brackets".format(count - 1))
    parsed = []
    for interval in intervals:
        if len(interval) != 2:
            raise ValueError("each bracket must contain low and high voltage")
        low, high = (_finite(interval[0], "bracket low"),
                     _finite(interval[1], "bracket high"))
        if high < low:
            raise ValueError("transition bracket high is below low")
        parsed.append((low, high))
    mids = [(low + high) * 0.5 for low, high in parsed]
    midpoint = analyze_transitions(mids, bits)
    lsb_low = (parsed[-1][0] - parsed[0][1]) / float(count - 2)
    lsb_high = (parsed[-1][1] - parsed[0][0]) / float(count - 2)
    if lsb_low <= 0:
        raise ValueError("endpoint brackets are too wide to bound a positive LSB")
    dnl_bounds = []
    for i in range(count - 2):
        width_low = max(0.0, parsed[i + 1][0] - parsed[i][1])
        width_high = parsed[i + 1][1] - parsed[i][0]
        if width_high < 0:
            raise ValueError("transition brackets cannot form a monotonic transfer")
        dnl_bounds.append((width_low / lsb_high - 1.0,
                           width_high / lsb_low - 1.0))
    inl_bounds = []
    for i, (low, high) in enumerate(parsed):
        if i in (0, count - 2):
            inl_bounds.append((0.0, 0.0))
            continue
        fraction = i / float(count - 2)
        ideal_low = ((1.0 - fraction) * parsed[0][0] +
                     fraction * parsed[-1][0])
        ideal_high = ((1.0 - fraction) * parsed[0][1] +
                      fraction * parsed[-1][1])
        n_low, n_high = low - ideal_high, high - ideal_low
        ratios = [n_low / lsb_low, n_low / lsb_high,
                  n_high / lsb_low, n_high / lsb_high]
        inl_bounds.append((min(ratios), max(ratios)))
    dnl_ok = all(low >= -dnl_limit and high <= dnl_limit
                 for low, high in dnl_bounds)
    inl_ok = all(low >= -inl_limit and high <= inl_limit
                 for low, high in inl_bounds)
    failed_dnl = [i + 1 for i, (low, high) in enumerate(dnl_bounds)
                  if low > dnl_limit or high < -dnl_limit]
    failed_inl = [i + 1 for i, (low, high) in enumerate(inl_bounds)
                  if low > inl_limit or high < -inl_limit]
    status = ("proved_within_deterministic_brackets" if dnl_ok and inl_ok else
              "definite_failure_within_brackets" if failed_dnl or failed_inl else
              "inconclusive_brackets_need_refinement")
    return {
        "qualification_status": status,
        "midpoint_static": midpoint,
        "fitted_lsb_voltage_bounds": [lsb_low, lsb_high],
        "dnl_code_numbers": list(range(1, count - 1)),
        "dnl_lsb_bounds": dnl_bounds,
        "inl_transition_numbers": list(range(1, count)),
        "inl_lsb_bounds": inl_bounds,
        "dnl_limit_lsb": dnl_limit,
        "inl_limit_lsb": inl_limit,
        "dnl_proved_within_brackets": dnl_ok,
        "inl_proved_within_brackets": inl_ok,
        "definitely_failing_dnl_codes": failed_dnl,
        "definitely_failing_inl_transitions": failed_inl,
        "worst_dnl_bound_magnitude_lsb": max(max(abs(a), abs(b)) for a, b in dnl_bounds),
        "worst_inl_bound_magnitude_lsb": max(max(abs(a), abs(b)) for a, b in inl_bounds),
        "warnings": [
            "Conditional on every supplied bracket containing a repeatable actual transition; uncertainty intervals do not establish this premise.",
            "Deterministic endpoint-fit qualification excludes end-bin DNL, offset, gain, transistor noise, process mismatch, and untested corners.",
        ],
    }


def fit_comparator_probability(grouped_trials, input_column="input_diff_V",
                               positive_column="positive_decisions",
                               count_column="samples", grid_points=41,
                               refinements=4):
    """Fit P(Q=1|v)=Phi((v-offset)/sigma) by binomial likelihood grid search.

    Input is a list of dictionaries containing voltage and repeated decision
    counts, e.g. the comparator-only test's ``grouped`` rows. Fit histories,
    common modes, and corners separately; mixing them can mislabel deterministic
    memory or offset variation as Gaussian noise. Sigma is referred to the
    *comparator differential input*, not automatically the ADC external input.
    No analog noise conclusion is valid from noiseless deterministic trials.
    This function therefore reports identifiability instead of a forced pass.
    """
    combined = {}
    for row in grouped_trials:
        voltage = _finite(row[input_column], "comparator differential input")
        successes = _finite(row[positive_column], "positive decisions")
        count = _finite(row[count_column], "trial count")
        if count != int(count) or successes != int(successes) or not 0 <= successes <= count or count <= 0:
            raise ValueError("trial and positive-decision counts must be valid integers")
        prior = combined.get(voltage, (0, 0))
        combined[voltage] = (prior[0] + int(successes), prior[1] + int(count))
    trials = [(voltage, successes, count) for voltage, (successes, count) in sorted(combined.items())]
    if len(trials) < 3 or trials[-1][0] <= trials[0][0]:
        raise ValueError("need at least three distinct comparator input voltages")
    if grid_points < 11 or refinements < 1:
        raise ValueError("grid_points>=11 and refinements>=1 are required")
    width = trials[-1][0] - trials[0][0]
    min_step = min(trials[i][0] - trials[i - 1][0] for i in range(1, len(trials)))
    sigma_floor = min_step / 1000.0
    initial_mu = (trials[0][0] - width, trials[-1][0] + width)
    initial_log_sigma = (math.log(sigma_floor), math.log(width * 4.0))
    mu_bounds, log_bounds = initial_mu, initial_log_sigma

    def probability(voltage, offset, sigma):
        z = (voltage - offset) / sigma
        return max(1e-15, min(1.0 - 1e-15,
                             0.5 * math.erfc(-z / math.sqrt(2.0))))

    def likelihood(offset, sigma):
        total = 0.0
        for voltage, successes, count in trials:
            p = probability(voltage, offset, sigma)
            total += successes * math.log(p) + (count - successes) * math.log1p(-p)
        return total

    best = None
    for _ in range(refinements):
        mu_step = (mu_bounds[1] - mu_bounds[0]) / (grid_points - 1)
        log_step = (log_bounds[1] - log_bounds[0]) / (grid_points - 1)
        pass_best = None
        for i in range(grid_points):
            offset = mu_bounds[0] + i * mu_step
            for j in range(grid_points):
                log_sigma = log_bounds[0] + j * log_step
                sigma = math.exp(log_sigma)
                candidate = (likelihood(offset, sigma), offset, log_sigma)
                if pass_best is None or candidate[0] > pass_best[0]:
                    pass_best = candidate
        best = pass_best
        mu_bounds = (max(initial_mu[0], best[1] - 2 * mu_step),
                     min(initial_mu[1], best[1] + 2 * mu_step))
        log_bounds = (max(initial_log_sigma[0], best[2] - 2 * log_step),
                      min(initial_log_sigma[1], best[2] + 2 * log_step))
    offset, sigma = best[1], math.exp(best[2])
    mixed = sum(0 < successes < count for _, successes, count in trials)
    total_trials = sum(count for _, _, count in trials)
    at_boundary = (sigma <= sigma_floor * 1.01 or sigma >= width * 3.99 or
                   offset <= initial_mu[0] + width * 1e-5 or
                   offset >= initial_mu[1] - width * 1e-5)
    identifiable = mixed >= 2 and not at_boundary
    rows = [{"input_diff_V": voltage, "samples": count,
             "positive_decisions": successes,
             "observed_positive_fraction": successes / float(count),
             "fitted_positive_probability": probability(voltage, offset, sigma)}
            for voltage, successes, count in trials]
    warnings = [
        "Gaussian independent-decision model is an assumption; this fit alone does not prove Gaussian noise or independence.",
        "Keep opposite input histories/common modes/corners separate and compare offsets before interpreting sigma as noise.",
        "A comparator-only transient-noise fit excludes ADC sampling, CDAC switching, reference noise, and input-driver interaction.",
        "No confidence interval or 8-bit ADC pass is inferred from this point fit.",
    ]
    if not identifiable:
        warnings.append("Noise sigma is not reliably identifiable: require repeated noisy decisions and at least two voltages showing both output states, with the fit away from search limits.")
    if total_trials < 100 or min(count for _, _, count in trials) < 10:
        warnings.append("Few trials per voltage; expand repeats near the transition instead of treating all-0/all-1 outcomes as exact probabilities.")
    return {
        "model": "binomial likelihood, Gaussian input noise CDF",
        "offset_comparator_input_V": offset,
        "sigma_comparator_input_V": sigma if identifiable else None,
        "candidate_sigma_comparator_input_V": sigma,
        "sigma_identifiable": identifiable,
        "fit_at_search_boundary": at_boundary,
        "total_trials": total_trials,
        "mixed_outcome_voltage_count": mixed,
        "log_likelihood_without_binomial_constants": best[0],
        "sigma_search_floor_V": sigma_floor,
        "rows": rows,
        "warnings": warnings,
    }


def _parse_code(text):
    stripped = str(text).strip()
    if stripped.lower().startswith(("0x", "0b", "0o")):
        return int(stripped, 0)
    number = _finite(stripped, "CSV code")
    if number != int(number):
        raise ValueError("CSV code is not an integer: {}".format(stripped))
    return int(number)


def load_samples_csv(path, bits=8, code_column="code", time_column="time",
                     threshold=None, clock_column=None, clock_threshold=None,
                     edge="rising", sample_delay=0.0,
                     vdiff_column=None, vip_column="vip", vin_column="vin"):
    """Return records {code,time,vdiff} and extraction metadata from CSV.

    If a marker is used, returned time is its interpolated threshold crossing;
    the code is read from the first recorded row at/after crossing + delay.
    ``selected_row_time`` distinguishes the two. This does not interpolate
    transitioning output bits. For a ramp, each row/marker must correspond to a
    settled conversion, and vdiff must represent that conversion's sampled input.
    """
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no data rows")
    use_code = code_column in fields
    bit_columns = ["d{}".format(k) for k in range(bits)]
    if not use_code and not all(name in fields for name in bit_columns):
        raise ValueError("CSV needs column '{}' or all bit columns {}".format(code_column, bit_columns))
    if threshold is not None:
        threshold = _finite(threshold, "bit threshold")
    if vdiff_column is None:
        vdiff_column = next((name for name in ("vdiff", "v_diff", "input_voltage") if name in fields), None)
    parsed = []
    for i, row in enumerate(rows):
        if use_code:
            code = _parse_code(row[code_column])
        else:
            code = 0
            for k, name in enumerate(bit_columns):
                level = _finite(row[name], "row {} {}".format(i, name))
                if threshold is None:
                    if level not in (0.0, 1.0):
                        raise ValueError("analog bit levels require an explicit threshold")
                    bit = int(level)
                else:
                    bit = int(level >= threshold)
                code |= bit << k
        time = _finite(row[time_column], "CSV time") if time_column in fields else None
        if vdiff_column is not None:
            if vdiff_column not in fields:
                raise ValueError("no CSV column '{}'".format(vdiff_column))
            vdiff = _finite(row[vdiff_column], "CSV differential input")
        elif vip_column in fields and vin_column in fields:
            vdiff = _finite(row[vip_column], "vip") - _finite(row[vin_column], "vin")
        else:
            vdiff = None
        parsed.append({"code": code, "time": time, "vdiff": vdiff})
    _validate_codes([row["code"] for row in parsed], bits)
    metadata = {"source_rows": len(rows), "sampling": "one code per CSV row", "warnings": []}
    if clock_column is None:
        if time_column in fields:
            metadata["warnings"].append("No clock/EOC marker chosen; every row is assumed to be an already sampled conversion, not raw transient points.")
        return parsed, metadata
    if clock_column not in fields or time_column not in fields:
        raise ValueError("clock extraction requires the chosen clock and time columns")
    if edge not in ("rising", "falling"):
        raise ValueError("edge must be rising or falling")
    if clock_threshold is None:
        clock_threshold = threshold
    if clock_threshold is None:
        raise ValueError("clock extraction requires clock_threshold or threshold")
    marker_threshold = _finite(clock_threshold, "clock threshold")
    delay = _finite(sample_delay, "sample delay")
    if delay < 0:
        raise ValueError("sample_delay must be nonnegative")
    times = [row["time"] for row in parsed]
    if any(times[i] <= times[i - 1] for i in range(1, len(times))):
        raise ValueError("CSV times must strictly increase for edge extraction")
    markers = [_finite(row[clock_column], "clock marker") for row in rows]
    selected = []
    for i in range(1, len(rows)):
        low, high = markers[i - 1], markers[i]
        crossed = ((low < marker_threshold <= high) if edge == "rising"
                   else (low >= marker_threshold > high))
        if crossed:
            fraction = (marker_threshold - low) / (high - low)
            crossing = times[i - 1] + fraction * (times[i] - times[i - 1])
            pick = bisect.bisect_left(times, crossing + delay)
            if pick < len(rows):
                record = dict(parsed[pick])
                record["selected_row_time"] = times[pick]
                record["time"] = crossing
                selected.append(record)
    if not selected:
        raise ValueError("no usable {} marker edges found".format(edge))
    metadata["sampling"] = "{} edge of '{}' plus {} s".format(edge, clock_column, delay)
    metadata["sampled_rows"] = len(selected)
    metadata["warnings"].append("Verify marker-to-output latency and settling; extracted bits must belong to that completed conversion. Ramp input at code-read time may need an explicit sampled-input column.")
    return selected, metadata


def ideal_quantizer_sine(n=256, fundamental_bin=17, bits=8, peak_fraction=0.99,
                         phase=0.317):
    """Reference data only, not a transistor simulation or ADC design result."""
    levels = 1 << bits
    amplitude = 0.5 * peak_fraction
    codes = []
    for i in range(n):
        value = amplitude * math.sin(2.0 * math.pi * fundamental_bin * i / n + phase)
        code = int(math.floor((value + 0.5) * levels))
        codes.append(max(0, min(levels - 1, code)))
    return codes


def selftest():
    """Meaningful reference checks independent of simulated ADC waveforms."""
    short = analyze_dynamic(ideal_quantizer_sine(), fundamental_bin=17, bits=8)
    long = analyze_dynamic(ideal_quantizer_sine(n=4096, fundamental_bin=281),
                           fundamental_bin=281, bits=8)
    expected = 6.02 * 8 + 1.76 + 20.0 * math.log10(0.99)
    assert abs(long["sndr_db"] - expected) < 0.8, (long["sndr_db"], expected)
    assert 47.5 < short["sndr_db"] < 52.5, short["sndr_db"]
    short_codes = ideal_quantizer_sine()
    mean = sum(short_codes) / 256.0
    variance = sum((code - mean) ** 2 for code in short_codes) / 256.0
    assert abs(short["total_ac_power_code2"] - variance) < variance * 1e-12
    # Exact integer sequence: bin 64 cosine power=32; Nyquist power=256.
    # This catches accidental doubling of the Nyquist power and harmonic removal.
    mixed = [128 + 16 * ((-1) ** i) + 8 * (1, 0, -1, 0)[i % 4]
             for i in range(256)]
    mix_result = analyze_dynamic(mixed, fundamental_bin=64, bits=8)
    assert abs(mix_result["signal_power_code2"] - 32.0) < 1e-9
    assert abs(mix_result["noise_distortion_power_code2"] - 256.0) < 1e-9
    assert abs(mix_result["sndr_db"] - 10.0 * math.log10(32.0 / 256.0)) < 1e-9
    # Ideal offset/gain-shifted transitions still have zero endpoint-fit INL/DNL.
    static = analyze_transitions([0.13 + k * 0.0031 for k in range(1, 256)])
    assert max(abs(x) for x in static["dnl_lsb"]) < 1e-12
    assert max(abs(x) for x in static["inl_lsb"]) < 1e-12
    assert static["missing_interior_codes"] == []
    # Dense reference ramp visits all 256 codes; ADC/noise results are not implied.
    ramp_v = [(i + 0.5) / 4096.0 for i in range(4096)]
    ramp_c = [min(255, int(math.floor(value * 256.0))) for value in ramp_v]
    ramp = analyze_ramp(ramp_v, ramp_c)
    assert ramp["complete_transfer"] and ramp["observed_code_count"] == 256
    assert max(abs(x) for x in ramp["static"]["dnl_lsb"]) < 1e-12
    assert max(abs(x) for x in ramp["static"]["inl_lsb"]) < 1e-12
    # Coarse ramps and actual zero-width bins are explicitly distinct.
    coarse = analyze_ramp([0.0, 0.1, 0.2], [0, 2, 3])
    assert not coarse["complete_transfer"] and coarse["static"] is None
    absent = [k / 256.0 for k in range(1, 256)]
    absent[100] = absent[99]
    missing = analyze_transitions(absent)
    assert missing["missing_interior_codes"] == [100]
    # Narrow paired tests can bound static metrics without a 4096-point ramp.
    lsb = 1.0 / 256.0
    brackets = [(k * lsb - 0.125 * lsb, k * lsb + 0.125 * lsb)
                for k in range(1, 256)]
    bracket_result = analyze_transition_brackets(brackets)
    assert bracket_result["dnl_proved_within_brackets"]
    assert bracket_result["inl_proved_within_brackets"]
    assert 0.25 < bracket_result["worst_dnl_bound_magnitude_lsb"] < 0.252
    bad_brackets = [(k * lsb, k * lsb) for k in range(1, 256)]
    bad_brackets[127] = (128.7 * lsb, 128.7 * lsb)
    assert analyze_transition_brackets(bad_brackets)["qualification_status"] == "definite_failure_within_brackets"
    trial_voltages = [-0.002, -0.001, -0.0005, -0.00025,
                      0.00025, 0.0005, 0.001, 0.002]
    too_few = [{"input_diff_V": voltage, "positive_decisions": int(voltage > 0),
                "samples": 1} for voltage in trial_voltages]
    assert fit_comparator_probability(too_few)["sigma_comparator_input_V"] is None
    known_offset, known_sigma = 0.0001, 0.0008
    known_trials = [{
        "input_diff_V": voltage,
        "positive_decisions": int(round(100000 * 0.5 * math.erfc(
            -(voltage - known_offset) / known_sigma / math.sqrt(2.0)))),
        "samples": 100000,
    } for voltage in trial_voltages]
    known_fit = fit_comparator_probability(known_trials)
    assert abs(known_fit["offset_comparator_input_V"] - known_offset) < 5e-6
    assert abs(known_fit["sigma_comparator_input_V"] - known_sigma) < 5e-6
    return {
        "status": "passed",
        "ideal_8bit_sine_n256_sndr_db": short["sndr_db"],
        "ideal_8bit_sine_n4096_sndr_db": long["sndr_db"],
        "ideal_8bit_theoretical_sndr_db_at_99percent_amplitude": expected,
        "nyquist_energy_and_harmonic_inclusion": "passed",
        "parseval_energy": "passed",
        "endpoint_fit_removes_offset_gain": "passed",
        "dense_ideal_ramp_observed_codes": ramp["observed_code_count"],
        "coarse_ramp_not_labeled_missing_codes": "passed",
        "zero_width_bin_detection": "passed",
        "paired_transition_bounds_include_endpoint_gain": "passed",
        "definite_static_failure_not_labeled_pass": "passed",
        "single_trial_noise_not_identifiable": "passed",
        "known_gaussian_cdf_parameter_recovery": "passed",
        "notice": "Reference checks validate analysis mathematics; they are not simulated ADC performance.",
    }


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("selftest", help="run ideal-quantizer and energy-weight reference checks")
    for mode in ("dynamic", "ramp"):
        child = sub.add_parser(mode)
        child.add_argument("csv_path")
        child.add_argument("--bits", type=int, default=8)
        child.add_argument("--code-column", default="code")
        child.add_argument("--time-column", default="time")
        child.add_argument("--threshold", type=float)
        child.add_argument("--clock")
        child.add_argument("--clock-threshold", type=float)
        child.add_argument("--edge", choices=("rising", "falling"), default="rising")
        child.add_argument("--delay", type=float, default=0.0)
        child.add_argument("--skip", type=int, default=0, help="discard initial sampled conversions")
        child.add_argument("--vdiff-column")
        child.add_argument("--vip-column", default="vip")
        child.add_argument("--vin-column", default="vin")
        if mode == "dynamic":
            child.add_argument("--bin", type=int, dest="fundamental_bin")
            child.add_argument("--fin", type=float)
            child.add_argument("--fs", type=float)
            child.add_argument("--n", type=int, default=256)
            child.add_argument("--full-spectrum", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "selftest":
        print(json.dumps(_json_safe(selftest()), indent=2, ensure_ascii=False))
        return 0
    if args.mode is None:
        parser.print_help()
        return 2
    if args.skip < 0:
        raise ValueError("skip must be nonnegative")
    records, extraction = load_samples_csv(
        args.csv_path, bits=args.bits, code_column=args.code_column,
        time_column=args.time_column, threshold=args.threshold,
        clock_column=args.clock, clock_threshold=args.clock_threshold,
        edge=args.edge, sample_delay=args.delay, vdiff_column=args.vdiff_column,
        vip_column=args.vip_column, vin_column=args.vin_column)
    records = records[args.skip:]
    if args.mode == "dynamic":
        if len(records) < args.n:
            raise ValueError("need {} samples after skip, only {} available".format(args.n, len(records)))
        records = records[:args.n]
        times = [record["time"] for record in records]
        result = analyze_dynamic(
            [record["code"] for record in records], args.fundamental_bin,
            args.fs, args.bits, args.fin,
            sample_times=times if all(time is not None for time in times) else None)
        if not args.full_spectrum:
            result.pop("spectrum_power_code2")
    else:
        voltages = [record["vdiff"] for record in records]
        if any(value is None for value in voltages):
            raise ValueError("ramp needs a differential input column or vip/vin columns")
        result = analyze_ramp(voltages, [record["code"] for record in records], args.bits)
    result["extraction"] = extraction
    print(json.dumps(_json_safe(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, AssertionError) as error:
        print("analysis error: {}".format(error), file=sys.stderr)
        sys.exit(1)
