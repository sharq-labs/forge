from engcore.mind.repsem.families import DeclaredFamily, FamilySlot
from engcore.mind.repsem.roles import VariableRole
from engcore.mind.repsem.v2 import FamilyContract


def linear(parameters, trajectory, constants):
    return parameters["coefficient"] * trajectory.slots["current"], {}


def quadratic(parameters, trajectory, constants):
    return parameters["coefficient"] * trajectory.slots["current"] ** 2, {}


def contracts():
    return {name: FamilyContract(
        DeclaredFamily(name, "Declared public development family", (FamilySlot("current", (VariableRole.CONTROLLED_INPUT,)),),
                       ("coefficient",), function), "development-1", "s", "V", {"current": "A"},
        {"coefficient": unit}, {}, {})
        for name, function, unit in (("linear", linear, "ohm"), ("quadratic", quadratic, "V/A**2"))}
