"""Aggregate BDOT classes into H3 7/8/9 in EPSG:2180; expose only views in 3857."""
from psycopg import sql
from python.bdot_common import connect, log


def metric_query(table, column, dimension):
    """Return per-cell metric SQL. Shared edges/points belong to lowest cell ID."""
    if dimension == 1:
        return sql.SQL('''SELECT id,count(*)::bigint value FROM (
            SELECT DISTINCT ON (b.feature_id,p.path) h.id
            FROM {} b CROSS JOIN LATERAL ST_DumpPoints(b.geom) p
            JOIN hex_work h ON h.geom && p.geom AND ST_Covers(h.geom,p.geom)
            ORDER BY b.feature_id,p.path,h.id) assigned GROUP BY id''').format(table)
    measure = sql.SQL('ST_Area(ST_Intersection(b.geom,h.geom))') if dimension == 3 else sql.SQL(
        'ST_Length(ST_Difference(ST_CollectionExtract(ST_Intersection(b.geom,h.geom),2),h.excluded_boundary))')
    return sql.SQL('''SELECT h.id,sum({}) value FROM hex_work h JOIN {} b
        ON b.geom && h.geom AND ST_Intersects(b.geom,h.geom) GROUP BY h.id''').format(measure,table)


def migrate_grid(cur):
    # H3 identifiers remain unchanged; all stored geometries and clipping become metric.
    cur.execute('''SELECT ST_SRID(geom) FROM grid.powiat LIMIT 1''')
    if cur.fetchone()[0] != 2180:
        cur.execute('''ALTER TABLE grid.powiat ALTER COLUMN geom TYPE geometry(MultiPolygon,2180)
            USING ST_Transform(geom,2180)''')
        cur.execute('''ALTER TABLE grid.h3_cells ALTER COLUMN geom TYPE geometry(Polygon,2180)
            USING ST_Transform(geom,2180)''')
        cur.execute('''ALTER TABLE grid.h3_cells ALTER COLUMN geom_clipped TYPE geometry(MultiPolygon,2180)
            USING ST_Transform(geom_clipped,2180)''')
    cur.execute('''UPDATE grid.h3_cells h SET geom_clipped=
        ST_Multi(ST_CollectionExtract(ST_Intersection(h.geom,p.geom),3)) FROM grid.powiat p''')
    cur.execute('UPDATE grid.h3_cells SET area_m2=ST_Area(geom_clipped)')


