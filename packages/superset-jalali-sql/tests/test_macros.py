import pytest
import sqlglot
from flask import Flask
from superset_jalali_sql.macros import *

def test_sql_parses():
    for digits in ('latin','persian'):
        sql = f"SELECT s.*, {jalali_columns('s.sale_date',digits=digits)} FROM sales s {jalali_join('s.sale_date')}"
        assert sqlglot.parse_one(sql, read='postgres')
    assert jalali_to_gregorian('1403/07/01') == "DATE '2024-09-22'"

@pytest.mark.parametrize('bad', ['sale_date;drop table sales', 'a--', 'x()', 'a b', 'a.*', 'a..b'])
def test_identifiers(bad):
    with pytest.raises(ValueError): jalali_join(bad)
    with pytest.raises(ValueError): jalali_columns('d',alias=bad)

def test_config_and_nulls():
    app=Flask(__name__); app.config['JALALI_SQL']={'min_year':1403,'max_year':1404,'digits':'persian'}
    with app.app_context():
        assert '1350' not in jalali_join('d')
        assert 'TRANSLATE' in jalali_columns('d')
    assert jalali_columns('d').count('CASE WHEN _jy.jy IS NULL') == 13
    with pytest.raises(ValueError): jalali_columns('d',prefix='x;')
    with pytest.raises(ValueError): jalali_columns('d',digits='arabic')
