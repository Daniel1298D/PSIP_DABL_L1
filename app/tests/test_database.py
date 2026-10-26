"""Opt-in integration checks against the test database only."""

import os
import unittest
from unittest.mock import patch

import psycopg
from shapely.geometry import MultiPolygon

import load


@unittest.skipUnless(os.getenv('RUN_DB_INTEGRATION') == '1', 'Opt-in database integration test')
class DatabaseTests(unittest.TestCase):
    def snapshot(self):
        with psycopg.connect(host=os.getenv('PGHOST', 'postgis'), port=os.getenv('PGPORT', '5432'),
                             user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
                             dbname=os.environ['POSTGRES_DB']) as conn:
            return conn.execute('''SELECT resolution,count(*),
                md5(string_agg(h3_index || ST_AsEWKT(geom_clipped), ',' ORDER BY h3_index))
                FROM grid.h3_cells GROUP BY resolution ORDER BY resolution''').fetchall()

    def test_repeat_load_and_failure_rollback(self):
        load.main()
        before = self.snapshot()
        load.main()
        self.assertEqual(before, self.snapshot())
        original = load.generate_grid

        def invalid_grid(*args):
            for i, (res, cell, full, clipped) in enumerate(original(*args)):
                yield res, cell, full, MultiPolygon() if i == 0 else clipped

        with patch.object(load, 'generate_grid', invalid_grid):
            with self.assertRaises(psycopg.errors.CheckViolation):
                load.main()
        self.assertEqual(before, self.snapshot(), 'Failed reload must preserve the previous grid')
