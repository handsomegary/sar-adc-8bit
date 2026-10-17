# Architecture and implementation

The design retains eight output decisions while adapting the project target to 20 MS/s and 0.9 V. This target is an implementation choice, not a maximum-speed claim for a process node.

| Block | Expanded MOS | Function |
|---|---:|---|
| Compact controller | 424 | Johnson states, clock phases, bit storage and output storage |
| CDAC switching/control | 314 | Input sampling and differential bottom-plate selection |
| Comparator | 27 | 11 direct regenerative devices plus buffers and SR hold gates |
| POR inverters | 4 | Two reset inverters around an ideal RC power-on network |
| **ADC** | **769** | Recursive active hierarchy; unused helper definitions excluded |

The active hierarchy contains 16 cells. The authored generators are in `src/`; `design/topology.json` describes the active cells and their nominal device connections. `design/adc_topology.scs` is a model-independent connectivity export. Its structure can be regenerated without loading any licensed models.

## CDAC and signal convention

The nominal differential full scale is 1 Vpp, LSB 3.90625 mV, common mode 0.45 V, and ideal reference levels 0.2/0.7 V. Both sides contain 256 capacitor units: eight binary-weighted branches plus a dummy unit, at 5 fF per unit. Unresolved decisions connect to common mode. A positive comparison decision selects the differential subtracting DAC step. The last comparison supplies the LSB decision; no subsequent LSB DAC update is needed.

All capacitances are ideal schematic primitives. No physical MOM/MIM dimensions, matching, routing, density or extracted parasitics are inferred from them.

## Comparator and control

The StrongARM-type stage drives isolation buffers, followed by a NAND SR hold. The held result remains available during comparator reset. Five Johnson state bits generate ten slots: two acquisition slots and eight comparison slots. Bit latches close before the counter slaves advance. Outputs become stable after the designated output-latch closing edge; the acquisition timestamp and output-read timestamp are distinct.

The nominal external clock is 200 MHz, ten clocks per 20 MS/s conversion. Actual conversion timestamps are retained in every published CSV. Analysis uses one settled output code per conversion, not arbitrary transient solver rows.

## Geometry interpretation

Each emitted MOS callback call denotes one explicit instance. Published widths and lengths are **nominal requested geometry**, in metres. Separate parallel units remain separate instances; for example, two 3 µm devices per polarity form each nominal 6 µm sampling-switch polarity. Widths are not capacitances, and W×L is not a die-area estimate.

| Representative element | Unit W/L | Explicit parallel units | Nominal parallel width |
|---|---|---:|---:|
| Comparator input, each differential leg | NMOS 3 µm / 30 nm | 1 | 3 µm per leg |
| Sampling switch, each side | NMOS 3 µm / 30 nm and PMOS 3 µm / 30 nm | 2 of each polarity | 6 µm per polarity |
| Each bottom-plate TG path | NMOS 3 µm / 30 nm and PMOS 3 µm / 30 nm | 1 of each polarity | 3 µm per polarity |
| Small logic inverter | NMOS 0.5 µm / 30 nm and PMOS 1 µm / 30 nm | 1 of each polarity | 0.5/1 µm |

These are explicit instance counts, not a foundry `m` or finger setting. Differential legs and series-stack widths are not combined as if they were parallel devices.

The callback topology does not encode the process-specific finger/macro/instance parameters that accompanied the licensed simulation cards. `fingers: null` therefore means **not exported**, not one finger. No native-card parasitic parameters or process coefficients are reconstructed. A future process binding must supply complete authorized cards rather than changing W/L in a foreign card.

The archived private native deck was checked against the exported active-cell MOS node/polarity/nominal-geometry records before this release was assembled. That check concerns connectivity and nominal geometry; this repository does not distribute or revalidate the native parameter cards.
