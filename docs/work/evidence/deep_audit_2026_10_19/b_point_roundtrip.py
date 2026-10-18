# Independent derivation: does a point range declared as (lower in K, upper in degC) survive the
# float comparison `upper.magnitude_in(lower.units) == lower.magnitude` (materials/ranges.py:73,82)?
# Assumes the degC->K map is x + 273.15 evaluated in binary64 (the standard affine definition).
bad = []
for tenths in range(-500, 10001):
    c = tenths / 10.0          # degC as a user would type it
    k_typed = round(c + 273.15, 2)   # the kelvin value a user would type for the same temperature
    k_conv = c + 273.15
    if k_conv != k_typed:
        bad.append((c, k_typed, k_conv))
print(len(bad), "of 10501 one-decimal degC values do not convert to the typed kelvin value exactly")
for c, kt, kc in bad[:5]:
    print(f"  {c} degC -> {kc!r} K, typed {kt!r} K ({'below' if kc < kt else 'above'})")
above = [b for b in bad if b[2] > b[1]]
print(len(above), "convert ABOVE the typed kelvin value (range becomes a non-point sliver, not refused)")
for c, kt, kc in above[:3]:
    print(f"  {c} degC -> {kc!r} K, typed {kt!r} K")
# reverse declaration: lower in degC (self.unit = degC), upper in K converted by k - 273.15
rev_above = rev_below = 0
example = None
for tenths in range(-500, 10001):
    c = tenths / 10.0
    k = round(c + 273.15, 2)
    back = k - 273.15
    if back > c:
        rev_above += 1
        example = example or (c, k, back)
    elif back < c:
        rev_below += 1
print(f"lower in degC / upper in K: {rev_above} slivers (upper converts above lower, not refused, not a point), "
      f"{rev_below} refused as 'upper below lower'; e.g. {example}")
