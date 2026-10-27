"""Exact small PostGIS cases, including points/lines on a shared hex edge."""
import os
import unittest
from psycopg import sql
from python.bdot_common import connect
from python.aggregate_bdot import metric_query


@unittest.skipUnless(os.getenv('RUN_BDOT_INTEGRATION') == '1', 'Opt-in PostGIS metric test')
class MetricTests(unittest.TestCase):
    def test_area_length_points_and_empty(self):
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TEMP TABLE hex_work(id bigint,geom geometry,excluded_boundary geometry);
                    INSERT INTO hex_work VALUES
                    (1,ST_MakeEnvelope(0,0,1,2,2180),ST_GeomFromText('MULTILINESTRING EMPTY',2180)),
                    (2,ST_MakeEnvelope(1,0,2,2,2180),ST_GeomFromText('MULTILINESTRING((1 0,1 2))',2180));
                    CREATE TEMP TABLE metric_fixture(feature_id bigint,geom geometry)''')
                cases = [
                    (3, ['POLYGON((0.5 0,1.5 0,1.5 2,0.5 2,0.5 0))'], {1:1.0,2:1.0}),
                    (2, ['LINESTRING(0 1,2 1)', 'LINESTRING(1 0,1 2)'], {1:3.0,2:1.0}),
                    (1, ['POINT(0.5 1)','POINT(1 1)','POINT(1.5 1)','POINT(3 3)'], {1:2,2:1}),
                    (1, [], {})]
                for dimension, geometries, expected in cases:
                    cur.execute('DELETE FROM metric_fixture')
                    for i, geometry in enumerate(geometries):
                        cur.execute('INSERT INTO metric_fixture VALUES(%s,ST_GeomFromText(%s,2180))',(i,geometry))
                    cur.execute(metric_query(sql.Identifier('metric_fixture'),'value',dimension))
                    self.assertEqual(dict(cur.fetchall()),expected)
                cur.execute('''CREATE TEMP TABLE zero_fixture(id bigint,value bigint NOT NULL DEFAULT 0);
                    INSERT INTO zero_fixture(id) SELECT id FROM hex_work''')
                query = metric_query(sql.Identifier('metric_fixture'),'value',1)
                cur.execute(sql.SQL('UPDATE zero_fixture z SET value=coalesce(m.value,0) FROM ({}) m WHERE z.id=m.id').format(query))
                cur.execute('SELECT count(*),sum(value),count(*) FILTER(WHERE value IS NULL) FROM zero_fixture')
                self.assertEqual(cur.fetchone(),(2,0,0))
