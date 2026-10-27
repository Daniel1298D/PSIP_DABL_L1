"""Read-only validation of stored BDOT data, wide result tables and map views."""
import argparse
import json
from pathlib import Path
from psycopg import sql
from python.bdot_common import connect


def validate():
    report={'source':'GUGiK BDOT10K 1465','environment':'env-test','processing_epsg':2180,'visualization_epsg':3857}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT layer_name,metric_column,dimension,source_count FROM bdot.layer_catalog ORDER BY layer_name')
            layers=cur.fetchall()
            assert len(layers)==73, 'Unexpected class inventory for this source snapshot'
            report['classes']=len(layers)
            report['objects']=sum(x[3] for x in layers)
            report['empty_classes']=[x[0] for x in layers if not x[3]]
            for layer,column,dimension,count in layers:
                cur.execute(sql.SQL('''SELECT count(*),count(*) FILTER(WHERE geom IS NULL OR
                    ST_SRID(geom)<>2180 OR NOT ST_IsValid(geom)) FROM {}''').format(sql.Identifier('bdot',layer)))
                assert cur.fetchone()==(count,0), f'Source validation failed: {layer}'
            report['results']=[]
            for resolution in (7,8,9):
                table=sql.Identifier('analysis',f'h3_{resolution}')
                bad=sql.SQL(' OR ').join(sql.SQL('{} IS NULL OR {} < 0').format(sql.Identifier(x[1]),sql.Identifier(x[1])) for x in layers)
                cur.execute(sql.SQL('''SELECT count(*),count(DISTINCT h3_index),
                    count(*) FILTER(WHERE {}),count(*) FILTER(WHERE ST_SRID(geom)<>2180
                    OR NOT ST_IsValid(geom) OR ST_IsEmpty(geom)) FROM {}''').format(bad,table))
                count,distinct,bad_values,bad_geometry=cur.fetchone()
                cur.execute('SELECT count(*) FROM grid.h3_cells WHERE resolution=%s',(resolution,))
                assert count==distinct==cur.fetchone()[0] and bad_values==bad_geometry==0
                cur.execute(sql.SQL('SELECT count(*) FROM {} WHERE ST_SRID(geom)<>3857 OR NOT ST_IsValid(geom)').format(
                    sql.Identifier('viz',f'h3_{resolution}')))
                assert cur.fetchone()[0]==0
                cur.execute('''SELECT count(*),max(absolute_error) FROM analysis.validation
                    WHERE resolution=%s''',(resolution,))
                validations,max_error=cur.fetchone()
                assert validations==len(layers)
                for layer,column,dim,n in layers:
                    cur.execute('SELECT expected,actual,absolute_error FROM analysis.validation WHERE resolution=%s AND layer_name=%s',(resolution,layer))
                    expected,actual,error=cur.fetchone()
                    assert error <= (0 if dim==1 else max(0.01,abs(expected)*1e-7))
                    cur.execute(sql.SQL('SELECT coalesce(sum({}),0) FROM {}').format(sql.Identifier(column),table))
                    assert abs(float(cur.fetchone()[0])-actual)<=max(0.01,abs(actual)*1e-10)
                report['results'].append({'resolution':resolution,'rows':count,'metric_columns':len(layers),
                    'null_or_negative_metrics':bad_values,'invalid_geometries':bad_geometry,'conservation_checks':validations,
                    'max_absolute_error_m_or_m2':max_error})
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=validate()
    content=json.dumps(report,indent=2,ensure_ascii=False)
    if args.output:
        args.output.write_text(content,encoding='utf-8')
    print(content)
