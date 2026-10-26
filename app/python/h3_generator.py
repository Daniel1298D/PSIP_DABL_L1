"""Generate full H3 cells intersecting a county and their clipped geometries."""

import argparse
import json
from pathlib import Path

import h3
from osgeo import gdal, ogr, osr
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union

DEFAULT_RESOLUTIONS = (6, 7, 8, 9)


def parse_resolutions(value):
    try:
        resolutions = tuple(sorted(set(int(x.strip()) for x in value.split(','))))
    except ValueError as exc:
        raise ValueError('Resolutions must be comma-separated integers') from exc
    if not resolutions or any(r < 0 or r > 10 for r in resolutions):
        raise ValueError('Use resolutions 0..10; higher values need a resource review')
    return resolutions


def read_county(path):
    gdal.UseExceptions()
    ogr.UseExceptions()
    dataset = ogr.Open(str(path))
    if dataset is None:
        raise ValueError(f'Cannot open county dataset: {path}')
    layer = dataset.GetLayer(0)
    source_crs = layer.GetSpatialRef()
    if source_crs is None:
        raise ValueError('Dataset CRS is missing; supply the .prj file')
    source_crs = source_crs.Clone()
    source_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target_crs = osr.SpatialReference()
    target_crs.ImportFromEPSG(4326)
    target_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source_crs, target_crs)
    polygons = []
    for feature in layer:
        raw = feature.GetGeometryRef()
        if raw is None:
            raise ValueError('County feature has no geometry')
        geometry = raw.Clone()
        geometry.Transform(transform)
        polygon = shape(json.loads(geometry.ExportToJson()))
        if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in ('Polygon', 'MultiPolygon'):
            raise ValueError('County must be a valid, non-empty Polygon/MultiPolygon')
        polygons.append(polygon)
    if not polygons:
        raise ValueError('County dataset is empty')
    county = unary_union(polygons)
    minx, miny, maxx, maxy = county.bounds
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise ValueError('Invalid WGS84 coordinate bounds')
    return county


def polygon_parts(geometry):
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > 0 else []
    if hasattr(geometry, 'geoms'):
        return [part for child in geometry.geoms for part in polygon_parts(child)]
    return []


def generate_grid(county, resolutions=DEFAULT_RESOLUTIONS):
    """Yield (resolution, H3 id, full polygon, clipped multipolygon).

    Overlap mode includes boundary cells even with centers outside the county.
    GeoJSON uses longitude/latitude; H3 boundaries use latitude/longitude.
    """
    h3_shape = h3.geo_to_h3shape(mapping(county))
    for resolution in resolutions:
        cells = sorted(h3.h3shape_to_cells_experimental(h3_shape, resolution, contain='overlap'))
        if not cells:
            raise ValueError(f'No cells generated for resolution {resolution}')
        for cell in cells:
            full = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])
            clipped_parts = polygon_parts(full.intersection(county))
            if clipped_parts:
                yield resolution, cell, full, MultiPolygon(clipped_parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('/data/powiat.shp'))
    parser.add_argument('--resolutions', default='6,7,8,9')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    county = read_county(args.input)
    features = []
    for resolution, cell, full, clipped in generate_grid(county, parse_resolutions(args.resolutions)):
        features.append({'type': 'Feature', 'properties': {'h3_index': cell, 'resolution': resolution},
                         'geometry': mapping(clipped)})
    args.output.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}), encoding='utf-8')
    print(f'Wrote {len(features)} clipped cells to {args.output}')


if __name__ == '__main__':
    main()
