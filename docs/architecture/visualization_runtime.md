# Global 3D Engineering Visualization Runtime

> **Status:** strategic architecture direction; NOT IMPLEMENTED.
>
> **Purpose:** define one global interactive 3D surface for complete Forge
> products, assemblies, motion and scientific results without giving the
> renderer scientific authority.
>
> **Execution boundary:** this does not start feature implementation during
> BIG 14/15.

## 1. Goal

Forge should eventually let an engineer open a complete vehicle, drone,
machine, motor or robotic system and move continuously between:

```text
whole product
 -> subsystem
 -> assembly
 -> component
 -> part
 -> internal section / cutaway
 -> motion state
 -> scientific result overlay
 -> limit / margin / evidence
```

The viewer should make complex engineering understandable without replacing the
underlying CAD, solver, product graph or evidence records.

## 2. Canonical architecture

The viewer must not own the authoritative product state.

```text
Engineering Product / Assembly Graph
          + Parametric CAD
          + Simulation / Telemetry Results
          + Evidence / Limits
                    ↓
             Forge Scene IR
                    ↓
          VisualizationProvider
                    ↓
       Three.js (first web provider)
                    ↓
       Interactive Engineering Viewer
```

Three.js is the preferred initial web renderer because it can provide portable
interactive 3D, animation, picking, clipping, materials, labels and custom
shader/overlay work. It is not a Scientific Core dependency and must remain
replaceable behind a provider boundary.

## 3. Scene IR

A canonical scene representation should reference, rather than duplicate,
authoritative engineering identities.

A scene node may bind:

- product/system/subsystem/assembly/part identity;
- geometry asset identity and level of detail;
- transform/reference frame;
- parent/child assembly relation;
- visibility/selectability;
- material appearance for presentation;
- authoritative dimension/annotation references;
- motion-channel references;
- result-field/telemetry references;
- threshold/limit references;
- provenance needed to explain what is being displayed.

The Scene IR is a projection for visualization. It does not become the source
of truth for dimensions, materials, simulation outputs or evidence.

## 4. Whole-product and large-assembly viewing

Large products must be hierarchical and progressively loaded.

Example:

```text
Vehicle
├── body
├── powertrain
│   ├── engine / motor
│   └── transmission
├── front suspension
├── rear suspension
├── cooling
├── electrical / harness
└── controls / sensors
```

The initial scene may use low-detail geometry. Detailed subsystem geometry,
fasteners, wiring and analysis meshes should load only when requested or when
the current view/fidelity needs them.

Required behaviours include:

- hierarchical assembly tree;
- isolate/hide/show;
- subsystem focus;
- level-of-detail selection;
- geometry chunk streaming;
- instancing for repeated standard parts;
- analysis-mesh overlays kept separate from presentation CAD where useful.

## 5. Engineering inspection modes

The viewer should support at least:

### Normal
Standard shaded product/assembly view.

### Transparent / X-ray
Make selected housings/covers transparent so internal components remain visible.

### Section / cutaway
Clip one or more planes or use CAD-derived section data to expose internal
construction.

### Exploded
Displace components along declared assembly relations while preserving identity.

### Dimension / annotation
Display exact authoritative dimensions, tolerances, fits, threads, clearances
and engineering metadata from the design records.

### Motion
Play kinematic, multibody, flight, vehicle or mechanism state over time.

### Scientific overlay
Display admitted fields/telemetry such as temperature, stress, displacement,
velocity, pressure, flow, current, voltage, power loss, vibration or lifecycle
state.

### Limits / risk
Display engineering margins and warnings only when an authoritative limit and
applicable computed/measured state exist.

## 6. Motor example

A motor should eventually be inspectable as:

```text
Motor
├── housing
├── stator
│   └── windings
├── rotor
├── shaft
├── bearings
├── cooling interfaces
└── electrical connectors
```

Possible synchronized views include:

- housing transparent while rotor motion plays;
- cutaway of stator/rotor/shaft;
- RPM and torque playback;
- current/voltage/back-EMF/loss telemetry where modeled;
- winding and housing thermal field;
- bearing speed/load/temperature state where supported;
- conductor/connector current and thermal margin;
- insulation-temperature margin;
- magnet-temperature/demagnetization margin where the selected magnetic
  material model and limits support it;
- lifecycle/wear state.

