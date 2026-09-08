"""What the Scientific Core is allowed to know the name of.

The rule, stated once and enforced below:

    The core knows shapes, not things. It may know a quantity has components;
    it may not know one of them is a force. It may know a condition compares
    two quantities; it may not know they are thrust and weight.

`test_the_scientific_core_owns_no_cstr_specific_rule` has enforced a narrow
version of this since GUARD 3, and it earned its place the day it was written:
it caught that commit putting the string `CSTR` into
`scientific/results/thresholds.py`. But it checks **six known domain words**,
and the core is about to gain composite quantities, relational conditions and
hierarchical problems. The risk those bring is not that someone writes `CSTR`
again. It is that one system's vocabulary arrives *with* the new shapes --
`thrust` beside a composite quantity, `battery` beside a hierarchical problem
-- and a guard listing today's domain words has nothing to say about it.

Two vocabularies, two reaches
-----------------------------
These are checked differently, and the difference is the whole design.

**Derived domain names -- checked in CODE only.** `battery`, `electrical`,
`kinetics`, `thermal`, `thermal_models`, and whatever the sixth domain is
called, read off the domain packages by :func:`derived_domain_names` rather
than listed. A name that appears in an identifier, or in a string literal that
is not a docstring, is the core branching on a domain: `if domain ==
"battery"` is leakage whatever it is spelled like. But the same word in prose
is usually the core *documenting its own ignorance*. `solvers/capability.py`
says:

    Domain packages add their own names (``electrical:dc``, ``thermal:steady``)
    without touching this class.

That sentence is the separation being explained. A guard that forbade it would
punish exactly the documentation a reader needs, and would be reported as
core contamination by someone who had made the core cleaner. Nine such
occurrences exist today across six files, every one of them a comment or a
docstring, and every one of them correct.

**Curated thing-terms -- checked in ALL text, prose included.** `thrust`,
`propeller`, `reactor`, `rpm`, `neutron`, `refrigerant` and the rest below.
These have no legitimate reason to appear in the core at all: a core docstring
that reaches for `thrust` to explain a shape is the core starting to think in
one system's terms, which is the thing being prevented. This reach is also
what preserves the original catch -- **the `CSTR` that GUARD 3 leaked was in a
class docstring**, not in code, so a code-only guard would have let it
through. `cstr` is in the curated list for that reason.

How the curated list was chosen
-------------------------------
Three rules, applied in order. Every entry satisfies all three.

1. **It names a thing, not a shape.** A physical object, a device, a material,
   a whole system, or a physical quantity that only one system measures.
2. **It occurs zero times under `scientific/` today.** The guard states an
   invariant the core already holds; it is not a cleanup ticket disguised as a
   check. A term the core already uses would make this fail on arrival, and a
   guard that fails for a pre-existing reason gets suppressed rather than
   fixed.
3. **It is not an ordinary English word whose non-physical sense belongs in
   core prose.**

Rule 3 is the one that did work, and what it excluded is worth recording,
because each looks like an obvious entry until measured:

    payload      542 occurrences in the core -- a serialization payload
    current        7 -- the adjective, almost always
    thermal        6 -- prose about the layering (rule 2)
    bearing        5 -- "load-bearing", "has a bearing on"
    resistance     5 -- both the physical and the ordinary sense
    voltage        4 -- docstring illustrations (rule 2)
    electrical     2 -- prose about the layering (rule 2)
    battery        1 -- a comment recounting a bug (rule 2)
    reynolds       1 -- a docstring example (rule 2)
    drag           1 -- the verb
    cell           0 -- excluded anyway: a table cell is too plausible
    lift           0 -- excluded anyway: the verb, as in "lifts out"
    altitude       0 -- excluded anyway: this repository uses it to mean
                        level of abstraction, not height
    fin            0 -- excluded anyway: too short to be worth the risk

`voltage`, `resistance` and `reynolds` are genuinely domain vocabulary sitting
in core docstrings as illustrations. Rule 2 excludes them, which is a
deliberate narrowing rather than an oversight: forbidding them is a change to
the core's prose, and this guard is not the place to make it. They are the
obvious next candidates if anyone wants to.

The shape vocabulary
--------------------
`quantity`, `condition`, `relation`, `component`, `series` and `composition`
are the core's own language and are never forbidden, by either reach. That
allowance is a hole if a future domain package is ever named one of them, so
:func:`shape_vocabulary_collisions` reports that collision and a test fails on
it rather than the allowance silently winning.
"""

from __future__ import annotations

import ast
import pathlib
import re

#: Repository root, from this file's location.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

SRC = REPO_ROOT / "src"
CORE = SRC / "engcore" / "scientific"

#: The package parents whose subdirectories name a domain or a system.
#:
#: Both, deliberately. `systems/` names composed systems -- `aerospace`,
#: `electrothermal` -- and a system's name has no more business in the core
#: than a domain's.
DOMAIN_PARENTS = (SRC / "engcore" / "domains", SRC / "engcore" / "systems")

#: The core's own language. Never forbidden, by either reach.
SHAPE_VOCABULARY = frozenset(
    {"quantity", "condition", "relation", "component", "series", "composition"}
)

