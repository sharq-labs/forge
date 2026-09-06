# `components.json` — what each field means and where it came from

35 resistors across four technologies and 23 package thermal resistances, all
read out of manufacturer datasheets. This file explains the fields, the method,
and the one thing the JEDEC numbers may not be used for.

## How the numbers were obtained

Each datasheet PDF was downloaded from the manufacturer's own document server
(the Vishay SFR16S entry uses a distributor mirror of the Vishay PDF, because
the 2025 revision of document 28722 no longer lists that type), its text
extracted, and the tables read directly.

**Values summarised from a PDF by a language model were not used, and there is
a specific reason.** The first attempt asked a summariser to read the Vishay
SFR25 datasheet. It returned *0.6 W at 70 °C, 500 V, −55 to +170 °C, ±100 ppm/K
for all resistance ranges, thermal resistance not specified*. The document
prints *0.4 W at 70 °C, 250 V, −55 to +155 °C, ±250 ppm/K below 4.7 Ω, thermal
resistance 200 K/W*. Five fields, five wrong. A benchmark whose ground truth
rests on numbers like those measures the summariser. Everything below was read
from extracted text.

## Fields

| Field | Meaning |
|---|---|
| `manufacturer`, `part_number` | The part as the datasheet names it. Where one datasheet covers several lead materials or tolerance grades that differ in a recorded number, they are separate entries (`PR02 (Cu lead)` and `PR02 (FeCu lead)` have different rated power and different thermal resistance). |
| `technology`, `package` | Thick film chip, metal film leaded, power metal film, Power Metal Strip, thick film on alumina. Package as the datasheet gives it — imperial chip size, DIN size, or a case style. |
| `resistance_range_ohm` | The span of values the type is made in. `note` carries the tolerance-grade split where the range depends on it. |
| `rated_power_w` + `rated_power_ambient_c` | **The pair is the specification; the wattage alone is not.** "0.4 W" is meaningless without "at 70 °C". Every film-resistor entry here is a P70 figure. The one exception is `bourns-pwr220t-20`, which is rated **20 W at 25 °C case temperature** — a different reference surface, flagged in `rated_power_reference`, and not comparable to a P70 without the thermal path from case to ambient. |
| `maximum_working_voltage_v` | The limiting element voltage (Vishay's *operating voltage, U<sub>max</sub> AC/DC*; Yageo's *maximum working voltage*). Below the value where P = V²/R would exceed the rating, the power rating binds first; above it, the voltage does. Two entries (`vishay-wsr5`, `bourns-pwr220t-20`) state a formula, √(P·R), rather than a number, because on a milliohm part the voltage limit is set by the power. |
| `maximum_overload_voltage_v` | Yageo only: a short-duration overload figure, **not** a continuous rating. |
| `temperature_coefficient_ppm_per_k` | A list, because TCR is banded by resistance value on almost every real part. A single ±100 ppm/K for a whole family is usually wrong at the ends of its range: the same Vishay SFR25 is ±250 ppm/K below 4.7 Ω and above 1 MΩ, and ±100 ppm/K in between. Entries with `value_min`/`value_max` instead of `value` are asymmetric bands (Yageo prints −200…+600 ppm/°C for its smallest values), which is not a ± tolerance and cannot be reduced to one. |
| `operating_temperature_range_c` | The category temperature range. `null` where the datasheet does not print one. |
| `permissible_film_temperature_c`, `maximum_hot_spot_temperature_c` | The film or hot-spot limit, which is what the rated dissipation is actually protecting. The PR family's hot spot runs to 205–250 °C while the ambient rating is stated at 70 °C. |
| `thermal_resistance_k_per_w` | Published R<sub>th</sub> where the datasheet gives it: SFR16S 170, SFR25 200, SFR25H 150, PR01 135, PR02 75/115, PR03 60/75 K/W. `null` on the chip families and on MRS and WSR, which publish none. `thermal_resistance_kind` flags the Bourns entry, whose 6.5 °C/W is **junction-to-case**, not junction-to-ambient. |
| `derating` | `knee_c` is the ambient above which the rated dissipation must be reduced; `zero_power_c` is where the curve reaches zero. `read_from_graph: true` marks a value taken from a curve's axis labels rather than a table. `null` where no knee could be extracted at all. |
| `source` | Document number, revision date, title, URL. |