A red winding is not evidence that a motor will burn. A warning such as
"continuous winding temperature limit exceeded" requires a traceable
temperature result, a traceable applicable limit, their units/context and the
scientific/evidence status of both.

## 7. Vehicle / engine / machine examples

A vehicle view may show the complete car, then isolate powertrain, suspension,
cooling or wiring. Motion playback may show suspension travel, wheel motion or
powertrain states.

A combustion engine cutaway may animate crankshaft/piston/valve motion when
kinematic/dynamic data exists. Thermal, stress or flow overlays come from their
respective models; the animation itself cannot prove those quantities.

A machine or robot may show joint motion, gear/transmission movement, cable
routing, spring/damper travel and contact states according to the available
models.

## 8. Drone flight example

A drone scene may combine:

- vehicle pose and trajectory;
- propeller/motor animation;
- motor RPM;
- thrust/force vectors;
- battery state;
- motor/ESC temperature;
- wind/environment vectors;
- payload motion;
- vibration or structural result overlays.

Flight animation must replay a recorded or computed trajectory. It must not
silently invent dynamics merely to look plausible.

## 9. Dimension authority

Displayed dimensions should have explicit origin:

1. **authoritative design dimension** — preferred for engineering/manufacturing;
2. **derived exact CAD measurement** — useful when explicitly identified;
3. **visual/mesh measurement** — inspection aid only.

The UI must distinguish these classes. A triangle mesh measurement must not
silently overwrite a parametric CAD dimension or tolerance.

## 10. Time-synchronized playback

Motion and fields should share an explicit time basis where comparable.

A playback frame may reference:

```text
time
position / orientation
joint coordinates
RPM / velocity
forces / torque
current / voltage
temperature
stress / displacement
battery / lifecycle state
```

If result channels use different clocks or representative windows, the viewer
must use Forge's declared mappings rather than fake temporal alignment.

## 11. Scientific overlays and failure visualization

The viewer can make scientific results easier to understand, but presentation
must preserve authority.

A thermal/electrical failure visualization should follow:

```text
authoritative operating condition
 -> electrical result / losses
 -> thermal result
 -> applicable material/component limit
 -> uncertainty / model discrepancy / evidence state
 -> margin / limit evaluation
 -> visual overlay
```

Examples that may be displayed when supported:

- winding insulation thermal-limit margin;
- wire/connector current or thermal margin;
- bearing temperature/speed/load margin;
- magnet thermal margin;
- battery thermal/electrical limits;
- structural stress/strain margin;
- component vibration or fatigue state;
- cooling/flow shortfalls.

Missing uncertainty, applicability, material limits or model-discrepancy
information stays visible as UNKNOWN. The UI must not turn an UNKNOWN into a
green "safe" state.

## 12. Visual semantics

Colour and animation can mislead. Therefore:

- every colour scale must name the represented quantity and units;
- thresholds must reference their source/identity;
- clipped or saturated ranges must be visible;
- interpolation/smoothing must not be presented as higher-fidelity data;
- "safe", "warning", "critical" or "failure" labels require declared rules;
- model/measurement uncertainty should be inspectable where available;
- solver agreement does not become validation because two overlays look alike;
- visual appeal never upgrades scientific evidence.

## 13. Provider strategy

Initial implementation target:

- **Three.js** for interactive web rendering;
- **glTF/GLB** as an efficient presentation-asset format where appropriate;
- CAD conversion/tessellation handled by the CAD/geometry provider layer;
- field/result conversion handled by scientific result adapters.

If Three.js lacks an exact engineering operation, Forge may:

1. use a Three.js extension;
2. implement a bounded renderer/plugin feature;
3. delegate exact CAD/geometry work to an OpenCascade/FreeCAD/CadQuery-class
   provider and render the result;
4. add another VisualizationProvider such as ParaView/VTK, Babylon.js,
   WebGPU or Unity where a use case justifies it.

The renderer must not force scientific or product contracts to become
Three.js-specific.

## 14. Definition of success

The layer is useful when the same authoritative Forge product can be explored
as:

```text
whole product
 -> exact assembly hierarchy
 -> transparent/cutaway/exploded view
 -> exact dimension annotations
 -> time-based motion
 -> scientific overlays
 -> limits/margins/evidence
```

while preserving the distinction between what is merely rendered, what was
computed, what was measured and what is scientifically supported.
