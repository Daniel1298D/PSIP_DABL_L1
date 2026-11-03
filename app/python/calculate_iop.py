"""Normalize every BDOT criterion by its maximum and compute the requested IOP."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from psycopg import sql
from python.bdot_common import connect, log

DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / 'config' / 'iop_weights.json'


def load_weights(path):
    content = Path(path).read_bytes()
    config = json.loads(content)
    criteria = {}
    for group in config['criteria']:
        weight = group['weight']
        if isinstance(weight, bool) or not isinstance(weight, (float, int)) or not math.isfinite(weight) or not -1 <= weight <= 1:
            raise ValueError(f'Invalid weight: {weight}')
        for column in group['columns']:
            if column in criteria:
                raise ValueError(f'Duplicate criterion: {column}')
            criteria[column] = dict(group, weight=float(weight))
    if not criteria:
        raise ValueError('No criteria configured')
    return config, criteria, hashlib.sha256(content).hexdigest()


def create_result(cur, source, target, criteria):
    """Create an ordered result table, preserving raw metrics and geometries."""
    if not criteria:
        raise ValueError('No criteria supplied')
    checks = [sql.SQL('count(*)')]
    for column, info in criteria.items():
        if not math.isfinite(info['weight']) or not -1 <= info['weight'] <= 1:
            raise ValueError(f'Invalid weight: {column}')
        c = sql.Identifier(column)
        checks.extend([
            sql.SQL('coalesce(max({}),0)::double precision').format(c),
            sql.SQL('count(*) FILTER (WHERE {}>0)').format(c),
            sql.SQL("count(*) FILTER (WHERE {} IS NULL OR {}<0 OR NOT ({}<'Infinity'::double precision))").format(c, c, c),
        ])
    cur.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(checks), source))
    stats = cur.fetchone()
    if stats[0] == 0:
        raise ValueError('Empty source grid')
    normalization = {}
    expressions = [sql.SQL('s.id'), sql.SQL('s.h3_index')]
    ordered_columns = [sql.Identifier('id'), sql.Identifier('h3_index')]
    terms = []
    for i, (column, info) in enumerate(criteria.items()):
        maximum, nonzero, invalid = stats[1 + 3 * i:4 + 3 * i]
        if invalid:
            raise ValueError(f'Invalid source metric {column}: {invalid} rows')
        normalization[column] = (maximum, nonzero)
        norm = column + '_norm'
        weight = column + '_waga'
        c, n, w = map(sql.Identifier, (column, norm, weight))
        normalizer = sql.SQL('s.{}::double precision / {}::double precision').format(c, sql.Literal(maximum)) if maximum else sql.SQL('0::double precision')
        expressions.extend([sql.SQL('s.{}').format(c), sql.SQL('{} AS {}').format(normalizer, n),
                            sql.SQL('{}::double precision AS {}').format(sql.Literal(info['weight']), w)])
        ordered_columns.extend([c, n, w])
        terms.append(sql.SQL('{} * {}').format(n, w))
    score = sql.SQL('({}) / {}::double precision AS iop').format(sql.SQL(' + ').join(terms), sql.Literal(len(criteria)))
    cur.execute(sql.SQL('''CREATE TABLE {} AS SELECT {},{},geom FROM
        (SELECT {},s.geom FROM {} s) normalized''').format(
        target, sql.SQL(',').join(ordered_columns), score, sql.SQL(',').join(expressions), source))
    changes = [sql.SQL('ADD PRIMARY KEY(id)'), sql.SQL('ADD UNIQUE(h3_index)'),
               sql.SQL('ALTER COLUMN h3_index SET NOT NULL'), sql.SQL('ALTER COLUMN geom SET NOT NULL'),
               sql.SQL('ALTER COLUMN iop SET NOT NULL'), sql.SQL('ADD CHECK (iop BETWEEN -1 AND 1)')]
    for column in criteria:
        for name, lower, upper in ((column + '_norm', 0, 1), (column + '_waga', -1, 1)):
            c = sql.Identifier(name)
            changes.extend([sql.SQL('ALTER COLUMN {} SET NOT NULL').format(c),
                            sql.SQL('ADD CHECK ({} BETWEEN {} AND {})').format(c, sql.Literal(lower), sql.Literal(upper))])
        changes.append(sql.SQL('ALTER COLUMN {} SET NOT NULL').format(sql.Identifier(column)))
    cur.execute(sql.SQL('ALTER TABLE {} {}').format(target, sql.SQL(',').join(changes)))
    cur.execute(sql.SQL('CREATE INDEX ON {} USING gist(geom)').format(target))
    return stats[0], normalization


def main(weights_path=DEFAULT_WEIGHTS):
    config, weights, config_sha = load_weights(weights_path)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            # Same lock order as the existing importer/aggregator.
            cur.execute('SELECT pg_advisory_xact_lock(72480123)')
            cur.execute('SELECT pg_advisory_xact_lock(72480124)')
            cur.execute('SELECT layer_name,metric_column,dimension FROM bdot.layer_catalog ORDER BY layer_name')
            layers = cur.fetchall()
            columns = [row[1] for row in layers]
            if not columns or set(columns) != set(weights):
                raise ValueError(f'Weight/catalog mismatch: missing={set(columns)-set(weights)}, extra={set(weights)-set(columns)}')
            criteria = {column: weights[column] for column in columns}
            cur.execute('''CREATE TABLE IF NOT EXISTS analysis.iop_criteria (
                metric_column text PRIMARY KEY,layer_name text NOT NULL,dimension integer NOT NULL,
                label text NOT NULL,weight double precision NOT NULL CHECK (weight BETWEEN -1 AND 1),
                rationale text NOT NULL)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS analysis.iop_normalization (
                resolution integer,metric_column text,maximum double precision NOT NULL,
                nonzero_rows bigint NOT NULL,PRIMARY KEY(resolution,metric_column))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS analysis.iop_metadata (
                resolution integer PRIMARY KEY,calculated_at timestamptz NOT NULL,
                model text NOT NULL,criteria_count integer NOT NULL,row_count bigint NOT NULL,
                config_sha256 text NOT NULL,source_fingerprint text NOT NULL)''')
            cur.execute('DELETE FROM analysis.iop_criteria')
            for layer, column, dimension in layers:
                info = criteria[column]
                cur.execute('INSERT INTO analysis.iop_criteria VALUES(%s,%s,%s,%s,%s,%s)',
                            (column, layer, dimension, info['label'], info['weight'], info['reason']))
            cur.execute('DELETE FROM analysis.iop_normalization')
            for resolution in (7, 8, 9):
                name = f'iop_h3_{resolution}'
                source = sql.Identifier('analysis', f'h3_{resolution}')
                target = sql.Identifier('analysis', name)
                cur.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(source))
                cur.execute(sql.SQL('DROP VIEW IF EXISTS {}').format(sql.Identifier('viz', name)))
                cur.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(target))
                count, normalization = create_result(cur, source, target, criteria)
                for column, (maximum, nonzero) in normalization.items():
                    cur.execute('INSERT INTO analysis.iop_normalization VALUES(%s,%s,%s,%s)',
                                (resolution, column, maximum, nonzero))
                cur.execute(sql.SQL("SELECT md5(string_agg(md5(s::text),'' ORDER BY id)) FROM {} s").format(source))
                fingerprint = cur.fetchone()[0]
                cur.execute('''INSERT INTO analysis.iop_metadata VALUES(%s,transaction_timestamp(),%s,%s,%s,%s,%s)
                    ON CONFLICT(resolution) DO UPDATE SET calculated_at=excluded.calculated_at,
                    model=excluded.model,criteria_count=excluded.criteria_count,row_count=excluded.row_count,
                    config_sha256=excluded.config_sha256,source_fingerprint=excluded.source_fingerprint''',
                            (resolution, config['model'], len(criteria), count, config_sha, fingerprint))
                fields = [sql.Identifier('id'), sql.Identifier('h3_index')]
                for column in criteria:
                    fields.extend(sql.Identifier(x) for x in (column, column + '_norm', column + '_waga'))
                fields.append(sql.Identifier('iop'))
                cur.execute(sql.SQL('''CREATE VIEW {} AS SELECT {},
                    ST_Transform(geom,3857)::geometry(MultiPolygon,3857) geom FROM {}''').format(
                    sql.Identifier('viz', name), sql.SQL(',').join(fields), target))
                comment = f'IOP=sum(metric/max(metric)*weight)/{len(criteria)}; per-resolution maxima; all-zero criterion=0; model={config["model"]}'
                cur.execute(sql.SQL('COMMENT ON TABLE {} IS {}').format(target, sql.Literal(comment)))
                cur.execute(sql.SQL('ANALYZE {}').format(target))
                log(f'{name}: {count} cells, {len(criteria)} criteria, EPSG:2180')
            # Validation runs before commit; any failure rolls back all three results.
            from python.validate_iop import validate_cursor
            report = validate_cursor(cur)
    log('COMMITTED: IOP tables and PostgreSQL visualization views')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = main(args.weights)
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.write_text(text, encoding='utf-8')
    print(text)