def main():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(72480123)')
            cur.execute('SELECT pg_advisory_xact_lock(72480124)')
            migrate_grid(cur)
            cur.execute('CREATE SCHEMA IF NOT EXISTS analysis')
            cur.execute('CREATE SCHEMA IF NOT EXISTS viz')
            cur.execute('''CREATE TABLE IF NOT EXISTS analysis.validation (
                resolution integer,layer_name text,expected double precision,actual double precision,
                absolute_error double precision, PRIMARY KEY(resolution,layer_name))''')
            cur.execute('SELECT layer_name,metric_column,dimension FROM bdot.layer_catalog ORDER BY layer_name')
            layers = cur.fetchall()
            if not layers:
                raise ValueError('Import BDOT first')
            for resolution in (7,8,9):
                name = f'h3_{resolution}'
                result = sql.Identifier('analysis', name)
                cur.execute('''CREATE TEMP TABLE hex_work ON COMMIT DROP AS
                    SELECT row_number() OVER (ORDER BY h3_index)::bigint id,h3_index,geom_clipped geom,
                    ST_GeomFromText('MULTILINESTRING EMPTY',2180) excluded_boundary
                    FROM grid.h3_cells WHERE resolution=%s''',(resolution,))
                cur.execute('CREATE INDEX ON hex_work USING gist(geom)')
                cur.execute('ANALYZE hex_work')
                # Assign line segments on a shared grid edge only to the lower ID.
                cur.execute('''UPDATE hex_work a SET excluded_boundary=coalesce((
                    SELECT ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(
                    ST_Intersection(ST_Boundary(a.geom),ST_Boundary(b.geom)))),2))
                    FROM hex_work b WHERE b.id<a.id AND b.geom && a.geom AND ST_Intersects(a.geom,b.geom)),
                    ST_GeomFromText('MULTILINESTRING EMPTY',2180))''')
                cur.execute(sql.SQL('DROP VIEW IF EXISTS {}').format(sql.Identifier('viz',name)))
                cur.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(result))
                cur.execute(sql.SQL('CREATE TABLE {} AS SELECT id,h3_index,geom::geometry(MultiPolygon,2180) geom FROM hex_work').format(result))
                cur.execute(sql.SQL('ALTER TABLE {} ADD PRIMARY KEY(id), ADD UNIQUE(h3_index), ALTER COLUMN geom SET NOT NULL').format(result))
                for layer, column, dimension in layers:
                    # Clip to the AOI once before grid overlay. This avoids numerical
                    # edge slivers admitting a source line that is outside the AOI.
                    cur.execute(sql.SQL('''CREATE TEMP TABLE bdot_work ON COMMIT DROP AS
                        SELECT b.feature_id,ST_Multi(ST_CollectionExtract(ST_Intersection(b.geom,a.geom),%s)) geom
                        FROM {} b CROSS JOIN grid.powiat a
                        WHERE b.geom && a.geom AND ST_Intersects(b.geom,a.geom)''').format(
                            sql.Identifier('bdot',layer)),(dimension,))
                    cur.execute('DELETE FROM bdot_work WHERE ST_IsEmpty(geom)')
                    cur.execute('CREATE INDEX ON bdot_work USING gist(geom)')
                    cur.execute('ANALYZE bdot_work')
                    typ = sql.SQL('bigint') if dimension == 1 else sql.SQL('double precision')
                    cur.execute(sql.SQL('ALTER TABLE {} ADD COLUMN {} {} NOT NULL DEFAULT 0 CHECK ({}>=0)').format(
                        result,sql.Identifier(column),typ,sql.Identifier(column)))
                    query = metric_query(sql.Identifier('bdot_work'),column,dimension)
                    cur.execute(sql.SQL('UPDATE {} r SET {}=coalesce(m.value,0) FROM ({}) m WHERE r.id=m.id').format(
                        result,sql.Identifier(column),query))
                    cur.execute(sql.SQL('SELECT coalesce(sum({}),0) FROM {}').format(sql.Identifier(column),result))
                    actual = float(cur.fetchone()[0])
                    if dimension == 1:
                        expected_sql = sql.SQL('SELECT count(*) FROM bdot_work b CROSS JOIN LATERAL ST_DumpPoints(b.geom) p')
                    else:
                        fn = sql.SQL('ST_Area') if dimension == 3 else sql.SQL('ST_Length')
                        expected_sql = sql.SQL('SELECT coalesce(sum({}(geom)),0) FROM bdot_work').format(fn)
                    cur.execute(expected_sql)
                    expected = float(cur.fetchone()[0])
                    error = abs(actual-expected)
                    tolerance = 0 if dimension == 1 else max(0.01,abs(expected)*1e-7)
                    if error > tolerance:
                        raise ValueError(f'Conservation failed {name}/{column}: expected={expected},actual={actual},error={error}')
                    cur.execute('''INSERT INTO analysis.validation VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT(resolution,layer_name) DO UPDATE SET expected=excluded.expected,
                        actual=excluded.actual,absolute_error=excluded.absolute_error''',
                                (resolution,layer,expected,actual,error))
                    log(f'{name}.{column}: {actual:.3f}; conservation error={error:.8f}')
                    cur.execute('DROP TABLE bdot_work')
                cur.execute(sql.SQL('CREATE INDEX ON {} USING gist(geom)').format(result))
                cur.execute(sql.SQL('ANALYZE {}').format(result))
                columns = sql.SQL(',').join(sql.Identifier(x[1]) for x in layers)
                cur.execute(sql.SQL('''CREATE VIEW {} AS SELECT id,h3_index,{},
                    ST_Transform(geom,3857)::geometry(MultiPolygon,3857) geom FROM {}''').format(
                        sql.Identifier('viz',name),columns,result))
                cur.execute('DROP TABLE hex_work')
    log('COMMITTED: analysis.h3_7/8/9 EPSG:2180; viz.h3_7/8/9 EPSG:3857')


if __name__ == '__main__':
    main()
