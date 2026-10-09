import os
from datetime import date,timedelta
import psycopg2
import pytest
from superset_jalali_sql import g2j
from superset_jalali_sql.macros import jalali_columns, jalali_join
from superset_jalali_sql.names import MONTHS, SEASONS, WEEKDAYS

@pytest.mark.integration
def test_all_sql_columns():
    if not os.environ.get('JALALI_TEST_DSN'): pytest.skip('Set JALALI_TEST_DSN to run integration tests')
    with psycopg2.connect(os.environ['JALALI_TEST_DSN']) as db, db.cursor() as c:
        c.execute(f"SELECT d::date, {jalali_columns('d')} FROM generate_series(DATE '1971-03-20', DATE '2172-03-21', INTERVAL '1 day') AS g(d) {jalali_join('d')}")
        for row in c:
            d=row[0]
            try: y,m,day=g2j(d)
            except ValueError:
                assert all(x is None for x in row[1:]); continue
            weekday=(d.weekday()+2)%7; season=(m-1)//3
            assert row[1:] == (y,m,day,f'{y:04}/{m:02}/{day:02}',y*10000+m*100+day,f'{y:04}-{m:02}',MONTHS[m-1],f'{y:04}-{m:02} {MONTHS[m-1]}',SEASONS[season],f'{y}-{season+1} {SEASONS[season]}',WEEKDAYS[weekday],weekday,d-timedelta(days=weekday))
        c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'")
        assert c.fetchone()[0] == 0
        c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='sales' AND column_name LIKE 'jalali_%'")
        assert c.fetchall() == []
        with pytest.raises(psycopg2.errors.InsufficientPrivilege): c.execute('CREATE TABLE public.should_not_exist(id int)')

@pytest.mark.integration
def test_persian_digits_and_null_dates():
    if not os.environ.get('JALALI_TEST_DSN'): pytest.skip('Set JALALI_TEST_DSN to run integration tests')
    with psycopg2.connect(os.environ['JALALI_TEST_DSN']) as db, db.cursor() as c:
        c.execute(f"SELECT {jalali_columns('d',prefix='latin_')}, {jalali_columns('d',prefix='persian_',digits='persian')} FROM (VALUES (DATE '2024-10-09'), (NULL::date)) AS dates(d) {jalali_join('d')} ORDER BY d NULLS LAST")
        latin_and_persian, nulls = c.fetchall()
        latin, persian = latin_and_persian[:13], latin_and_persian[13:]
        translate=str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')
        assert persian == tuple(x.translate(translate) if isinstance(x,str) else x for x in latin)
        assert persian[3] == '۱۴۰۳/۰۷/۱۸'
        assert all(x is None for x in nulls)
