# Design prompts

20 prompts. Give one to a model, capture what comes back in the shape `design_schema.json` describes, and label it with `label_template.md`. Nothing here calls an API.

Composition: choose_a_package 4, estimate_a_rise 4, full 7, judge_a_design 3, partial 8, pick_for_a_temperature 4, size_under_load 5, sparse 5

Rules these were written against:

1. No vocabulary from the tool under test.
2. No planted contradiction; stated numbers come from a real datasheet.
3. Under-specification is realistic, not a trap.
4. No forced choice between two bad options.
5. Ordinary difficulty.

---

## P01 — size_under_load (full)

> I need a 220 ohm series resistor across a 12 V rail. It sits in a sealed enclosure that runs at 55 C inside, no fan. I have Vishay SFR25 metal film parts in stock (0.4 W at 70 C, 250 V max, 200 K/W thermal resistance, -55 to +155 C). Is the SFR25 the right part here, and what will it run at? Show your working.

*Built around:* vishay-sfr25

## P02 — size_under_load (partial)

> Pick a chip resistor for a 10 ohm current-limit in a 5 V circuit. Board is a normal 4-layer FR4 with no airflow. Yageo RC series is fine - 0603 is 0.1 W and 75 V, 0805 is 0.125 W and 150 V, 1206 is 0.25 W and 200 V. Which size, and why that one?

*Built around:* yageo-rc0603, yageo-rc0805, yageo-rc1206

## P03 — size_under_load (sparse)

> What size chip resistor do I need to drop 24 V across 100 ohms?

*Built around:* vishay-crcw1206

## P04 — size_under_load (full)

> Bleeder resistor across a 400 V DC bus. I want it to discharge the bus and I can afford about 4 W steady. The cabinet ambient is 60 C. Vishay PR03 (Cu lead) is rated 3 W at 70 C with 60 K/W thermal resistance and 750 V maximum working voltage, hot spot limit 250 C. Size the resistance and tell me whether one PR03 does it.

*Built around:* vishay-pr03-cu

## P05 — size_under_load (partial)

> I'm using a Vishay WSR5 shunt (0.005 ohm, 5 W at 70 C) to measure current in a motor drive. Peak is 60 A for a few seconds, average is 15 A. Is the WSR5 adequate, and what shunt voltage do I get?

*Built around:* vishay-wsr5

## P06 — choose_a_package (full)

> A part dissipates 5 W continuously. Ambient is 40 C, still air, no heatsink. I've got three candidate packages with junction-to-ambient thermal resistances of 46.7, 111.2 and 220.8 C/W from their datasheets. Junction limit is 125 C. Which package can I use?

*Built around:* ti-opa2333-drb-vson-8, ti-opa333-dbv-sot23-5, ti-lm339-d-soic-14

## P07 — choose_a_package (partial)

> Choosing between a SOT-23-6 buck (TI LMR51430, RtJA 107.8 C/W) and a 9-pin VQFN-HR one (LMR43610, RtJA 84.4 C/W) for a 3 A design losing about 0.9 W. Which one keeps the junction cooler, and by roughly how much?

*Built around:* ti-lmr51430-ddc-sot23-6, ti-lmr43610-rpe-vqfn-hr-9

## P08 — choose_a_package (sparse)

> Is an HSOIC-8 with a thermal pad good enough for 2 W?

*Built around:* ti-tps54360-dda-hsoic-8

## P09 — choose_a_package (partial)

> Low-side switch, about 0.4 W of conduction loss, in a 70 C cabinet. SOT23 MOSFET datasheets quote 310 C/W junction to ambient on a bare footprint and 260 C/W with a 1 cm2 drain pad. Is SOT23 workable, or do I need to go bigger? Assume 150 C max junction.

*Built around:* nexperia-bss138p-sot23, diodes-dmn2041l

## P10 — pick_for_a_temperature (full)

> Downhole tool, ambient reaches 140 C. I need a 1 kohm chip resistor there. Yageo RC0201 is rated -55 to +125 C; RC0402 and Vishay CRCW0402 are rated -55 to +155 C. Dissipation is only about 5 mW. Which part, and is there anything else I should watch at that temperature?

*Built around:* yageo-rc0201, yageo-rc0402, vishay-crcw0402

## P11 — pick_for_a_temperature (partial)

> I need a reference divider that holds its value over -40 C to +85 C. Vishay MRS25 is +/-50 ppm/K, SFR25 is +/-100 ppm/K over most of its range. How much drift do I get from each across that span, and which should I use?

*Built around:* vishay-mrs25, vishay-sfr25

## P12 — pick_for_a_temperature (sparse)

> Which resistor family survives 250 C ambient?

*Built around:* vishay-wsr5

## P13 — pick_for_a_temperature (full)

> Bourns PWR220T-20, TO-220 thick film on alumina, 20 W at 25 C case, 6.5 C/W junction to case, -55 to +155 C. I want to run it at 8 W on a heatsink in a 50 C enclosure. What heatsink thermal resistance do I need, and what is the case running at?

*Built around:* bourns-pwr220t-20

## P14 — estimate_a_rise (full)

> Vishay SFR25H, 150 K/W, dissipating 0.3 W in 25 C still air. What does the body settle at, and how long does it take to get there? The part is about 0.25 g of ceramic and film.

*Built around:* vishay-sfr25h

## P15 — estimate_a_rise (partial)

> PR01 power film resistor, 135 K/W, running 0.8 W. Ambient is 45 C. How hot does it get, and is that a problem?

*Built around:* vishay-pr01

## P16 — estimate_a_rise (sparse)

> How hot does a 2512 chip resistor get at 1 W?

*Built around:* vishay-crcw2512

## P17 — estimate_a_rise (partial)

> A 47 ohm SFR25 sees a 20 V pulse for 30 seconds, then nothing for ten minutes, repeating. Ambient 25 C. Does it survive? The datasheet gives 0.4 W at 70 C and 200 K/W.

*Built around:* vishay-sfr25

## P18 — judge_a_design (full)

> Someone on my team specified a CRCW0805 (0.25 W at 70 C, 150 V max) as a 33 ohm ballast on a 24 V supply, in a 60 C enclosure. They say it is fine because it is under the voltage rating. Is the design sound? Give me a yes or no and the numbers behind it.

*Built around:* vishay-crcw0805

## P19 — judge_a_design (partial)

> Design review: 1 Mohm RCV2512 high-voltage chip resistor used as the top leg of a divider on a 2500 V bus. Rated 1 W at 70 C and 3000 V. Anything wrong with this?

*Built around:* vishay-rcv2512

## P20 — judge_a_design (sparse)

> Two 1206 resistors in parallel to share 0.4 W. Fine?

*Built around:* vishay-crcw1206, yageo-rc1206

