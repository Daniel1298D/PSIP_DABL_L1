"""Load county and H3 grids atomically into the selected PostGIS database."""

import json
import os
from pathlib import Path

import psycopg
from shapely.geometry import MultiPolygon, Polygon

from python.h3_generator import generate_grid, parse_resolutions, read_county, project_geometry


def main():
    source = Path(os.getenv('SHAPEFILE_PATH', '/data/powiat.shp'))
    resolutions = parse_resolutions(os.getenv('H3_RESOLUTIONS', '6,7,8,9'))
    county = read_county(source)
    metric_county = project_geometry(county)
    county_multi = MultiPolygon([metric_county]) if isinstance(metric_county, Polygon) else metric_county
    rows = list(generate_grid(county, resolutions, output_epsg=2180))
    for name in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB'):
        if not os.getenv(name):
            raise ValueError(f'Required environment variable is empty: {name}')
    with psycopg.connect(host=os.getenv('PGHOST', 'postgis'),
                         port=int(os.getenv('PGPORT', '5432')),
                         user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
                         dbname=os.environ['POSTGRES_DB'], connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(72480123)')
            cursor.execute('CREATE SCHEMA IF NOT EXISTS grid')
            cursor.execute('''CREATE TABLE IF NOT EXISTS grid.powiat (
                id integer PRIMARY KEY CHECK (id = 1), source_name text NOT NULL,
                geom geometry(MultiPolygon,2180) NOT NULL)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS grid.h3_cells (
                resolution smallint NOT NULL CHECK (resolution BETWEEN 0 AND 15),
                h3_index text NOT NULL,
                geom geometry(Polygon,2180) NOT NULL,
                geom_clipped geometry(MultiPolygon,2180) NOT NULL,
                area_m2 double precision NOT NULL CHECK (area_m2 > 0),
                PRIMARY KEY (resolution,h3_index))''')
            cursor.execute("SELECT Find_SRID('grid','powiat','geom')")
            if cursor.fetchone()[0] != 2180:
                cursor.execute('ALTER TABLE grid.powiat ALTER COLUMN geom TYPE geometry(MultiPolygon,2180) USING ST_Transform(geom,2180)')
                cursor.execute('ALTER TABLE grid.h3_cells ALTER COLUMN geom TYPE geometry(Polygon,2180) USING ST_Transform(geom,2180)')
                cursor.execute('ALTER TABLE grid.h3_cells ALTER COLUMN geom_clipped TYPE geometry(MultiPolygon,2180) USING ST_Transform(geom_clipped,2180)')
            cursor.execute('CREATE INDEX IF NOT EXISTS h3_cells_geom_idx ON grid.h3_cells USING gist(geom)')
            cursor.execute('CREATE INDEX IF NOT EXISTS h3_cells_clipped_idx ON grid.h3_cells USING gist(geom_clipped)')
            cursor.execute('''INSERT INTO grid.powiat VALUES (1,%s,ST_GeomFromText(%s,2180))
                ON CONFLICT(id) DO UPDATE SET source_name=excluded.source_name,geom=excluded.geom''',
                           (source.name, county_multi.wkt))
            # Replace only our generated grid. Any failure rolls back the entire load.
            cursor.execute('DELETE FROM grid.h3_cells')
            with cursor.copy('COPY grid.h3_cells (resolution,h3_index,geom,geom_clipped,area_m2) FROM STDIN') as copy:
                for resolution, cell, full, clipped in rows:
                    copy.write_row((resolution, cell, 'SRID=2180;' + full.wkt,
                                    'SRID=2180;' + clipped.wkt, 1.0))
            cursor.execute('UPDATE grid.h3_cells SET area_m2=ST_Area(geom_clipped)')
            cursor.execute('''SELECT count(*) FROM grid.h3_cells
                WHERE NOT ST_IsValid(geom) OR NOT ST_IsValid(geom_clipped)
                OR ST_IsEmpty(geom_clipped) OR ST_SRID(geom_clipped)<>2180''')
            if cursor.fetchone()[0]:
                raise ValueError('Invalid grid geometry; transaction rolled back')
            cursor.execute('''SELECT resolution,count(*),round(sum(area_m2)::numeric,2)
                FROM grid.h3_cells GROUP BY resolution ORDER BY resolution''')
            summary = cursor.fetchall()
            if {row[0] for row in summary} != set(resolutions):
                raise ValueError('A requested resolution is empty')
            cursor.execute('''WITH aoi AS (SELECT geom FROM grid.powiat),
                coverage AS (SELECT resolution,ST_UnaryUnion(ST_Collect(geom_clipped)) geom
                FROM grid.h3_cells GROUP BY resolution)
                SELECT resolution,ST_Area(ST_SymDifference(coverage.geom,aoi.geom))/ST_Area(aoi.geom)
                FROM coverage CROSS JOIN aoi''')
            for resolution, error in cursor.fetchall():
                if error > 0.00001:
                    raise ValueError(f'Coverage mismatch at resolution {resolution}: {error:.8f}')
        print(json.dumps({'resolutions': [{'resolution': r, 'cells': n, 'area_m2': float(a)}
                                         for r,n,a in summary]}))
    print('Committed county and H3 grids to schema grid.')


if __name__ == '__main__':
    main()
