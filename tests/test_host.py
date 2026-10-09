import importlib.util
from pathlib import Path
from datetime import timedelta
from superset_jalali_sql import parse_jalali,j2g

spec=importlib.util.spec_from_file_location('host',Path(__file__).parents[1]/'embed-app/app.py')
host=importlib.util.module_from_spec(spec); spec.loader.exec_module(host)

def test_range_validation():
    with host.app.test_client() as client:
        assert client.post('/range',json={'from':'۱۴۰۳/۰۷/۰۱','to':'1403/07/30'}).json['range_gregorian']=={'from':'2024-09-22','to':'2024-10-21','end_exclusive':'2024-10-22'}
        for body in ({'from':'1404/12/30','to':'1405/01/01'},{'from':'1403/07/30','to':'1403/07/01'},{'from':"1403/07/01' OR TRUE",'to':'1403/07/30'},[],{'to':'1403/07/30'}):
            assert client.post('/range',json=body).status_code==400
        with client.session_transaction() as s: assert s['range']['from']=='1403/07/01'
        assert client.post('/login',json={'user':'unknown'}).status_code==400
        assert client.post('/range',json={}).json['range_gregorian'] is None

def test_presets():
    with host.app.test_client() as client:
        rows=client.get('/jalali/presets').json
        assert len(rows)==7
        for row in rows:
            assert j2g(*parse_jalali(row['from'])) <= j2g(*parse_jalali(row['to']))
        assert j2g(*parse_jalali(rows[1]['from'])).weekday()==5
