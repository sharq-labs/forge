"""Write the design prompts to a file. Calls no API.

What a prompt here is
---------------------
An ordinary request to design something, in the words a working engineer would
use, built around a part that exists and whose datasheet numbers are in
``components.json``. The model being asked is not told what will be checked, is
not told that anything will be checked, and is not told that this is an
evaluation.

The rules these prompts follow, and why each one matters
-------------------------------------------------------
**A prompt engineered to elicit an error measures nothing.** The failure rate is
the finding, not the target. Five rules keep that true, and every prompt below
was written against them:

1. **No vocabulary from the tool.** No prompt says Biot, Fourier, lumped,
   applicability, validity, derating curve, excursion, emissivity, or
   linearisation. A model that hears "check the Biot number" will check the
   Biot number, and the benchmark would then measure whether the prompt worked.

2. **No planted contradiction.** Where a prompt states numbers, they are
   consistent and drawn from a real datasheet. None is quietly a factor of two
   off, none names a temperature outside the part's own range, none asks for a
   part to be used past a rating. If a design comes back over a limit, the model
   put it there.

3. **Under-specification is realistic, not a trap.** Real requests omit the
   ambient, the airflow, the board, the duty cycle and the mounting. Prompts
   here omit those too, in the proportions a real inbox does. The interesting
   question is what a designer does with a gap: state the assumption, ask, or
   silently fill it. That is a property of the answer, not of the prompt.

4. **No forced choice between two bad options.** Where a prompt offers
   candidates, at least one is a defensible answer.

5. **Ordinary difficulty.** Five prompt families, deliberately mundane: size a
   resistor under a load, choose a package for a dissipation, pick a material or
   part for a temperature, estimate a temperature rise, and judge whether a
   stated design is safe. Nothing exotic; the claim under test is about ordinary
   design, so the prompts are ordinary.

Information level
-----------------
Each prompt records ``information_level``:

* ``full`` — everything needed for a defensible answer is stated.
* ``partial`` — one or two ordinary facts are missing (ambient, airflow, duty).
* ``sparse`` — the request is a sentence, as it often arrives.

Under-specified prompts are where the interesting errors live, so the set is
weighted towards them: 6 full, 8 partial, 6 sparse.

Usage
-----
    python benchmarks/ai_designs/generate_prompts.py
        [--components components.json] [--out prompts.json] [--md prompts.md]

Writes both a machine-readable ``prompts.json`` and a human-readable
``prompts.md``. It contacts nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

#: The five families. A benchmark that only asked one kind of question would
#: measure one kind of mistake.
FAMILIES = (
    "size_under_load",
    "choose_a_package",
    "pick_for_a_temperature",
    "estimate_a_rise",
    "judge_a_design",
)

#: The 20 seed prompts. Written out rather than generated from templates,
#: because a template that fills a slot writes twenty versions of one prompt and
#: this set is meant to vary in shape as well as in numbers. `parts` names the
#: `components.json` ids each prompt is built around, so a reader can check that
#: every number in a prompt is one the datasheet prints.
SEEDS: tuple[dict, ...] = (
    # ---- size a resistor under a load -----------------------------------
    {
        "id": "P01",
        "family": "size_under_load",
        "information_level": "full",
        "parts": ["vishay-sfr25"],
        "prompt": (
            "I need a 220 ohm series resistor across a 12 V rail. It sits in a "
            "sealed enclosure that runs at 55 C inside, no fan. I have Vishay "
            "SFR25 metal film parts in stock (0.4 W at 70 C, 250 V max, 200 K/W "
            "thermal resistance, -55 to +155 C). Is the SFR25 the right part "
            "here, and what will it run at? Show your working."
        ),
    },
    {
        "id": "P02",
        "family": "size_under_load",
        "information_level": "partial",
        "parts": ["yageo-rc0603", "yageo-rc0805", "yageo-rc1206"],
        "prompt": (
            "Pick a chip resistor for a 10 ohm current-limit in a 5 V circuit. "
            "Board is a normal 4-layer FR4 with no airflow. Yageo RC series is "
            "fine - 0603 is 0.1 W and 75 V, 0805 is 0.125 W and 150 V, 1206 is "
            "0.25 W and 200 V. Which size, and why that one?"
        ),
    },
    {
        "id": "P03",
        "family": "size_under_load",
        "information_level": "sparse",
        "parts": ["vishay-crcw1206"],
        "prompt": (
            "What size chip resistor do I need to drop 24 V across 100 ohms?"
        ),
    },
    {
        "id": "P04",
        "family": "size_under_load",
        "information_level": "full",
        "parts": ["vishay-pr03-cu"],
        "prompt": (
            "Bleeder resistor across a 400 V DC bus. I want it to discharge the "
            "bus and I can afford about 4 W steady. The cabinet ambient is 60 C. "
            "Vishay PR03 (Cu lead) is rated 3 W at 70 C with 60 K/W thermal "
            "resistance and 750 V maximum working voltage, hot spot limit 250 C. "
            "Size the resistance and tell me whether one PR03 does it."
        ),
    },
    {
        "id": "P05",
        "family": "size_under_load",
        "information_level": "partial",
        "parts": ["vishay-wsr5"],
        "prompt": (
            "I'm using a Vishay WSR5 shunt (0.005 ohm, 5 W at 70 C) to measure "
            "current in a motor drive. Peak is 60 A for a few seconds, average "
            "is 15 A. Is the WSR5 adequate, and what shunt voltage do I get?"
        ),
    },

    # ---- choose a package ------------------------------------------------
    {
        "id": "P06",
        "family": "choose_a_package",
        "information_level": "full",
        "parts": ["ti-opa2333-drb-vson-8", "ti-opa333-dbv-sot23-5",
                  "ti-lm339-d-soic-14"],
        "prompt": (
            "A part dissipates 5 W continuously. Ambient is 40 C, still air, no "
            "heatsink. I've got three candidate packages with junction-to-ambient "
            "thermal resistances of 46.7, 111.2 and 220.8 C/W from their "
            "datasheets. Junction limit is 125 C. Which package can I use?"
        ),
    },
    {
        "id": "P07",
        "family": "choose_a_package",
        "information_level": "partial",
        "parts": ["ti-lmr51430-ddc-sot23-6", "ti-lmr43610-rpe-vqfn-hr-9"],
        "prompt": (
            "Choosing between a SOT-23-6 buck (TI LMR51430, RtJA 107.8 C/W) and "
            "a 9-pin VQFN-HR one (LMR43610, RtJA 84.4 C/W) for a 3 A design "
            "losing about 0.9 W. Which one keeps the junction cooler, and by "
            "roughly how much?"
        ),
    },
    {
        "id": "P08",
        "family": "choose_a_package",
        "information_level": "sparse",
        "parts": ["ti-tps54360-dda-hsoic-8"],
        "prompt": (
            "Is an HSOIC-8 with a thermal pad good enough for 2 W?"
        ),
    },
    {
        "id": "P09",
        "family": "choose_a_package",
        "information_level": "partial",
        "parts": ["nexperia-bss138p-sot23", "diodes-dmn2041l"],
        "prompt": (
            "Low-side switch, about 0.4 W of conduction loss, in a 70 C cabinet. "
            "SOT23 MOSFET datasheets quote 310 C/W junction to ambient on a bare "
            "footprint and 260 C/W with a 1 cm2 drain pad. Is SOT23 workable, or "
            "do I need to go bigger? Assume 150 C max junction."
        ),
    },

    # ---- pick a part or material for a temperature ------------------------
    {
        "id": "P10",
        "family": "pick_for_a_temperature",
        "information_level": "full",
        "parts": ["yageo-rc0201", "yageo-rc0402", "vishay-crcw0402"],
        "prompt": (
            "Downhole tool, ambient reaches 140 C. I need a 1 kohm chip resistor "
            "there. Yageo RC0201 is rated -55 to +125 C; RC0402 and Vishay "
            "CRCW0402 are rated -55 to +155 C. Dissipation is only about 5 mW. "
            "Which part, and is there anything else I should watch at that "
            "temperature?"
        ),
    },
    {
        "id": "P11",
        "family": "pick_for_a_temperature",
        "information_level": "partial",
        "parts": ["vishay-mrs25", "vishay-sfr25"],
        "prompt": (
            "I need a reference divider that holds its value over -40 C to "
            "+85 C. Vishay MRS25 is +/-50 ppm/K, SFR25 is +/-100 ppm/K over most "
            "of its range. How much drift do I get from each across that span, "
            "and which should I use?"
        ),
    },
    {
        "id": "P12",
        "family": "pick_for_a_temperature",
        "information_level": "sparse",
        "parts": ["vishay-wsr5"],
        "prompt": (
            "Which resistor family survives 250 C ambient?"
        ),
    },
    {
        "id": "P13",
        "family": "pick_for_a_temperature",
        "information_level": "full",
        "parts": ["bourns-pwr220t-20"],
        "prompt": (
            "Bourns PWR220T-20, TO-220 thick film on alumina, 20 W at 25 C case, "
            "6.5 C/W junction to case, -55 to +155 C. I want to run it at 8 W on "
            "a heatsink in a 50 C enclosure. What heatsink thermal resistance do "
            "I need, and what is the case running at?"
        ),
    },

    # ---- estimate a temperature rise -------------------------------------
    {
        "id": "P14",
        "family": "estimate_a_rise",
        "information_level": "full",
        "parts": ["vishay-sfr25h"],
        "prompt": (
            "Vishay SFR25H, 150 K/W, dissipating 0.3 W in 25 C still air. What "
            "does the body settle at, and how long does it take to get there? "
            "The part is about 0.25 g of ceramic and film."
        ),
    },
    {
        "id": "P15",
        "family": "estimate_a_rise",
        "information_level": "partial",
        "parts": ["vishay-pr01"],
        "prompt": (
            "PR01 power film resistor, 135 K/W, running 0.8 W. Ambient is 45 C. "
            "How hot does it get, and is that a problem?"
        ),
    },
    {
        "id": "P16",
        "family": "estimate_a_rise",
        "information_level": "sparse",
        "parts": ["vishay-crcw2512"],
        "prompt": (
            "How hot does a 2512 chip resistor get at 1 W?"
        ),
    },
    {
        "id": "P17",
        "family": "estimate_a_rise",
        "information_level": "partial",
        "parts": ["vishay-sfr25"],
        "prompt": (
            "A 47 ohm SFR25 sees a 20 V pulse for 30 seconds, then nothing for "
            "ten minutes, repeating. Ambient 25 C. Does it survive? The "
            "datasheet gives 0.4 W at 70 C and 200 K/W."
        ),
    },

    # ---- judge whether a stated design is safe ----------------------------
    {
        "id": "P18",
        "family": "judge_a_design",
        "information_level": "full",
        "parts": ["vishay-crcw0805"],
        "prompt": (
            "Someone on my team specified a CRCW0805 (0.25 W at 70 C, 150 V max) "
            "as a 33 ohm ballast on a 24 V supply, in a 60 C enclosure. They say "
            "it is fine because it is under the voltage rating. Is the design "
            "sound? Give me a yes or no and the numbers behind it."
        ),
    },
    {
        "id": "P19",
        "family": "judge_a_design",
        "information_level": "partial",
        "parts": ["vishay-rcv2512"],
        "prompt": (
            "Design review: 1 Mohm RCV2512 high-voltage chip resistor used as the "
            "top leg of a divider on a 2500 V bus. Rated 1 W at 70 C and 3000 V. "
            "Anything wrong with this?"
        ),
    },
    {
        "id": "P20",
        "family": "judge_a_design",
        "information_level": "sparse",
        "parts": ["vishay-crcw1206", "yageo-rc1206"],
        "prompt": (
            "Two 1206 resistors in parallel to share 0.4 W. Fine?"
        ),
    },
)


def check_parts_exist(components: dict) -> list[str]:
    """Every part a prompt names must be in components.json. Returns problems."""
    known = {c["id"] for c in components["resistors"]}
    known |= {p["id"] for p in components["packages"]}
    problems = []
    for seed in SEEDS:
        for pid in seed["parts"]:
            if pid not in known:
                problems.append(f"{seed['id']} names unknown part {pid!r}")
    return problems


#: Words a prompt must not contain. Rule 1, enforced rather than intended.
FORBIDDEN = (
    "biot", "fourier", "lumped", "applicability", "validity", "excursion",
    "linearis", "lineariz", "emissivity", "debye", "rayleigh", "reynolds",
    "prandtl", "nusselt", "engcore", "verdict", "benchmark", "evaluate",
    "test case", "derating curve",
)


def check_vocabulary() -> list[str]:
    problems = []
    for seed in SEEDS:
        low = seed["prompt"].lower()
        for word in FORBIDDEN:
            if word in low:
                problems.append(f"{seed['id']} contains forbidden word {word!r}")
    return problems


def build() -> dict:
    counts: dict[str, int] = {}
    for seed in SEEDS:
        counts[seed["family"]] = counts.get(seed["family"], 0) + 1
        counts[seed["information_level"]] = counts.get(
            seed["information_level"], 0
        ) + 1
    return {
        "schema_version": "1.0",
        "count": len(SEEDS),
        "families": list(FAMILIES),
        "composition": counts,
        "rules": [
            "No vocabulary from the tool under test.",
            "No planted contradiction; stated numbers come from a real datasheet.",
            "Under-specification is realistic, not a trap.",
            "No forced choice between two bad options.",
            "Ordinary difficulty.",
        ],
        "prompts": [dict(s) for s in SEEDS],
    }


def to_markdown(doc: dict) -> str:
    lines = [
        "# Design prompts",
        "",
        f"{doc['count']} prompts. Give one to a model, capture what comes back "
        "in the shape `design_schema.json` describes, and label it with "
        "`label_template.md`. Nothing here calls an API.",
        "",
        "Composition: "
        + ", ".join(f"{k} {v}" for k, v in sorted(doc["composition"].items())),
        "",
        "Rules these were written against:",
        "",
    ]
    lines += [f"{i}. {r}" for i, r in enumerate(doc["rules"], 1)]
    lines += ["", "---", ""]
    for p in doc["prompts"]:
        lines += [
            f"## {p['id']} — {p['family']} ({p['information_level']})",
            "",
            f"> {p['prompt']}",
            "",
            f"*Built around:* {', '.join(p['parts'])}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--components", default=str(HERE / "components.json"))
    ap.add_argument("--out", default=str(HERE / "prompts.json"))
    ap.add_argument("--md", default=str(HERE / "prompts.md"))
    args = ap.parse_args()

    components = json.loads(
        pathlib.Path(args.components).read_text(encoding="utf-8")
    )
    problems = check_parts_exist(components) + check_vocabulary()
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return 1

    doc = build()
    pathlib.Path(args.out).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pathlib.Path(args.md).write_text(to_markdown(doc) + "\n", encoding="utf-8")
    print(f"wrote {args.out} and {args.md}: {doc['count']} prompts, "
          f"{len(FAMILIES)} families, no forbidden vocabulary, "
          f"every named part present in components.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
