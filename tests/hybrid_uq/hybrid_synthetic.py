"""Synthetic calibration problems for the V2 route tests: an analytic model through the frozen ``calibrate``."""

from __future__ import annotations

import math

import numpy as np

from engcore.inference import (
    AdmittedForwardTable,
    CalibrationParameterSet,
    CalibrationSpec,
    GaussianObservation,
    NoiseModel,
    ObservationSet,
    ParameterBounds,
    ParameterIdentity,
    ParameterTransform,
    calibrate,
    gaussian_grid_posterior,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity

MODEL = ModelReference("hybrid-uq-synthetic.model", "1")
UNIT = "dimensionless"


class Problem:
    """``model(theta, x) -> predictions``; observations drawn once with a fixed seed."""

    def __init__(self, label, model, x, truth, sigma, lower, upper, start, *, seed=20260913, transforms=None,
                 names=None, observed=None):
        self.label, self.model = label, model
        self.x = np.asarray(x, dtype=float)
        truth = np.asarray(truth, dtype=float)
        self.sigma = np.full(len(self.x), float(sigma))
        if observed is None:
            rng = np.random.default_rng(seed)
            observed = model(truth, self.x) + rng.normal(0.0, self.sigma)
        self.observed = np.asarray(observed, dtype=float)
        p = len(truth)
        names = names or tuple(f"theta{i + 1}" for i in range(p))
        transforms = transforms or ("identity",) * p
        self.parameters = CalibrationParameterSet(tuple(
            ParameterIdentity(name=names[i], unit=UNIT, model=MODEL,
                              bounds=ParameterBounds(Quantity(float(lower[i]), UNIT), Quantity(float(upper[i]), UNIT)),
                              transform=ParameterTransform(transforms[i]))
            for i in range(p)))
        self.observations = ObservationSet(tuple(
            GaussianObservation(condition_id=f"x{i}", observable_name="y", value=Quantity(float(v), UNIT),
                                sigma=Quantity(float(s), UNIT), source_ref=f"synthetic:{label}:{i}")
            for i, (v, s) in enumerate(zip(self.observed, self.sigma))), dataset_id=f"synthetic.{label}")
        self.spec = CalibrationSpec(parameters=self.parameters, fixed={},
                                    initial_point={n: Quantity(float(v), UNIT) for n, v in zip(names, start)},
                                    noise_model=NoiseModel())
        self.calls = 0

    def forward(self, theta):
        self.calls += 1
        values = self.model(np.asarray(theta, dtype=float), self.x)
        if values is None or not np.all(np.isfinite(values)):
            return None
        return [Quantity(float(v), UNIT) for v in values]

    def calibrate(self):
        return calibrate(self.spec, self.observations, self.forward, heldout_dataset_id=f"synthetic.{self.label}.heldout")

    def grid(self, axes):
        mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
        keys = self.observations.keys
        values = np.asarray([self.model(row, self.x) for row in mesh], dtype=float)
        ok = np.all(np.isfinite(values), axis=1)
        table = AdmittedForwardTable(parameter_names=self.parameters.names, observation_keys=keys, points=mesh,
                                     values=np.where(ok[:, None], values, 0.0), admissible_mask=ok,
                                     admission_refs=tuple((("analytic|fixture|ver|bind",) * len(keys)) if o else () for o in ok),
                                     rejection_reasons=tuple("" if o else "non-finite" for o in ok),
                                     observation_units=(UNIT,) * len(keys))
        return gaussian_grid_posterior(table, self.observations)

    def table_builder(self):
        keys = self.observations.keys

        def build(points):
            mesh = np.asarray(points, dtype=float)
            values = np.asarray([self.model(row, self.x) for row in mesh], dtype=float)
            ok = np.all(np.isfinite(values), axis=1)
            return AdmittedForwardTable(parameter_names=self.parameters.names, observation_keys=keys, points=mesh,
                                        values=np.where(ok[:, None], values, 0.0), admissible_mask=ok,
                                        admission_refs=tuple((("analytic|fixture|ver|bind",) * len(keys)) if o else () for o in ok),
                                        rejection_reasons=tuple("" if o else "non-finite" for o in ok),
                                        observation_units=(UNIT,) * len(keys))
        return build


def conditioned(problem):
    """The problem's observations with each one's x declared as its condition (CORE-006: the calibrated range).

    Separate from ``Problem.observations`` so every existing observation keeps its bytes; a prediction check passes this
    as ``calibration_observations`` and declares its own x on the spec.
    """
    return ObservationSet(tuple(
        GaussianObservation(o.condition_id, o.observable_name, o.value, o.sigma, o.source_ref,
                            conditions={"x": Quantity(float(x), UNIT)})
        for o, x in zip(problem.observations.observations, problem.x)), dataset_id=problem.observations.dataset_id)


def affine(label="affine", **kw):
    x = np.linspace(0.0, 1.0, 12)
    return Problem(label, lambda t, x: t[0] + t[1] * x, x, (1.0, 2.0), 0.05, (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0), **kw)


def strong_nonlinearity():
    return Problem("F1_strong_nonlinearity", lambda t, x: t[1] * np.exp(-t[0] * x), np.linspace(0.0, 1.0, 8),
                   (3.0, 2.0), 0.35, (0.01, 0.01), (20.0, 10.0), (1.0, 1.0))


def at_bound():
    return Problem("F2_parameter_at_bound", lambda t, x: t[0] + t[1] * x, np.linspace(0, 1, 10), (1.0, -0.05), 0.02,
                   (0.0, 0.0), (5.0, 5.0), (0.5, 0.5))


def nearly_singular():
    return Problem("F3_nearly_singular", lambda t, x: t[0] * x + t[1] * (x + 1e-9 * x ** 2), np.linspace(1.0, 2.0, 10),
                   (1.0, 1.0), 0.01, (-10.0, -10.0), (10.0, 10.0), (0.5, 0.5))


def mirror_mode():
    return Problem("F4_mirror_mode", lambda t, x: t[0] ** 2 * x, np.linspace(1.0, 2.0, 6), (1.0,), 0.05, (-3.0,), (3.0,), (0.5,))


def weak_identification():
    return Problem("F5_weak_identification", lambda t, x: t[0] + t[1] * x, np.linspace(10.0, 10.05, 6), (1.0, 0.3), 0.01,
                   (-50.0, -5.0), (50.0, 5.0), (0.0, 0.0))


def log_parameterization(transform):
    return Problem(f"F6_k_{transform}", lambda t, x: t[0] * x, np.linspace(0.1, 1.0, 8), (0.2,), 0.1, (1e-6,), (5.0,), (1.0,),
                   transforms=(transform,))


def thin_ridge():
    """Affine, thin and strongly correlated: the Gaussian is exact; a coarse grid over the bounds aliases."""
    return weak_identification()


def bimodal_two_parameter():
    return Problem("bimodal_2p", lambda t, x: t[0] ** 2 * x + t[1], np.linspace(1.0, 2.0, 10), (1.0, 0.5), 0.05,
                   (-3.0, -2.0), (3.0, 2.0), (0.5, 0.0))


def gaussian_truth(problem):
    """The exact posterior of an affine model with bounds far away: the weighted least-squares Gaussian."""
    X = np.column_stack([np.ones_like(problem.x), problem.x]) / problem.sigma[:, None]
    cov = np.linalg.inv(X.T @ X)
    return cov @ X.T @ (problem.observed / problem.sigma), cov


def nan_guard(value):
    return value if math.isfinite(value) else None
