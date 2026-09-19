"""Bind assurance and law identities into generic replay artifacts."""

from __future__ import annotations

from ..scientific.equations import LawReference
from ..scientific.replay_core import ArtifactIdentity
from .assurance_bundle import AssuranceBundle


def assurance_artifact(bundle:AssuranceBundle)->ArtifactIdentity:
    return ArtifactIdentity("assurance_bundle","scientific-assurance",bundle.digest)


def law_artifact(reference:LawReference)->ArtifactIdentity:
    return ArtifactIdentity("scientific_law",reference.law_id,reference.fingerprint)
