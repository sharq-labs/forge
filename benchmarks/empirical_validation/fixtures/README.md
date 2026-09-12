# Raw fixtures

Every file here is a plain JSON object of physical quantities. Nothing in this
directory imports engcore, names an engcore class, or is expressed in the units
engcore happens to store internally.

Two rules govern the contents:

1. **Units are in the key.** `mass_g`, not `mass`. A fixture that says only
   `mass: 250.0` would let either side read it in whatever unit suited it, and
   a unit fault would then be unobservable.

2. **Nothing is pre-derived.** A lumped body is declared as a mass, a specific
   heat, an area and a film coefficient — not as a heat capacity and a
   conductance. `C = m c_p` and `hA = h A` are performed twice, once in each
   adapter, so a geometry or property mix-up shows up as a disagreement instead
   of having been resolved before either side saw it.

The units chosen are deliberately the ones a datasheet or a lab notebook uses:
mAh, mV, mOhm, kOhm, L/min, g/cm3, kJ/mol, ppm/K, degC, minutes. A fixture
already written in joules per kelvin and cubic metres per second would test no
unit handling at all, which is most of what this round is for.
