"""Static-CMOS control for a 10-slot, 8-bit differential SAR ADC.

This module only generates native Spectre text. It does not launch a simulator and
does not select MOS models.  ``mos`` must return a native-model instance line:

    mos(name, drain, gate, source, bulk, pmos, width_m, length_m)

Widths are restricted to 0.5, 1, 2, and 3 um; the default length is 30 nm.
The parent generator supplies all process-dependent device cards.

All flip-flops in the controller share buffered, interlocked master/slave
phases.  Masters close before slaves open, so every flip-flop captures the
old ring state at a falling edge.  Both storage stages have reset-dominant
gates; reset does not make the two stages transparent simultaneously.
"""

import re


SAR_CONTROL_PORTS = (
    "vdd", "vss", "CLK", "RST", "cmpQ", "track", "cmpclk", "q0",
    "b7", "b6", "b5", "b4", "b3", "b2", "b1", "b0",
    "v7", "v6", "v5", "v4", "v3", "v2", "v1", "v0",
    "D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0",
)


def generate_sar_logic(mos, prefix="sar", logic_l=30e-9):
    """Return transistor-only native Spectre logic and the control subcircuit.

    Interface: vdd vss CLK RST cmpQ track cmpclk q0, then b7..b0, v7..v0,
    D7..D0.  RST is active high.  cmpQ=1 selects the positive ADC half-code.
    b* are current conversion decisions; v* say which decisions are valid.
    D* hold the preceding completed conversion and update at q0's falling
    edge.  q0 and q1 are tracking slots, q2..q9 evaluate bits 7..0.

    cmpclk follows the guarded master high phase AND !track.  The guard
    delays comparator evaluation until all slave latches have closed, and
    delays comparator reset until all master input latches have closed.
    This is electrically safer than gating the raw external CLK directly.

    Standalone negative-edge DFF wrappers are also emitted: dffr0 and dffr1,
    with ports vdd vss d clk rst q. The controller uses shared-phase versions
    named pdffr0/pdffr1 to avoid clock-phase skew between ring and data.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", prefix):
        raise ValueError("prefix must be a SPICE identifier")
    if logic_l not in (30e-9, 60e-9):
        raise ValueError("logic_l must be 30 nm or 60 nm")

    lines = [
        "// 8-bit SAR logic: real-model MOS only; no ideal logic sources",
        "// Width/length units passed to the MOS callback are metres.",
        "// All subcircuits have vdd vss as their first two ports.",
        "// RST: active high. Ring initialization: q0=1, q1..q9=0.",
        "// Slot order: q0,q1 track; q2..q9 decide bits 7..0.",
        "// Output D7..D0 updates one slot after the final decision.",
    ]
    wn = 0.5e-6
    wp = 1.0e-6

    def sub(name):
        return prefix + "_" + name

    def supplies_first(nodes):
        fields = nodes.split()
        if fields[:2] == ["vdd", "vss"]:
            return " ".join(fields)
        if fields[-2:] != ["vdd", "vss"]:
            raise ValueError("subcircuit calls must supply vdd and vss")
        return " ".join(fields[-2:] + fields[:-2])

    def start(name, ports):
        lines.append("")
        lines.append("subckt " + sub(name) + " " + supplies_first(ports))

    def end(name):
        lines.append("ends " + sub(name))

    def device(name, d, g, s, b, pmos, width):
        card = mos(name, d, g, s, b, pmos, width, logic_l)
        if not isinstance(card, str) or not card.strip():
            raise TypeError("mos callback must return a nonempty SPICE line")
        lines.append(card.rstrip("\r\n"))

    def inst(name, nodes, circuit):
        lines.append("X" + name + " (" + supplies_first(nodes) + ") " + sub(circuit))

    start("inv", "a y vdd vss")
    device("Mp", "y", "a", "vdd", "vdd", True, wp)
    device("Mn", "y", "a", "vss", "vss", False, wn)
    end("inv")

    start("inv_hi", "a y vdd vss")
    device("Mp", "y", "a", "vdd", "vdd", True, 3e-6)
    device("Mn", "y", "a", "vss", "vss", False, 2e-6)
    end("inv_hi")

    start("nand2", "a b y vdd vss")
    device("Mp0", "y", "a", "vdd", "vdd", True, wp)
    device("Mp1", "y", "b", "vdd", "vdd", True, wp)
    # Series devices are doubled relative to the base inverter.
    device("Mn0", "y", "a", "ns", "vss", False, 1e-6)
    device("Mn1", "ns", "b", "vss", "vss", False, 1e-6)
    end("nand2")

    start("nor2", "a b y vdd vss")
    device("Mp0", "ps", "a", "vdd", "vdd", True, 2e-6)
    device("Mp1", "y", "b", "ps", "vdd", True, 2e-6)
    device("Mn0", "y", "a", "vss", "vss", False, wn)
    device("Mn1", "y", "b", "vss", "vss", False, wn)
    end("nor2")

    start("and2", "a b y vdd vss")
    inst("n", "a b yn vdd vss", "nand2")
    inst("i", "yn y vdd vss", "inv")
    end("and2")

    start("or2", "a b y vdd vss")
    inst("n", "a b yn vdd vss", "nor2")
    inst("i", "yn y vdd vss", "inv")
    end("or2")

    start("tg", "a y en enb vdd vss")
    device("Mn", "y", "en", "a", "vss", False, wn)
    device("Mp", "y", "enb", "a", "vdd", True, wp)
    end("tg")

    start("mux", "d0 d1 sel y vdd vss")
    inst("s", "sel selb vdd vss", "inv")
    inst("t0", "d0 y selb sel vdd vss", "tg")
    inst("t1", "d1 y sel selb vdd vss", "tg")
    end("mux")

    start("buf_hi", "a y vdd vss")
    inst("i0", "a an vdd vss", "inv")
    inst("i1", "an y vdd vss", "inv_hi")
    end("buf_hi")

    start("phases", "clk phm phmb phs phsb vdd vss")
    inst("ci", "clk clkb vdd vss", "inv")
    # Cross-coupling senses the final buffered outputs, not raw gate nodes.
    # A closing phase must reach LOW before the opposite phase can open.
    inst("mn", "clkb phs mraw vdd vss", "nor2")
    inst("sn", "clk phm sraw vdd vss", "nor2")
    inst("mb", "mraw phm vdd vss", "buf_hi")
    inst("sb", "sraw phs vdd vss", "buf_hi")
    inst("mi", "phm phmb vdd vss", "inv_hi")
    inst("si", "phs phsb vdd vss", "inv_hi")
    end("phases")

    for init in (0, 1):
        name = "latchr" + str(init)
        start(name, "d en enb rst nrst q vdd vss")
        inst("in", "d x en enb vdd vss", "tg")
        inst("fb", "q x enb en vdd vss", "tg")
        if init == 0:
            # Reset forces qb=1 and q=0, even if the input TG is closed.
            inst("g", "x nrst qb vdd vss", "nand2")
        else:
            # Reset forces qb=0 and q=1.
            inst("g", "x rst qb vdd vss", "nor2")
        inst("o", "qb q vdd vss", "inv")
        end(name)

        pname = "pdffr" + str(init)
        start(pname, "d phm phmb phs phsb rst nrst q vdd vss")
        inst("master", "d phm phmb rst nrst mq vdd vss", name)
        inst("slave", "mq phs phsb rst nrst q vdd vss", name)
        end(pname)

        dname = "dffr" + str(init)
        start(dname, "d clk rst q vdd vss")
        inst("ri", "rst nrst vdd vss", "inv")
        inst("ph", "clk phm phmb phs phsb vdd vss", "phases")
        inst("ff", "d phm phmb phs phsb rst nrst q vdd vss", pname)
        end(dname)

    start("control", " ".join(SAR_CONTROL_PORTS))
    inst("reset_inv", "RST nrst vdd vss", "inv")
    inst("clock_phases", "CLK phm phmb phs phsb vdd vss", "phases")

    # Every master is closed before any ring or data slave opens.
    for j in range(10):
        previous = (j - 1) % 10
        nodes = "q{0} phm phmb phs phsb RST nrst q{1} vdd vss".format(
            previous, j)
        inst("ring" + str(j), nodes, "pdffr1" if j == 0 else "pdffr0")

    inst("track", "q0 q1 track vdd vss", "or2")
    inst("not_track", "track ntrack vdd vss", "inv")
    inst("compare_clock", "phm ntrack cmpclk vdd vss", "and2")

    for bit in range(7, -1, -1):
        slot = 9 - bit
        # At the falling edge, the old ring q(slot) selects cmpQ for this bit.
        inst("bit_mux" + str(bit),
             "b{0} cmpQ q{1} bd{0} vdd vss".format(bit, slot), "mux")
        inst("bit" + str(bit),
             "bd{0} phm phmb phs phsb RST nrst b{0} vdd vss".format(bit),
             "pdffr0")

        inst("valid_or" + str(bit),
             "v{0} q{1} va{0} vdd vss".format(bit, slot), "or2")
        inst("valid_and" + str(bit),
             "ntrack va{0} vd{0} vdd vss".format(bit), "and2")
        inst("valid" + str(bit),
             "vd{0} phm phmb phs phsb RST nrst v{0} vdd vss".format(bit),
             "pdffr0")

        # q9->q0 commits bit0; q0->q1 copies all eight completed bits.
        inst("output_mux" + str(bit),
             "D{0} b{0} q0 od{0} vdd vss".format(bit), "mux")
        inst("output" + str(bit),
             "od{0} phm phmb phs phsb RST nrst D{0} vdd vss".format(bit),
             "pdffr0")

    end("control")
    return "\n".join(lines) + "\n"
