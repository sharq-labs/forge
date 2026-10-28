"""Declared L1 family. No fixture truth is consulted by the simulator."""
from engcore.mind.repsem.families import DeclaredFamily, FamilySlot
from engcore.mind.repsem.roles import VariableRole
from engcore.mind.repsem.v2 import FamilyContract


def ohmic(parameters, trajectory, constants):
    return parameters["resistance"] * trajectory.slots["current"], {}


def contracts():
    family = DeclaredFamily("ohmic", "Known static ohmic family; parameter estimation only",
                            (FamilySlot("current", (VariableRole.CONTROLLED_INPUT,)),),
                            ("resistance",), ohmic)
    return {"ohmic": FamilyContract(family, "development-1", "s", "V", {"current": "A"},
                                    {"resistance": "ohm"}, {}, {})}