## What is *not* in here, and why

`left_out` in the JSON carries the count and the reason for each. In summary,
**27 datasheet numbers were wanted and not recorded**:

* **11** derating knees for the Yageo RC_L sizes — that datasheet draws the
  derating curve as an image and prints no knee temperature in text.
* **5** operating temperature ranges for the Vishay PR family — the document
  prints hot-spot and film limits but no category range, and a range must not
  be inferred from a hot-spot figure.
* **4** θ<sub>JA</sub> values for TI TPS62840 — the thermal table has four data
  columns and three board labels, and which board belongs to which column
  cannot be settled from the extracted text. Guessing the alignment would be
  inventing the board type.
* **4** θ<sub>JA</sub> values for TI LM2596 — its footnotes describe specific
  copper areas *and* claim a 4-layer JEDEC board. Both cannot describe the same
  number, so none of them is recorded as a JEDEC comparison value.
* **3** thermal resistances (MRS16, MRS25, WSR5) — not published.

## The JEDEC caveat, and what it implies for how these values may be used

JESD51-3 (the low-effective-thermal-conductivity test board) says its θ<sub>JA</sub>
values are intended for **comparing packages under standardised conditions**,
and are not intended to and do not predict performance in an application-specific
environment. JESD51-7 is the high-conductivity counterpart; JESD51-2A fixes the
still-air environment both are measured in.

Two of the datasheets here say so themselves, and the wording is reproduced
verbatim in `caveat_printed_verbatim`:

> The value of RθJA given in this table is only valid for comparison with other
> packages and cannot be used for design purposes.
> — Texas Instruments, LMR51430 datasheet, §7.4

**What follows for this benchmark.** A θ<sub>JA</sub> in this file is a property
of *a package on a named board in still air*, not of the package. So:

* Ranking two packages against each other, on the same standard and board, is
  what the number is for. `ti-opa333-dbv-sot23-5` at 220.8 °C/W dissipates worse
  than `ti-opa2333-drb-vson-8` at 46.7 °C/W, and that comparison is sound.
* Computing a junction temperature in an application — T<sub>J</sub> = T<sub>A</sub>
  + θ<sub>JA</sub>·P — is **the use the standard rules out**, because the board
  in the application is not the test board. A design that does this is making an
  error, and the number it used carries the warning against it.
* θ<sub>JA</sub> is not a heat-transfer coefficient and not an `hA`. Converting
  one into the other requires a surface area and an assumption about where the
  heat leaves, neither of which the JEDEC measurement supplies.

The conversion in `convert.py` uses θ<sub>JA</sub> to form the lumped model's
`ambient_conductance` as 1/θ<sub>JA</sub>. **That is exactly the prohibited use**,
and it is logged as an assumption on every case where it happens, precisely so
that the harness cannot make the error silently. See `README.md`, "What this does
not establish".

## Provenance of the package table, stated plainly

23 θ<sub>JA</sub> entries:

| | count |
|---|---|
| JESD number **and** board both printed in the datasheet | 2 |
| board described, no JESD document named | 7 |
| θ<sub>JA</sub> printed with only a methodology reference (TI's SPRA953) | 14 |

The target was 15–20 values "measured under JEDEC JESD51" with the standard and
board recorded for each. What published datasheets actually support is two fully
pinned, seven board-described and fourteen methodology-referenced. That is why
the field is called `jedec_standard_printed` and not `jedec_standard`: the
absence is recorded rather than filled in.
