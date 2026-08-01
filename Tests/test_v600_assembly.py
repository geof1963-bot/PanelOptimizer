# -*- coding: utf-8 -*-
"""Focused V6.00 canonical assembly contracts."""

from __future__ import annotations

import unittest

from Core.DowelPlanner import DowelAxis, _axis_mismatch


class V600AssemblyTests(unittest.TestCase):
    """Verify the mathematical hard requirements independently of OCC."""

    @staticmethod
    def _axis(origin=(10.0, 20.0, 2.5), direction=(0.0, 1.0, 0.0)):
        return DowelAxis(
            origin_xyz_mm=origin,
            direction_xyz=direction,
            hole_diameter_mm=5.0,
            nominal_length_mm=30.0,
            useful_depth_limits_mm=(12.0, 13.0),
        )

    def test_one_canonical_axis_is_exactly_coaxial_with_itself(self):
        axis = self._axis()
        self.assertEqual(_axis_mismatch(axis, axis), (0.0, 0.0))

    def test_centerline_offset_is_rejected(self):
        first = self._axis()
        second = self._axis(origin=(10.03, 20.0, 2.5))
        _angle, centerline = _axis_mismatch(first, second)
        self.assertGreater(centerline, 0.02)

    def test_angular_offset_is_rejected(self):
        first = self._axis()
        second = self._axis(direction=(0.003, 0.9999955, 0.0))
        angle, _centerline = _axis_mismatch(first, second)
        self.assertGreater(angle, 0.1)

    def test_axis_carries_one_shared_cutter_definition(self):
        axis = self._axis()
        self.assertEqual(axis.direction_xyz[2], 0.0)
        self.assertEqual(axis.nominal_length_mm, 30.0)
        self.assertEqual(axis.useful_depth_limits_mm, (12.0, 13.0))


if __name__ == "__main__":
    unittest.main()
