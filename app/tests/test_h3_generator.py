import unittest

import h3
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from python.h3_generator import generate_grid, parse_resolutions, read_county


class GridTests(unittest.TestCase):
    def assert_coverage(self, county, resolution=8):
        rows = list(generate_grid(county, [resolution]))
        self.assertTrue(rows)
        self.assertEqual(len(rows), len({row[1] for row in rows}))
        for res, cell, full, clipped in rows:
            self.assertTrue(h3.is_valid_cell(cell))
            self.assertEqual(h3.get_resolution(cell), res)
            self.assertTrue(full.is_valid and clipped.is_valid)
            self.assertGreater(clipped.area, 0)
            self.assertLess(clipped.difference(county).area, 1e-12)
        covered = unary_union([row[3] for row in rows])
        self.assertLess(county.symmetric_difference(covered).area / county.area, 1e-8)

    def test_holes_and_disjoint_polygons(self):
        shell = [(20,52), (20.1,52), (20.1,52.1), (20,52.1)]
        hole = [(20.03,52.03), (20.07,52.03), (20.07,52.07), (20.03,52.07)]
        self.assert_coverage(MultiPolygon([Polygon(shell,[hole]), box(20.2,52,20.21,52.01)]))

    def test_tiny_area_includes_boundary_cell(self):
        self.assert_coverage(box(20,52,20.00001,52.00001), 6)

    def test_resolution_validation(self):
        self.assertEqual(parse_resolutions('9,6,6,7'), (6,7,9))
        for value in ('', 'abc', '-1', '11', '6,,7'):
            with self.assertRaises(ValueError):
                parse_resolutions(value)

    def test_actual_county_transformation_and_coverage(self):
        county = read_county('/data/powiat.shp')
        minx,miny,maxx,maxy = county.bounds
        self.assertTrue(14 < minx < maxx < 25 and 49 < miny < maxy < 55)
        self.assert_coverage(county, 6)


if __name__ == '__main__':
    unittest.main()
