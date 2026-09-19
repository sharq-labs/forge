# Universal Equation / Law IR

The Equation IR is the domain-neutral symbolic contract beneath scientific-law
validation. It represents equations as typed data rather than executable text.

## Guarantees

- every symbol has an explicit declared unit at the Law boundary;
- addition/subtraction require equal dimensions;
- multiplication/division compose exact dimension vectors;
- powers use exact rational exponents;
- exp/log/sin/cos/tan require dimensionless arguments;
- sqrt halves dimension exponents exactly;
- an equation's left and right sides must have the same physical dimension;
- arbitrary callables, eval and exec are not part of the representation;
- evaluation accepts only typed `Quantity` bindings;
- evaluation returns numeric sides and residual only — never a scientific
  support/validation verdict.

Applicability, evidence, uncertainty and validation remain separate layers.
A dimensionally correct equation can still be scientifically inapplicable.

## Stability and identity

V1 is exposed as the `engcore.scientific.equations` subpackage rather than
being added immediately to the frozen `engcore.scientific.__all__` surface.
That lets the contract be exercised and hardened before a future explicit API
freeze.

`equation_fingerprint` and `law_fingerprint` hash deterministic serialized
content, so provenance can bind an assessment to the exact equation/law
contract it used. Dimension reports and equation evaluations revalidate their
own claims when deserialized; a forged PASS or forged residual is refused.

## Provenance binding

`LawReference` records both the semantic `law_id` and the SHA-256 content
fingerprint. A replay that resolves the same id to different equation bytes,
symbol units, assumptions or references is refused as
`law_fingerprint_mismatch`.

`LawRegistry` is explicit and instance-owned; the Core creates no global law
catalogue and never silently replaces an existing identity.
