"""Download official Warsaw BDOT10K and atomically import all classes in EPSG:2180."""
import argparse
import hashlib
import json
import re
import urllib.request
import zipfile
from pathlib import Path

from osgeo import gdal, ogr, osr
from psycopg import sql

from python.bdot_common import connect, log

SOURCE_URL = 'https://opendata.geoportal.gov.pl/bdot10k/schemat2021/14/1465_GML.zip'


def download(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix('.download')
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, temporary.open('wb') as output:
            while chunk := response.read(1024*1024):
                output.write(chunk)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip():
                raise ValueError('Downloaded archive failed CRC validation')
        temporary.replace(path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('/cache/1465_GML.zip'))
    args = parser.parse_args()
    path = download(args.archive).resolve()
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    gdal.UseExceptions()
    ogr.UseExceptions()
    gdal.SetConfigOption('GML_SKIP_RESOLVE_ELEMS', 'ALL')
    target = osr.SpatialReference()
    target.ImportFromEPSG(2180)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    with zipfile.ZipFile(path) as archive:
        members = sorted(n for n in archive.namelist()
                         if re.search(r'__OT_[A-Z0-9]+_[ALP]\.xml$', n))
    if not members:
        raise ValueError('No BDOT class files found in archive')
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(72480124)')
            cur.execute('CREATE SCHEMA IF NOT EXISTS bdot')
            cur.execute('''CREATE TABLE IF NOT EXISTS bdot.layer_catalog (
                layer_name text PRIMARY KEY, metric_column text UNIQUE NOT NULL,
                dimension integer NOT NULL, unit text NOT NULL, source_count bigint NOT NULL,
                invalid_repaired bigint NOT NULL, empty_count bigint NOT NULL,
                source_url text NOT NULL, sha256 text NOT NULL, loaded_at timestamptz NOT NULL DEFAULT now())''')
            for member in members:
                name = re.search(r'__(OT_[A-Z0-9]+_[ALP])\.xml$', member).group(1).lower()
                dimension = {'a':3, 'l':2, 'p':1}[name[-1]]
                unit = {3:'m2', 2:'m', 1:'count'}[dimension]
                table = sql.Identifier('bdot', name)
                cur.execute(sql.SQL('''CREATE TABLE IF NOT EXISTS {} (
                    feature_id bigint PRIMARY KEY, source_id text,
                    attributes jsonb NOT NULL, geom geometry(Geometry,2180) NOT NULL)''').format(table))
                cur.execute(sql.SQL('DELETE FROM {}').format(table))
                dataset = ogr.Open(f'/vsizip/{path}/{member}')
                if dataset is None:
                    raise ValueError(f'Cannot parse {member}')
                count = 0
                if dataset.GetLayerCount():
                    layer = dataset.GetLayer(0)
                    source = layer.GetSpatialRef()
                    if source is None:
                        raise ValueError(f'Missing CRS for {name}')
                    source = source.Clone()
                    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
                    transform = osr.CoordinateTransformation(source, target)
                    with cur.copy(sql.SQL('COPY {} (feature_id,source_id,attributes,geom) FROM STDIN').format(table)) as copy:
                        for feature in layer:
                            geometry = feature.GetGeometryRef()
                            if geometry is None:
                                raise ValueError(f'Missing geometry in {name}')
                            geometry = geometry.Clone()
                            geometry.Transform(transform)
                            geometry.FlattenTo2D()
                            attributes = feature.items()
                            count += 1
                            copy.write_row((count, attributes.get('gml_id'),
                                            json.dumps(attributes, ensure_ascii=False, default=str),
                                            'SRID=2180;' + geometry.ExportToWkt()))
                cur.execute(sql.SQL('SELECT count(*) FROM {} WHERE NOT ST_IsValid(geom)').format(table))
                repaired = cur.fetchone()[0]
                cur.execute(sql.SQL('''UPDATE {} SET geom=ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),%s))''').format(table), (dimension,))
                cur.execute(sql.SQL('SELECT count(*) FROM {} WHERE ST_IsEmpty(geom)').format(table))
                empty = cur.fetchone()[0]
                cur.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {} USING gist(geom)').format(
                    sql.Identifier(name+'_geom_idx'), table))
                cur.execute(sql.SQL('ANALYZE {}').format(table))
                cur.execute('''INSERT INTO bdot.layer_catalog
                    (layer_name,metric_column,dimension,unit,source_count,invalid_repaired,empty_count,source_url,sha256)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(layer_name) DO UPDATE SET source_count=excluded.source_count,
                    invalid_repaired=excluded.invalid_repaired,empty_count=excluded.empty_count,
                    sha256=excluded.sha256,loaded_at=now()''',
                            (name,name[3:],dimension,unit,count,repaired,empty,SOURCE_URL,checksum))
                log(f'Imported {name}: {count} objects; repaired={repaired}; empty={empty}')
            cur.execute('SELECT sum(source_count),count(*) FROM bdot.layer_catalog')
            total, layers = cur.fetchone()
    log(f'COMMITTED BDOT: {layers} classes, {total} objects, EPSG:2180, SHA256={checksum}')


if __name__ == '__main__':
    main()
