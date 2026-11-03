"""Read-only checks of normalization, weights, IOP, source preservation and CRS."""
import argparse
import json
from pathlib import Path

from psycopg import sql
from python.bdot_common import connect


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_cursor(cur):
    cur.execute('SELECT metric_column,weight FROM analysis.iop_criteria ORDER BY metric_column')
    criteria = cur.fetchall()
    require(bool(criteria), 'Missing criteria')
    count_criteria = len(criteria)
    cur.execute('SELECT metric_column FROM bdot.layer_catalog ORDER BY metric_column')
    require([x[0] for x in criteria] == [x[0] for x in cur.fetchall()], 'Incomplete class coverage')
    cur.execute('SELECT metric_column FROM bdot.layer_catalog ORDER BY layer_name')
    column_order = [x[0] for x in cur.fetchall()]
    report = {'environment': 'env-test', 'normalization': 'value / maximum_per_layer_and_resolution',
              'iop_formula': 'sum(normalized_value * weight) / number_of_all_criteria',
              'criteria_count': count_criteria, 'processing_epsg': 2180, 'visualization_epsg': 3857,
              'results': []}
    for resolution in (7, 8, 9):
        table_name = f'iop_h3_{resolution}'
        source = sql.Identifier('analysis', f'h3_{resolution}')
        result = sql.Identifier('analysis', table_name)
        cur.execute(sql.SQL('SELECT count(*),count(DISTINCT id),count(DISTINCT h3_index),min(iop),max(iop) FROM {}').format(result))
        rows, ids, h3ids, min_score, max_score = cur.fetchone()
        cur.execute(sql.SQL('SELECT count(*) FROM {}').format(source))
        require(rows == ids == h3ids == cur.fetchone()[0] and rows > 0, f'Grid IDs/count: {table_name}')
        raw = [sql.Identifier(x) for x in ['h3_index'] + column_order]
        original = sql.SQL(',').join(sql.SQL('s.{}').format(c) for c in raw)
        copied = sql.SQL(',').join(sql.SQL('r.{}').format(c) for c in raw)
        cur.execute(sql.SQL('''SELECT count(*) FROM {} s FULL JOIN {} r USING(id)
            WHERE s.id IS NULL OR r.id IS NULL OR ROW({}) IS DISTINCT FROM ROW({})
            OR ST_AsEWKB(s.geom) IS DISTINCT FROM ST_AsEWKB(r.geom)''').format(source, result, original, copied))
        require(cur.fetchone()[0] == 0, f'Source changed or copy differs: {table_name}')
        cur.execute(sql.SQL("SELECT md5(string_agg(md5(s::text),'' ORDER BY id)) FROM {} s").format(source))
        fingerprint = cur.fetchone()[0]
        cur.execute('SELECT row_count,criteria_count,source_fingerprint,calculated_at,config_sha256 FROM analysis.iop_metadata WHERE resolution=%s', (resolution,))
        metadata = cur.fetchone()
        require(metadata is not None and metadata[:3] == (rows, count_criteria, fingerprint), f'Stale source: {table_name}')
        zero_layers = []
        positive_maxima = 0
        for column, weight in criteria:
            c, n, w = map(sql.Identifier, (column, column + '_norm', column + '_waga'))
            cur.execute(sql.SQL('SELECT coalesce(max({}),0)::double precision,count(*) FILTER(WHERE {}>0) FROM {}').format(c, c, source))
            maximum, nonzero = cur.fetchone()
            cur.execute('SELECT maximum,nonzero_rows FROM analysis.iop_normalization WHERE resolution=%s AND metric_column=%s', (resolution, column))
            require(cur.fetchone() == (maximum, nonzero), f'Maximum mismatch: {table_name}.{column}')
            cur.execute(sql.SQL('''SELECT count(*) FILTER(WHERE {} IS NULL OR NOT ({} BETWEEN 0 AND 1)),
                count(*) FILTER(WHERE {} IS NULL OR {} IS DISTINCT FROM %s::double precision),max({}) FROM {}''').format(n, n, w, w, n, result), (weight,))
            bad_normalized, bad_weights, max_norm = cur.fetchone()
            require(bad_normalized == bad_weights == 0, f'Invalid values: {table_name}.{column}')
            require(max_norm == (1.0 if maximum > 0 else 0.0), f'Maximum must map to 1 or empty to 0: {column}')
            if maximum > 0:
                positive_maxima += 1
            else:
                zero_layers.append(column)
            cur.execute(sql.SQL('''SELECT count(*) FROM {} r JOIN {} s USING(id)
                WHERE abs(r.{} - coalesce(s.{}::double precision / nullif(%s,0),0))>1e-12''').format(result, source, n, c), (maximum,))
            require(cur.fetchone()[0] == 0, f'Normalization formula mismatch: {table_name}.{column}')
        # Independent row-wise SUM over a VALUES relation, using all configured criteria.
        pairs = sql.SQL(',').join(sql.SQL('(r.{},r.{})').format(
            sql.Identifier(c + '_norm'), sql.Identifier(c + '_waga')) for c, _ in criteria)
        cur.execute(sql.SQL('''SELECT coalesce(max(abs(r.iop - expected.value)),0),
            count(*) FILTER(WHERE r.iop IS NULL OR NOT (r.iop BETWEEN -1 AND 1)) FROM {} r
            CROSS JOIN LATERAL (SELECT sum(n*w)/%s::double precision value FROM (VALUES {}) v(n,w)) expected''').format(result, pairs), (count_criteria,))
        error, bad_scores = cur.fetchone()
        require(error <= 1e-12 and bad_scores == 0, f'IOP formula/range: {table_name}')
        cur.execute(sql.SQL('SELECT count(*) FROM {} WHERE geom IS NULL OR ST_SRID(geom)<>2180 OR NOT ST_IsValid(geom)').format(result))
        require(cur.fetchone()[0] == 0, f'Processing geometry: {table_name}')
        cur.execute(sql.SQL('SELECT count(*),count(*) FILTER(WHERE ST_SRID(geom)<>3857 OR NOT ST_IsValid(geom)) FROM {}').format(sql.Identifier('viz', table_name)))
        require(cur.fetchone() == (rows, 0), f'Visualization geometry: {table_name}')
        cur.execute('''SELECT column_name FROM information_schema.columns
            WHERE table_schema='analysis' AND table_name=%s ORDER BY ordinal_position''', (table_name,))
        expected_order = ['id', 'h3_index']
        for column in column_order:
            expected_order.extend([column, column + '_norm', column + '_waga'])
        expected_order.extend(['iop', 'geom'])
        require([x[0] for x in cur.fetchall()] == expected_order, f'Non-adjacent columns: {table_name}')
        cur.execute('''SELECT column_name FROM information_schema.columns
            WHERE table_schema='viz' AND table_name=%s ORDER BY ordinal_position''', (table_name,))
        require([x[0] for x in cur.fetchall()] == expected_order, f'View column order: {table_name}')
        report['results'].append({'resolution': resolution, 'table': f'analysis.{table_name}',
            'rows': rows, 'normalized_columns': count_criteria, 'weight_columns': count_criteria,
            'positive_maxima_mapped_to_one': positive_maxima, 'all_zero_criteria': zero_layers,
            'iop_min': min_score, 'iop_max': max_score, 'max_iop_recalculation_error': error,
            'null_or_out_of_range_values': 0, 'raw_metrics_and_geometries_match_source': True,
            'adjacent_columns': True, 'calculated_at': metadata[3], 'config_sha256': metadata[4]})
    return report


def validate():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            return validate_cursor(cur)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(validate(), ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