#: Physical objects, materials, whole systems and system-specific quantities.
#: See the module docstring for the three rules every entry satisfies.
FORBIDDEN_TERMS = frozenset(
    {
        # devices and parts
        "propeller", "rotor", "motor", "resistor", "reactor", "cstr",
        "turbine", "airfoil", "wing", "nozzle", "valve", "gearbox",
        "capacitor", "inductor", "transistor", "diode", "electrode",
        "anode", "cathode", "heatsink", "pump", "conductor",
        # media and materials
        "coolant", "refrigerant",
        # physical quantities only one system measures
        "thrust", "torque", "rpm", "neutron", "amperage", "enthalpy",
        "concentration", "arrhenius", "nusselt", "prandtl", "stoichiometry",
        "combustion", "airspeed",
        # whole systems and vehicles
        "drone", "vehicle", "chassis", "propulsion", "aerospace",
        "electrothermal",
        # A domain name that is clean in core prose today, so the reach the
        # narrow guard had over it is not quietly given up by moving domain
        # names to the code-only rule.
        "kinetics",
    }
)

#: The six terms the narrow guard checked. Kept as a named set so
#: `test_cstr_domain.py` can assert they are still covered: this list must be
#: widenable and must not be shrinkable.
NARROW_GUARD_TERMS = frozenset(
    {"cstr", "arrhenius", "reactor", "kinetics", "coolant", "concentration"}
)

#: Splits an identifier into lowercase word parts, snake_case and CamelCase
#: alike: `ThermalModelsRegistry` and `thermal_models_registry` both give
#: ("thermal", "models", "registry").
_IDENT_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|[0-9]+")
_TEXT_WORDS = re.compile(r"[A-Za-z]+")


def derived_domain_names() -> tuple[str, ...]:
    """Every domain and system package name, read off the tree.

    **Walked, not listed.** A guard from a hand-maintained list guards only
    what someone remembered, and the name most worth forbidding is the one
    nobody has written down yet -- the sixth domain's. This makes that name
    forbidden the day the package exists.

    Names are taken **whole and never split on ``_``**. Splitting
    `thermal_models` yields `models`, which is core vocabulary in every sense,
    and a guard forbidding it would fail on arrival for a reason having
    nothing to do with layering.
    """
    names: set[str] = set()
    for parent in DOMAIN_PARENTS:
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if child.is_dir() and (child / "__init__.py").is_file():
                names.add(child.name.lower())
    return tuple(sorted(names))


def shape_vocabulary_collisions() -> tuple[str, ...]:
    """Domain names the shape allowance would silently un-forbid.

    Empty today. If a package is ever named `composition`, the allowance
    would quietly stop the guard seeing it, so this is surfaced and asserted
    on rather than left to win by default.
    """
    return tuple(sorted(set(derived_domain_names()) & SHAPE_VOCABULARY))


def _parts(name: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in _IDENT_PARTS.findall(name))


def _contains_run(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    size = len(needle)
    if not size or size > len(haystack):
        return False
    return any(
        haystack[i : i + size] == needle for i in range(len(haystack) - size + 1)
    )


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Identity of every docstring node, so prose can be told from code."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.add(id(value))
    return found


def code_words(path: pathlib.Path) -> list[tuple[str, ...]]:
    """Word-part tuples for everything the module's CODE names.

    Identifiers, attributes, definitions, arguments, keywords -- and string
    literals that are **not** docstrings, because `if domain == "battery"`
    hides a domain name in a string and is exactly the branch being forbidden.
    Comments never reach here: the tokenizer is not used, the AST is, and the
    AST does not carry comments.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_node_ids(tree)
    out: list[tuple[str, ...]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.append(_parts(node.id))
        elif isinstance(node, ast.Attribute):
            out.append(_parts(node.attr))
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            out.append(_parts(node.name))
        elif isinstance(node, ast.arg):
            out.append(_parts(node.arg))
        elif isinstance(node, ast.keyword) and node.arg:
            out.append(_parts(node.arg))
        elif isinstance(node, ast.alias):
            out.append(_parts(node.asname or node.name.replace(".", "_")))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.append(
                    tuple(w.lower() for w in _TEXT_WORDS.findall(node.value))
                )
    return out


def prose_and_code_words(path: pathlib.Path) -> set[str]:
    """Every word anywhere in the file, comments and docstrings included."""
    return {
        w.lower() for w in _TEXT_WORDS.findall(path.read_text(encoding="utf-8"))
    }


def offenders(root: pathlib.Path | None = None) -> list[str]:
    """Every violation of the rule under ``root``, defaulting to the core.

    One string per violation, naming the file, the term, and which reach
    caught it, so a failure says what to do rather than only that something
    is wrong.
    """
    root = CORE if root is None else root
    domain_names = [
        name for name in derived_domain_names() if name not in SHAPE_VOCABULARY
    ]
    curated = FORBIDDEN_TERMS - SHAPE_VOCABULARY

    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:  # a tree outside the repository, as in a mutation copy
            rel = path.as_posix()

        identifiers = code_words(path)
        for name in domain_names:
            needle = _parts(name)
            if any(_contains_run(h, needle) for h in identifiers):
                found.append(
                    f"{rel}: domain name {name!r} used in code -- the core is "
                    f"branching on a domain"
                )
        for term in sorted(prose_and_code_words(path) & curated):
            found.append(
                f"{rel}: {term!r} names a thing -- the core knows shapes, not "
                f"things"
            )
    return found
