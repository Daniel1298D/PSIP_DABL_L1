"""Shared connection and logging for the test-only BDOT pipeline."""
import os
import psycopg


def connect():
    if os.getenv('TARGET_ENVIRONMENT') != 'env-test':
        raise ValueError('This BDOT pipeline is restricted to TARGET_ENVIRONMENT=env-test')
    return psycopg.connect(host=os.getenv('PGHOST', 'postgis'),
                           port=os.getenv('PGPORT', '5432'),
                           user=os.environ['POSTGRES_USER'],
                           password=os.environ['POSTGRES_PASSWORD'],
                           dbname=os.environ['POSTGRES_DB'], connect_timeout=15)


def log(message):
    print(message, flush=True)
