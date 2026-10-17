"""Compact transistor-only, native Spectre SAR control generator.

The external API and top-level ports match sar_logic.generate_sar_logic.
Only a five-stage Johnson counter retains master/slave flip-flops. Conversion
bits and output bits use one resettable latch each; flags are combinational.
All primitive gates and the proven interlocked phases come from sar_logic.
"""

try:
    from .sar_logic import SAR_CONTROL_PORTS, generate_sar_logic as _full_logic
except ImportError:
    from sar_logic import SAR_CONTROL_PORTS, generate_sar_logic as _full_logic


def generate_sar_logic(mos, prefix="sar", logic_l=30e-9):
    """Return compact control and the original transistor primitive helpers.

    mos(name,d,g,s,b,pmos,w,l) is the unchanged native PDK card callback.
    Supplies are first on every subcircuit. The top is <prefix>_control.

    Ten decoded slots retain the original timing. q0/q1 track; q2..q9
    compare bits 7..0. A bit latch is transparent only
    during its selected slot AND the guarded master high phase. It closes
    before the counter's slaves can advance. Thus the first comparison sees a
    zero differential DAC, and each later comparison sees earlier decisions.

    The Johnson state j0..j4 starts at 00000 and advances as
    10000,11000,11100,11110,11111,01111,00111,00011,00001,00000.
    v_i is equivalent to OR(q_(slot_i+1)..q9), slot_i=9-i. v0 is always zero because the
    LSB decision is the final comparator result; applying its DAC step is
    unnecessary. The final bit is held across q9->q0, while track disables
    the entire DAC. Outputs are transparent only in q0 AND master phase,
    becoming stable at q0's falling edge, the same sampling point as the
    original controller. They begin updating during q0's high phase rather
    than changing atomically at its falling edge; sample after that edge.

    Only one Johnson state bit changes per edge. Direct resolved functions
    avoid suffix-OR handoff hazards; track=!j1 AND !j4 remains constant
    across q0->q1. Verify actual propagation/settling with the PDK models.
    A held asynchronous reset is required to initialize the counter into
    its ten-state cycle, as with the original onehot ring. Both single-latch
    register banks retain the original reset0 behavior.
    """
    primitive_text = _full_logic(mos, prefix=prefix, logic_l=logic_l)
    marker = "\nsubckt " + prefix + "_control "
    if marker not in primitive_text:
        raise ValueError("original logic generator control declaration missing")
    # Keep primitives, phases, storage cells and standalone DFF wrappers;
    # replace only the original control definition in the returned text.
    lines = [primitive_text.split(marker, 1)[0].rstrip(), "",
             "// Three-input NAND, used to select a bit slot and master phase.",
             "subckt " + prefix + "_nand3 vdd vss a b c y"]
    for k, gate in enumerate(("a", "b", "c")):
        lines.append(mos("Mp" + str(k), "y", gate, "vdd", "vdd",
                         True, 1e-6, logic_l).rstrip("\r\n"))
    for k, (d, gate, source) in enumerate((
            ("y", "a", "n0"), ("n0", "b", "n1"), ("n1", "c", "vss"))):
        # 2 um is an available native card and compensates the series stack.
        lines.append(mos("Mn" + str(k), d, gate, source, "vss",
                         False, 2e-6, logic_l).rstrip("\r\n"))
    lines.extend(["ends " + prefix + "_nand3", "",
                  "// Compact control: 5 Johnson DFFs, 16 static single latches.",
                  "// Direct resolved flags; v0 is permanently LOW.",
                  "// D7..D0 must be sampled after the q0 falling edge.",
                  "subckt " + prefix + "_control " + " ".join(SAR_CONTROL_PORTS)])

    def inst(name, nodes, circuit):
        lines.append("X" + name + " (vdd vss " + nodes + ") " + prefix + "_" + circuit)

    inst("reset_inv", "RST nrst", "inv")
    inst("clock_phases", "CLK phm phmb phs phsb", "phases")
    for j in range(5):
        previous = "j4b" if j == 0 else "j" + str(j - 1)
        inst("johnson" + str(j),
             previous + " phm phmb phs phsb RST nrst j" + str(j), "pdffr0")
        inst("johnson_inv" + str(j), "j{0} j{0}b".format(j), "inv")

    inst("q0_decode", "j0b j4b q0", "and2")
    inst("track", "j1 j4 track", "nor2")
    inst("not_track", "track ntrack", "inv")
    inst("compare_clock", "phm ntrack cmpclk", "and2")

    # Complementary enables from a NAND and inverter avoid a redundant
    # inversion; the enables are shared by both TGs in the static latch.
    selected_literals = {
        7: ("j1", "j2b"), 6: ("j2", "j3b"), 5: ("j3", "j4b"),
        4: ("j0", "j4"), 3: ("j0b", "j1"), 2: ("j1b", "j2"),
        1: ("j2b", "j3"), 0: ("j3b", "j4"),
    }
    for bit in range(7, -1, -1):
        a, b = selected_literals[bit]
        inst("bit_enable_n" + str(bit),
             "{0} {1} phm benb{2}".format(a, b, bit), "nand3")
        inst("bit_enable" + str(bit),
             "benb{0} ben{0}".format(bit), "inv")
        inst("bit" + str(bit),
             "cmpQ ben{0} benb{0} RST nrst b{0}".format(bit), "latchr0")

    inst("valid7", "j2 j4 v7", "or2")
    inst("valid6", "j3 j4 v6", "or2")
    inst("valid5", "j4 v5", "buf_hi")
    for bit in range(4, 0, -1):
        inst("valid" + str(bit), "j4 j{0}b v{1}".format(4 - bit, bit), "and2")
    # A real inverter drives LOW. No ideal voltage source or node alias.
    inst("valid0_low", "vdd v0", "inv")

    inst("output_enable_n", "q0 phm oenb", "nand2")
    inst("output_enable", "oenb oen", "inv_hi")
    for bit in range(7, -1, -1):
        inst("output" + str(bit),
             "b{0} oen oenb RST nrst D{0}".format(bit), "latchr0")

    lines.append("ends " + prefix + "_control")
    return "\n".join(lines) + "\n"
