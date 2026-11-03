"""Hand-calculated PostGIS fixtures for the normalization and IOP definition."""
import os
import unittest

from psycopg import sql
from python.bdot_common import connect
from python.calculate_iop import DEFAULT_WEIGHTS, create_result, load_weights


class ConfigTests(unittest.TestCase):
    def test_complete_inventory_and_user_weights(self):
        _, weights, _ = load_weights(DEFAULT_WEIGHTS)
        self.assertEqual(len(weights), 73)
        for column, expected in {'bubd_a': -.8, 'ptlz_a': -.8, 'ptwp_a': -1., 'skdr_l': .7, 'skjz_l': .7}.items():
            self.assertEqual(weights[column]['weight'], expected)


@unittest.skipUnless(os.getenv('RUN_IOP_INTEGRATION') == '1', 'Opt-in PostGIS IOP test')
class IopTests(unittest.TestCase):
    def test_positive_minimum_integer_metric_zero_maximum_and_neutral_weight(self):
        # Building values are 5 and 10: max scaling must give .5/1, not min-max 0/1.
        # Four criteria include both an empty one and a zero-weight one in the divisor.
        criteria = {c: {'weight': w} for c, w in [('building', -.8), ('road', .7), ('empty', -1.), ('neutral', 0.)]}
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TEMP TABLE source_fixture(id bigint,h3_index text,
                    building double precision,road bigint,empty double precision,neutral double precision,
                    geom geometry(MultiPolygon,2180));
                    INSERT INTO source_fixture VALUES
                    (1,'cell1',5,10,0,7,ST_Multi(ST_MakeEnvelope(0,0,1,1,2180))),
                    (2,'cell2',10,0,0,7,ST_Multi(ST_MakeEnvelope(1,0,2,1,2180)))''')
                count, stats = create_result(cur, sql.Identifier('source_fixture'), sql.Identifier('pg_temp', 'iop_fixture'), criteria)
                self.assertEqual(count, 2)
                self.assertEqual(stats['empty'], (0., 0))
                cur.execute('SELECT building_norm,road_norm,empty_norm,neutral_norm,iop FROM iop_fixture ORDER BY id')
                rows = cur.fetchall()
                self.assertEqual(rows[0][:4], (.5, 1., 0., 1.))
                self.assertEqual(rows[1][:4], (1., 0., 0., 1.))
                self.assertAlmostEqual(rows[0][4], .075)
                self.assertAlmostEqual(rows[1][4], -.2)
                cur.execute('UPDATE source_fixture SET building=0,road=0,neutral=0')
                create_result(cur, sql.Identifier('source_fixture'), sql.Identifier('pg_temp', 'zero_fixture'), criteria)
                cur.execute('SELECT count(*) FROM zero_fixture WHERE building_norm<>0 OR road_norm<>0 OR empty_norm<>0 OR neutral_norm<>0 OR iop<>0')
                self.assertEqual(cur.fetchone()[0], 0)
                # A different resolution has a different observed maximum.
                cur.execute('UPDATE source_fixture SET building=5')
                create_result(cur, sql.Identifier('source_fixture'), sql.Identifier('pg_temp', 'other_resolution_fixture'), criteria)
                cur.execute('SELECT min(building_norm),max(building_norm) FROM other_resolution_fixture')
                self.assertEqual(cur.fetchone(), (1., 1.))
                for invalid in (None, -1., float('inf'), float('nan')):
                    cur.execute('UPDATE source_fixture SET building=%s WHERE id=1', (invalid,))
                    with self.assertRaisesRegex(ValueError, 'Invalid source metric'):
                        create_result(cur, sql.Identifier('source_fixture'), sql.Identifier('pg_temp', 'bad_fixture'), criteria)


if __name__ == '__main__':
    unittest.main()
