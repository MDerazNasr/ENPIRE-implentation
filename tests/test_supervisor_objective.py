from __future__ import annotations

import math
import unittest

import numpy as np

from supervisor.objective_adapter import (
    ActorObjectiveAdapter,
    ObjectiveError,
    frozen_reference_objective,
)


class Dual:
    def __init__(self, value, gradient):
        self.value = value
        self.gradient = tuple(gradient)

    def __add__(self, other):
        other = other if isinstance(other, Dual) else Dual(other, (0, 0, 0))
        return Dual(
            self.value + other.value,
            tuple(a + b for a, b in zip(self.gradient, other.gradient)),
        )

    __radd__ = __add__

    def __mul__(self, other):
        other = other if isinstance(other, Dual) else Dual(other, (0, 0, 0))
        return Dual(
            self.value * other.value,
            tuple(
                self.value * b + other.value * a
                for a, b in zip(self.gradient, other.gradient)
            ),
        )

    __rmul__ = __mul__


class ObjectiveAdapterTests(unittest.TestCase):
    def test_default_matches_frozen_reference_for_arrays(self) -> None:
        actor = np.array([1.0, 2.0], dtype=np.float32)
        bc = np.array([0.5, 0.25], dtype=np.float32)
        weight = np.float32(0.2)
        actual = ActorObjectiveAdapter().combine(actor, bc, weight)
        expected = frozen_reference_objective(actor, bc, weight)
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.dtype, np.float32)
        self.assertEqual(actual.shape, actor.shape)

    def test_default_matches_reference_gradients_without_framework_dependency(self) -> None:
        actor = Dual(2.0, (1, 0, 0))
        bc = Dual(3.0, (0, 1, 0))
        weight = Dual(0.25, (0, 0, 1))
        actual = ActorObjectiveAdapter().combine(actor, bc, weight)
        expected = frozen_reference_objective(actor, bc, weight)
        self.assertEqual(actual.value, expected.value)
        self.assertEqual(actual.gradient, expected.gradient)
        self.assertEqual(actual.gradient, (1.0, 0.25, 3.0))

    def test_plugin_boundary_accepts_custom_math_and_rejects_bad_scalars(self) -> None:
        adapter = ActorObjectiveAdapter(plugin=lambda actor, bc, weight: actor + bc)
        self.assertEqual(adapter.combine(2.0, 3.0, 0.1), 5.0)
        for plugin in (lambda *_: None, lambda *_: math.inf, lambda *_: math.nan):
            with self.subTest(plugin=plugin):
                with self.assertRaises(ObjectiveError):
                    ActorObjectiveAdapter(plugin=plugin).combine(1.0, 2.0, 0.5)


if __name__ == "__main__":
    unittest.main()
