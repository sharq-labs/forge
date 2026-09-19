"""Explicit registry for scientific law definitions.

There is deliberately no global registry.  A caller owns a registry instance
and therefore owns which law contracts are in scope for a run.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..errors import DuplicateRegistrationError
from .errors import LawIdentityError
from .law import LawDefinition
from .reference import LawReference


class LawRegistry:
    def __init__(self, laws: Iterable[LawDefinition] = ()) -> None:
        self._laws: dict[str, LawDefinition] = {}
        for law in laws:
            self.register(law)

    def register(self, law: LawDefinition) -> None:
        if not isinstance(law, LawDefinition):
            raise TypeError("LawRegistry.register requires LawDefinition")
        if law.law_id in self._laws:
            raise DuplicateRegistrationError(
                f"scientific law {law.law_id!r} is already registered"
            )
        self._laws[law.law_id] = law

    def get(self, law_id: str) -> LawDefinition:
        key = str(law_id).strip()
        try:
            return self._laws[key]
        except KeyError:
            raise LawIdentityError(
                "law_not_found",
                f"scientific law {key!r} is not registered",
            ) from None

    def reference(self, law_id: str) -> LawReference:
        return LawReference.from_law(self.get(law_id))

    def references(self) -> tuple[LawReference, ...]:
        return tuple(
            LawReference.from_law(self._laws[key])
            for key in sorted(self._laws)
        )

    def __contains__(self, law_id: object) -> bool:
        return isinstance(law_id, str) and law_id in self._laws

    def __len__(self) -> int:
        return len(self._laws)
