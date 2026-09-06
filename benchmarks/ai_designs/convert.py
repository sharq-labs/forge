"""A stated design becomes an engcore payload — and every gap it had is written down.

Why this file is the most dangerous part of the benchmark
---------------------------------------------------------
A design is prose with numbers in it. A payload is a complete declaration. The
distance between the two is filled by this module, and **whatever fills it is a
claim nobody made.** If the filling is silent, the benchmark stops measuring the
design and starts measuring the converter, without saying so.

Three things keep that visible:

1. **Every supplied value is logged**, with its class and its justification, in
   ``conversion_notes``. Nothing enters a payload unrecorded.
2. **A design that cannot be posed without inventing a required value is its own
   outcome**, ``unconvertible``, and is counted separately rather than pushed
   through on a guess.
3. **Three policies**, run separately, so the effect of the filling is a measured
   difference rather than an assumption:

   * ``stated_only`` — only what the design said. Nothing is looked up and
     nothing is invented.
   * ``datasheet_completed`` — plus what the named part's datasheet gives:
     ratings, temperature coefficient, category temperature, published thermal
     resistance. The design named the part, so the datasheet is the design's own
     referent, not an outside contribution.
   * ``fully_declared`` — plus a fixed, documented set of invented declarations
     for the body and the surrounding fluid. This is the only policy under which
     a report can reach SUPPORTED at all, and it is the one whose numbers have
     the same shape as the frozen benchmark's.

Value classes
-------------
``stated``      the design said it.
``arithmetic``  it follows from what the design said, by one identity that is
                named in the note (P = V^2/R, C = m c_p, hA = 1/R_th).
``datasheet``   ``components.json`` has it, with a document reference, for the
                part the design named.
``literature``  a published property with a citation, not specific to the part.
``invented``    nobody said it. Only ``fully_declared`` admits these, and each
                one is listed in ``INVENTED_FIELDS`` with what it feeds.

The prohibited use, made loud
------------------------------
``thermal_resistance_kind == "junction_to_ambient"`` means the number is a JEDEC
theta-JA. Turning it into an ``ambient_conductance`` is exactly the use JESD51-3
rules out. The conversion does it, because the design did, and logs it as
``JEDEC_THETA_JA_USED_AS_A_CONDUCTANCE`` so that no result can be read without
seeing it.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field

HERE = pathlib.Path(__file__).resolve().parent

KELVIN_OFFSET = 273.15

#: The payload field names for the two ends of a derating line. Spelled out
#: here rather than imported from engcore: this file builds a payload and must
#: not depend on the package it is a payload for.
dc_models_rated_power_temperature = "rated_power_temperature"
dc_models_zero_power_temperature = "zero_power_temperature"

POLICIES = ("stated_only", "datasheet_completed", "fully_declared")

#: Payload fields without which no problem can be posed at all. Absent any of
#: these, the design is `unconvertible` rather than forced through.
REQUIRED = (
    "source_voltage", "reference_resistance", "temperature_coefficient",
    "reference_temperature", "heat_capacity", "ambient_conductance",
    "ambient_temperature", "initial_temperature", "duration",
)

#: Optional declarations that only `fully_declared` will invent, and the
#: validity conditions each one feeds. Used by :func:`verdict_rests_on_invention`
#: to say whether a refusal was decided by something nobody declared.
INVENTED_FIELDS: dict[str, tuple[str, ...]] = {
    "characteristic_length": ("biot_number", "internal_fourier_number",
                              "geometry_route_ratio"),
    "body_volume": ("geometry_route_ratio",),
    "surface_area": ("biot_number", "internal_fourier_number",
                     "radiation_to_convection_ratio", "geometry_route_ratio",
                     "convection_conductance_agreement_ratio"),
    "body_conductivity": ("biot_number", "internal_fourier_number"),
    "surface_emissivity": ("radiation_to_convection_ratio",),
    "melting_temperature": ("melting_temperature_utilization",),
    "conductance_excursion_bound": ("conductance_excursion_ratio",),
    "capacity_excursion_bound": ("capacity_excursion_ratio",),
    "linearization_band": ("linearization_excursion_ratio",),
    "debye_temperature": ("reduced_debye_temperature",),
    "fluid_conductivity": ("convection_conductance_agreement_ratio",),
    "fluid_kinematic_viscosity": ("convection_flow_range_utilization",
                                  "convection_conductance_agreement_ratio"),
    "fluid_prandtl_number": ("convection_property_range_utilization",
                             "convection_flow_range_utilization",
                             "convection_conductance_agreement_ratio"),
    "fluid_expansion_coefficient": ("convection_flow_range_utilization",),
    "fluid_velocity": ("convection_flow_range_utilization",),
    "convection_length": ("convection_flow_range_utilization",
                          "convection_conductance_agreement_ratio"),
}

#: Air near 300 K. Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat
#: and Mass Transfer*, 6th ed. (Wiley, 2007), Table A.4. Cited, so `literature`
#: rather than `invented` -- but still a value the design did not state, and
#: still logged.
AIR = {
    "fluid_kinematic_viscosity": 1.589e-5,
    "fluid_prandtl_number": 0.707,
}


@dataclass
class Conversion:
    """One design, converted or refused, with the reasons either way."""

    design_id: str
    policy: str
    payload: dict | None = None
    notes: list[dict] = field(default_factory=list)
    unconvertible_because: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.payload is not None

    def note(self, field_name: str, value, kind: str, why: str) -> None:
        self.notes.append(
            {"field": field_name, "value": value, "class": kind, "why": why}
        )

    def classes_used(self) -> set[str]:
        return {n["class"] for n in self.notes}

    def invented_fields(self) -> set[str]:
        return {n["field"] for n in self.notes if n["class"] == "invented"}


def load_components(path: str | pathlib.Path | None = None) -> dict:
    p = pathlib.Path(path) if path else HERE / "components.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {
        "resistors": {r["id"]: r for r in doc["resistors"]},
        "packages": {q["id"]: q for q in doc["packages"]},
    }


def _tcr_for(part: dict, resistance: float) -> tuple[float, str] | None:
    """The datasheet's TCR band that contains this resistance, in 1/K.

    Real parts band their coefficient by value, and picking the family headline
    where a band applies would be substituting a number. A resistance outside
    every band returns None rather than the nearest one.
    """
    for band in part.get("temperature_coefficient_ppm_per_k", []):
        if band.get("value") is None:
            continue
        if band["from_ohm"] <= resistance <= band["to_ohm"]:
            return (
                band["value"] * 1e-6,
                f"{part['part_number']} datasheet TCR band "
                f"{band['from_ohm']}-{band['to_ohm']} ohm = "
                f"{band['value']} ppm/K ({part['source']['document_number']})",
            )
    return None


def geometry_from_datasheet(part: dict | None) -> dict | None:
    """L_c, surface area and volume from the outline the datasheet prints.

    22 of the 35 resistors in ``components.json`` publish an outline. For a
    rectangular chip the six faces give the area and L x W x H the volume; for a
    cylindrical leaded body the barrel plus two ends. The characteristic length
    is then V/A_s, which is the definition the lumped model uses when none is
    declared -- so the two routes agree by construction, and they agree on a
    number that came from a document.

    Returns None where the datasheet prints no outline, and the caller must
    then invent one or refuse.
    """
    dims = (part or {}).get("dimensions_mm")
    if not dims:
        return None
    if dims.get("shape") == "cylinder":
        r = dims["body_diameter"] / 2000.0
        length = dims["body_length"] / 1000.0
        area = 2.0 * math.pi * r * length + 2.0 * math.pi * r * r
        volume = math.pi * r * r * length
        basis = (f"cylinder, diameter {dims['body_diameter']} mm and length "
                 f"{dims['body_length']} mm from the datasheet outline")
    else:
        L = dims["length"] / 1000.0
        W = dims["width"] / 1000.0
        H = dims["height"] / 1000.0
        area = 2.0 * (L * W + L * H + W * H)
        volume = L * W * H
        basis = (f"rectangular chip {dims['length']} x {dims['width']} x "
                 f"{dims['height']} mm from the datasheet outline")
    return {"characteristic_length": volume / area, "surface_area": area,
            "body_volume": volume, "basis": basis}


#: Fallback outlines for the 13 parts whose datasheets print none in extractable
#: form. Every number is invented and is logged as such.
_INVENTED_OUTLINE_MM = {
    "DIN 0204": (3.5, 1.8, 1.8),
    "DIN 0207": (6.5, 2.5, 2.5),
    "DIN 0411": (9.0, 3.5, 3.5),
    "DIN 0617": (15.0, 5.5, 5.5),
    "4527": (11.6, 6.9, 2.5),
    "TO-220": (10.0, 9.0, 4.5),
}


def _geometry_for(part: dict | None) -> tuple[dict, str]:
    """(geometry, value class). Datasheet outline where there is one."""
    from_sheet = geometry_from_datasheet(part)
    if from_sheet is not None:
        return from_sheet, "datasheet"
    pkg = (part or {}).get("package", "") or ""
    dims = None
    for key, value in _INVENTED_OUTLINE_MM.items():
        if key in pkg:
            dims = value
            break
    if dims is None:
        dims = (3.2, 1.6, 0.55)
    L, W, H = (x / 1000.0 for x in dims)
    area = 2.0 * (L * W + L * H + W * H)
    volume = L * W * H
    return (
        {"characteristic_length": volume / area, "surface_area": area,
         "body_volume": volume,
         "basis": f"invented outline {dims[0]} x {dims[1]} x {dims[2]} mm; this "
                  f"datasheet prints no extractable package dimensions"},
        "invented",
    )


def _q(x: float, unit: str) -> str:
    return f"{x:.10g} {unit}"


def convert(design: dict, components: dict, policy: str) -> Conversion:
    """Build a payload from a stated design under one policy."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    c = Conversion(design_id=design["id"], policy=policy)
    stated = design["stated_design"]
    ctx = stated.get("declared_thermal_context", {})
    limits = stated.get("declared_limits", {})
    part = components["resistors"].get(stated.get("part_id"))
    package = components["packages"].get(stated.get("package_id"))
    allow_datasheet = policy in ("datasheet_completed", "fully_declared")
    allow_invented = policy == "fully_declared"

    got: dict[str, float] = {}

    # ---- the circuit -----------------------------------------------------
    if "source_voltage_v" in stated:
        got["source_voltage"] = stated["source_voltage_v"]
        c.note("source_voltage", got["source_voltage"], "stated", "design states it")
    if "resistance_ohm" in stated:
        got["reference_resistance"] = stated["resistance_ohm"]
        c.note("reference_resistance", got["reference_resistance"], "stated",
               "design states it")

    if "reference_temperature_c" in stated:
        got["reference_temperature"] = stated["reference_temperature_c"] + KELVIN_OFFSET
        c.note("reference_temperature", got["reference_temperature"], "stated",
               "design states the temperature its resistance is quoted at")
    elif allow_invented:
        got["reference_temperature"] = 20.0 + KELVIN_OFFSET
        c.note("reference_temperature", got["reference_temperature"], "invented",
               "design did not say what temperature its resistance is quoted "
               "at; 20 C assumed, which is the usual datasheet reference and "
               "is nonetheless a value nobody stated")

    if "temperature_coefficient_ppm_per_k" in stated:
        got["temperature_coefficient"] = (
            stated["temperature_coefficient_ppm_per_k"] * 1e-6
        )
        c.note("temperature_coefficient", got["temperature_coefficient"], "stated",
               "design states it")
    elif allow_datasheet and part is not None and "reference_resistance" in got:
        band = _tcr_for(part, got["reference_resistance"])
        if band is not None:
            got["temperature_coefficient"], why = band
            c.note("temperature_coefficient", got["temperature_coefficient"],
                   "datasheet", why)

    # ---- the thermal path ------------------------------------------------
    if "ambient_c" in stated:
        got["ambient_temperature"] = stated["ambient_c"] + KELVIN_OFFSET
        c.note("ambient_temperature", got["ambient_temperature"], "stated",
               "design states it")

    if "initial_temperature_c" in stated:
        got["initial_temperature"] = stated["initial_temperature_c"] + KELVIN_OFFSET
        c.note("initial_temperature", got["initial_temperature"], "stated",
               "design states it")
    elif "ambient_temperature" in got:
        got["initial_temperature"] = got["ambient_temperature"]
        c.note("initial_temperature", got["initial_temperature"], "arithmetic",
               "design did not state a starting temperature; a body switched on "
               "from rest starts at its ambient, which the design did state")

    rth = stated.get("thermal_resistance_k_per_w")
    kind = stated.get("thermal_resistance_kind", "unstated")
    if rth is None and allow_datasheet and part is not None:
        rth = part.get("thermal_resistance_k_per_w")
        if rth is not None:
            kind = "body_to_ambient"
            c.note("thermal_resistance_source", rth, "datasheet",
                   f"{part['part_number']} datasheet R_th = {rth} K/W "
                   f"({part['source']['document_number']})")
    if rth is None and allow_datasheet and package is not None:
        rth = package.get("theta_ja_c_per_w")
        kind = "junction_to_ambient"
        c.note("thermal_resistance_source", rth, "datasheet",
               f"{package['part_number']} {package['package']} theta-JA = "
               f"{rth} C/W")
    if rth is not None and rth > 0:
        got["ambient_conductance"] = 1.0 / rth
        c.note("ambient_conductance", got["ambient_conductance"], "arithmetic",
               f"hA = 1/R_th with R_th = {rth} K/W")
        if kind == "junction_to_ambient":
            c.note("JEDEC_THETA_JA_USED_AS_A_CONDUCTANCE", rth, "invented",
                   "the stated thermal resistance is a JEDEC junction-to-ambient "
                   "value; JESD51-3 states such values compare packages and do "
                   "not predict application performance, so treating it as this "
                   "body's conductance to ambient is the use the standard rules "
                   "out. The design did it and the conversion follows the design.")
        elif kind == "junction_to_case":
            c.note("JUNCTION_TO_CASE_USED_AS_JUNCTION_TO_AMBIENT", rth, "invented",
                   "the stated thermal resistance stops at the case; using it as "
                   "the whole path to ambient omits the case-to-ambient leg the "
                   "design did not state")

    if "heat_capacity_j_per_k" in stated:
        got["heat_capacity"] = stated["heat_capacity_j_per_k"]
        c.note("heat_capacity", got["heat_capacity"], "stated", "design states it")
    elif "mass_g" in stated and "specific_heat_j_per_kg_k" in stated:
        got["heat_capacity"] = (
            stated["mass_g"] * 1e-3 * stated["specific_heat_j_per_kg_k"]
        )
        c.note("heat_capacity", got["heat_capacity"], "arithmetic",
               "C = m c_p from the mass and specific heat the design states")
    elif "mass_g" in stated and allow_invented:
        got["heat_capacity"] = stated["mass_g"] * 1e-3 * 850.0
        c.note("heat_capacity", got["heat_capacity"], "invented",
               "design gave a mass but no specific heat; 850 J/(kg K) assumed "
               "for an alumina-bodied part, which is a value nobody stated")
    elif allow_datasheet and part is not None and part.get("mass_mg") and allow_invented:
        got["heat_capacity"] = part["mass_mg"] * 1e-6 * 850.0
        c.note("heat_capacity", got["heat_capacity"], "invented",
               f"C = m c_p from the datasheet mass ({part['mass_mg']} mg, "
               f"{part['source']['document_number']}) and an INVENTED specific "
               f"heat of 850 J/(kg K) for alumina. The mass is documented; the "
               f"specific heat is not, and it scales the answer linearly.")
    elif allow_invented:
        geo, geo_class = _geometry_for(part)
        got["heat_capacity"] = geo["body_volume"] * 3800.0 * 850.0
        c.note("heat_capacity", got["heat_capacity"], "invented",
               f"design stated neither a heat capacity nor a mass; C = rho V c_p "
               f"with volume from a {geo_class} outline ({geo['basis']}), an "
               f"invented rho = 3800 kg/m3 and an invented c_p = 850 J/(kg K).")

    if "duration_s" in stated:
        got["duration"] = stated["duration_s"]
        c.note("duration", got["duration"], "stated", "design states it")
    elif allow_invented and "heat_capacity" in got and "ambient_conductance" in got:
        tau = got["heat_capacity"] / got["ambient_conductance"]
        got["duration"] = 8.0 * tau
        c.note("duration", got["duration"], "invented",
               "design said nothing about how long the load lasts; eight time "
               "constants assumed so the body reaches its steady state. A design "
               "meant as a short pulse would be judged as if it ran to "
               "equilibrium, which is a different design.")

    missing = [k for k in REQUIRED if k not in got]
    if missing:
        c.unconvertible_because = [
            f"{k} could not be obtained under policy {policy!r} without "
            f"inventing it" for k in missing
        ]
        return c

    # ---- the optional declarations ---------------------------------------
    applicability: dict[str, str] = {}
    conductor_limits: dict[str, str] = {}
    ratings: dict[str, object] = {}
    source_ratings: dict[str, object] = {}

    def put(target: dict, key: str, value: float, unit: str, kind_: str,
            why: str) -> None:
        target[key] = _q(value, unit)
        c.note(key, value, kind_, why)

    # limits the design itself declared
    if "maximum_operating_temperature_c" in limits:
        put(conductor_limits, "maximum_operating_temperature",
            limits["maximum_operating_temperature_c"] + KELVIN_OFFSET, "kelvin",
            "stated", "design states a maximum operating temperature")
    elif allow_datasheet and part is not None and part.get(
            "operating_temperature_range_c"):
        put(conductor_limits, "maximum_operating_temperature",
            part["operating_temperature_range_c"][1] + KELVIN_OFFSET, "kelvin",
            "datasheet",
            f"{part['part_number']} category temperature upper limit "
            f"({part['source']['document_number']})")

    if "rated_power_w" in limits:
        put(ratings, "rated_power", limits["rated_power_w"], "watt", "stated",
            "design states a rated power")
    elif allow_datasheet and part is not None and part.get("rated_power_w"):
        put(ratings, "rated_power", part["rated_power_w"], "watt", "datasheet",
            f"{part['part_number']} rated dissipation "
            f"{part['rated_power_w']} W at {part['rated_power_ambient_c']} C "
            f"({part['source']['document_number']}). Declared here WITHOUT the "
            f"ambient it is rated at, because the payload's rating field carries "
            f"no ambient; a part run above that ambient has a lower real rating "
            f"and this conversion cannot say so.")

    # The other half of the rating. A rated dissipation is a pair, and since the
    # domain grew fields for the pair this is where the datasheet's derating
    # knee reaches the payload. Only parts whose datasheet prints a knee are
    # eligible: `components.json` leaves `derating` null for the eleven Yageo
    # sizes, which draw the curve as an image and print no temperature, so a
    # Yageo case is still checked against the flat rating. That is not a gap in
    # the conversion -- it is the honest consequence of a number the source does
    # not publish, and it makes the two families behave differently in the
    # results for a reason a reader can check.
    derating_curve = (part or {}).get("derating") or {}
    knee = limits.get("rated_power_temperature_c", derating_curve.get("knee_c"))
    zero = limits.get(
        "zero_power_temperature_c",
        derating_curve.get("zero_power_c")
        or (part or {}).get("permissible_film_temperature_c"),
    )
    stated_pair = ("rated_power_temperature_c" in limits
                   or "zero_power_temperature_c" in limits)
    if (knee is not None and zero is not None and "rated_power" in ratings
            and (stated_pair or allow_datasheet)):
        graph = derating_curve.get("read_from_graph") and not stated_pair
        why = (
            "design states the rating temperature" if stated_pair else
            f"{part['part_number']} rated dissipation is stated at "
            f"{knee} C and derates to zero at {zero} C "
            f"({part['source']['document_number']})"
            + ("; the knee was read from the derating curve's axis labels "
               "rather than from a table, and is flagged as such in "
               "components.json" if graph else "")
        )
        put(ratings, dc_models_rated_power_temperature, knee + KELVIN_OFFSET,
            "kelvin", "stated" if stated_pair else "datasheet", why)
        put(ratings, dc_models_zero_power_temperature, zero + KELVIN_OFFSET,
            "kelvin", "stated" if stated_pair else "datasheet", why)

    if "maximum_working_voltage_v" in limits:
        put(ratings, "maximum_working_voltage", limits["maximum_working_voltage_v"],
            "volt", "stated", "design states a maximum working voltage")
    elif allow_datasheet and part is not None and part.get(
            "maximum_working_voltage_v"):
        put(ratings, "maximum_working_voltage", part["maximum_working_voltage_v"],
            "volt", "datasheet",
            f"{part['part_number']} operating voltage limit "
            f"({part['source']['document_number']})")

    if "derating_factor" in limits:
        ratings["derating_factor"] = limits["derating_factor"]
        c.note("derating_factor", limits["derating_factor"], "stated",
               "design states a derating factor")

    # The supply's own current rating. Stated or absent -- NEVER invented, even
    # under `fully_declared`. Every other invented value here is a property of a
    # physical body that some datasheet could in principle publish; a supply's
    # current limit is a property of a rail the design chose, and a made-up one
    # would decide `source_current_utilization` on nothing at all. A design that
    # does not state it leaves that condition UNKNOWN, which is the honest
    # answer and is why several otherwise complete cases cannot reach SUPPORTED.
    if "source_maximum_current_a" in limits:
        put(source_ratings, "maximum_current", limits["source_maximum_current_a"],
            "ampere", "stated", "design states the supply's current limit")
    if "source_derating_factor" in limits:
        source_ratings["derating_factor"] = limits["source_derating_factor"]
        c.note("source_derating_factor", limits["source_derating_factor"],
               "stated", "design states a derating factor for the supply")

    # the body and the fluid
    def ctx_or_invent(key: str, ctx_key: str, unit: str, invented,
                      why_invented: str, target=applicability) -> None:
        if ctx_key in ctx:
            put(target, key, ctx[ctx_key], unit, "stated",
                "design declares it")
        elif allow_invented and invented is not None:
            put(target, key, invented, unit, "invented", why_invented)

    geo, geo_class = _geometry_for(part)
    for key, ctx_key, unit in (
        ("characteristic_length", "characteristic_length_m", "meter"),
        ("surface_area", "surface_area_m2", "meter**2"),
        ("body_volume", "body_volume_m3", "meter**3"),
    ):
        if ctx_key in ctx:
            put(applicability, key, ctx[ctx_key], unit, "stated",
                "design declares it")
        elif geo_class == "datasheet" and allow_datasheet:
            put(applicability, key, geo[key], unit, "datasheet",
                f"{key} from the datasheet outline: {geo['basis']}. The bodies "
                f"here are solid, so V/A_s is the length the model asks for.")
        elif allow_invented:
            put(applicability, key, geo[key], unit, "invented", geo["basis"])
    ctx_or_invent("body_conductivity", "body_conductivity_w_per_m_k",
                  "watt/meter/kelvin", 30.0,
                  "no datasheet publishes the body's bulk conductivity; 30 "
                  "W/(m K) assumed for alumina")
    ctx_or_invent("surface_emissivity", "surface_emissivity", "dimensionless",
                  0.85,
                  "no datasheet publishes an emissivity; 0.85 assumed for a "
                  "lacquered or moulded surface")
    if "melting_temperature_c" in ctx:
        put(applicability, "melting_temperature",
            ctx["melting_temperature_c"] + KELVIN_OFFSET, "kelvin", "stated",
            "design declares it")
    elif allow_invented:
        put(applicability, "melting_temperature", 2345.0, "kelvin", "invented",
            "no datasheet publishes a phase-change temperature; 2345 K assumed "
            "for alumina")

    if "constant_conductance_span_k" in ctx:
        put(applicability, "conductance_excursion_bound",
            ctx["constant_conductance_span_k"], "kelvin", "stated",
            "design declares the span it holds hA constant over")
    elif allow_invented:
        put(applicability, "conductance_excursion_bound", 60.0, "kelvin",
            "invented",
            "the design never said over what span it believes its thermal "
            "resistance constant; 60 K assumed. This is the assumption most "
            "likely to decide a verdict and least likely to have been made "
            "consciously by the designer.")

    if "constant_capacity_span_k" in ctx:
        put(applicability, "capacity_excursion_bound",
            ctx["constant_capacity_span_k"], "kelvin", "stated",
            "design declares the span it holds C constant over")
    elif allow_invented:
        put(applicability, "capacity_excursion_bound", 150.0, "kelvin", "invented",
            "no design states the span over which it treats the heat capacity "
            "as constant; 150 K assumed")

    if "linearization_band_k" in ctx:
        put(conductor_limits, "linearization_band", ctx["linearization_band_k"],
            "kelvin", "stated", "design declares it")
    elif allow_invented:
        put(conductor_limits, "linearization_band", 200.0, "kelvin", "invented",
            "no datasheet states the span over which its temperature "
            "coefficient is linear; 200 K assumed, which is wider than most "
            "film resistors are characterised over")

    if "debye_temperature_k" in ctx:
        put(conductor_limits, "debye_temperature", ctx["debye_temperature_k"],
            "kelvin", "stated", "design declares it")
    elif allow_invented:
        put(conductor_limits, "debye_temperature", 400.0, "kelvin", "invented",
            "no resistor datasheet states a Debye temperature; 400 K assumed, "
            "which is in the range of the nickel-chromium alloys these films "
            "are made from but is not a number any source here prints")

    # the fluid. Only where the design said something about the air.
    airflow = ctx.get("airflow")
    conv_len = ctx.get("convection_length_m")
    if airflow is not None and (conv_len is not None or allow_invented):
        if conv_len is None:
            conv_len = math.sqrt(
                ctx.get("surface_area_m2", geo["surface_area"])
            )
            c.note("convection_length", conv_len, "invented",
                   "no design states the length its boundary layer develops "
                   "along; the square root of the surface area assumed")
        put(applicability, "convection_length", conv_len, "meter",
            "stated" if "convection_length_m" in ctx else "invented",
            "design declares it" if "convection_length_m" in ctx
            else "square root of the surface area")
        put(applicability, "fluid_kinematic_viscosity",
            AIR["fluid_kinematic_viscosity"], "meter**2/second", "literature",
            "dry air near 300 K, Incropera et al. 6th ed. Table A.4")
        put(applicability, "fluid_prandtl_number", AIR["fluid_prandtl_number"],
            "dimensionless", "literature",
            "dry air near 300 K, Incropera et al. 6th ed. Table A.4")
        if "fluid_conductivity_solved_w_per_m_k" in ctx:
            put(applicability, "fluid_conductivity",
                ctx["fluid_conductivity_solved_w_per_m_k"],
                "watt/meter/kelvin", "stated",
                "design declares the fluid conductivity its coefficient rests on")
        if airflow == "forced" and "fluid_velocity_m_per_s" in ctx:
            put(applicability, "fluid_velocity", ctx["fluid_velocity_m_per_s"],
                "meter/second", "stated", "design declares a free-stream velocity")
        elif airflow == "still":
            beta = 1.0 / got["ambient_temperature"]
            put(applicability, "fluid_expansion_coefficient", beta, "1/kelvin",
                "arithmetic",
                "beta = 1/T for an ideal gas at the stated ambient")

    # ---- assemble --------------------------------------------------------
    conductor: dict = {
        "reference_resistance": _q(got["reference_resistance"], "ohm"),
        "temperature_coefficient": _q(got["temperature_coefficient"], "1/kelvin"),
        "reference_temperature": _q(got["reference_temperature"], "kelvin"),
    }
    if conductor_limits:
        conductor["limits"] = conductor_limits
    if ratings:
        conductor["ratings"] = ratings

    body: dict = {
        "heat_capacity": _q(got["heat_capacity"], "joule/kelvin"),
        "ambient_conductance": _q(got["ambient_conductance"], "watt/kelvin"),
        "ambient_temperature": _q(got["ambient_temperature"], "kelvin"),
        "initial_temperature": _q(got["initial_temperature"], "kelvin"),
        "duration": _q(got["duration"], "second"),
    }
    if applicability:
        body["applicability"] = applicability

    payload: dict = {
        "source_voltage": _q(got["source_voltage"], "volt"),
        "stages": [{"component_id": "R1", "conductor": conductor, "body": body}],
        "coupling": {
            "seed_temperature": _q(got["initial_temperature"], "kelvin"),
            "tolerance": "1e-06 kelvin",
            "max_iterations": 200,
        },
    }
    if source_ratings:
        payload["source_ratings"] = source_ratings
    c.payload = payload
    return c


def verdict_rests_on_invention(conversion: Conversion,
                               violated_conditions: list[str]) -> list[str]:
    """Which violated conditions were fed by a value nobody declared.

    A refusal decided by an invented number is a refusal of the conversion, not
    of the design. This is a static dependency check over ``INVENTED_FIELDS``:
    cheap, and it answers the question the numbers otherwise hide.
    """
    invented = conversion.invented_fields()
    fed: set[str] = set()
    for f in invented:
        fed |= set(INVENTED_FIELDS.get(f, ()))
    return sorted(set(violated_conditions) & fed)
