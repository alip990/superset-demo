"""Compare embedded guest queries with read-only business SQL, including map aggregation."""
import os
import json
import requests
import psycopg2

HOST=os.environ.get('HOST_URL','http://embed-app:8090')
SS=os.environ.get('SUPERSET_URL','http://superset:8088')
DSN=os.environ.get('DEMO_DSN','postgresql://demo_reader:demo_reader@db:5432/demo')

def checked(response):
    response.raise_for_status()
    return response.json()

def run():
    admin=requests.Session()
    token=checked(admin.post(SS+'/api/v1/security/login',json={'username':'admin','password':'admin','provider':'db'},timeout=30))['access_token']
    admin.headers['Authorization']='Bearer '+token
    csrf=checked(admin.get(SS+'/api/v1/security/csrf_token/',timeout=30))['result']
    datasets=checked(admin.get(SS+'/api/v1/dataset/',params={'q':json.dumps({'page_size':100})},timeout=30))['result']
    ids={d['table_name']:d['id'] for d in datasets}
    host=requests.Session()
    checked(host.post(HOST+'/login',json={'user':'manager'},timeout=30))
    checked(host.post(HOST+'/range',json={'from':'1403/07/01','to':'1403/07/30'},timeout=30))
    guest=checked(host.get(HOST+'/guest-token',timeout=30))
    assert guest['rls'] == [{'dataset':ids['sales'],'clause':"sale_date >= DATE '2024-09-22' AND sale_date < DATE '2024-10-22'"}]
    def query(name,columns,expr,token):
        body={'datasource':{'id':ids[name],'type':'table'},'force':False,
              'queries':[{'columns':columns,'metrics':[{'expressionType':'SQL','sqlExpression':expr,'label':'total'}],
                          'row_limit':10000,'time_range':'No filter','filters':[],'extras':{'where':'','having':''}}],
              'result_format':'json','result_type':'full'}
        result=checked(requests.post(SS+'/api/v1/chart/data',json=body,headers={'X-GuestToken':token,'X-CSRFToken':csrf,'Referer':SS},timeout=120))['result'][0]
        assert result['status']=='success',result
        return result
    with psycopg2.connect(DSN) as db,db.cursor() as c:
        c.execute("SELECT SUM(amount) FROM sales WHERE sale_date >= DATE '2024-09-22' AND sale_date < DATE '2024-10-22'")
        expected=float(c.fetchone()[0])
        monthly=query('sales_jalali',['jalali_month_label'],'SUM(amount)',guest['token'])
        assert monthly['data']==[{'jalali_month_label':'1403-07 مهر','total':expected}],monthly
        mapped=query('sales_by_branch',[],'SUM(total_amount)',guest['token'])
        assert float(mapped['data'][0]['total'])==expected,mapped
        checked(host.post(HOST+'/login',json={'user':'ali_north'},timeout=30))
        north=checked(host.get(HOST+'/guest-token',timeout=30))
        c.execute("SELECT SUM(amount) FROM sales WHERE region='north' AND sale_date >= DATE '2024-09-22' AND sale_date < DATE '2024-10-22'")
        regional=float(c.fetchone()[0]); assert regional<expected
        assert float(query('sales_jalali',[],'SUM(amount)',north['token'])['data'][0]['total'])==regional
        assert float(query('sales_by_branch',[],'SUM(total_amount)',north['token'])['data'][0]['total'])==regional
        checked(host.post(HOST+'/range',json={'from':'1403/08/01','to':'1403/08/30'},timeout=30))
        other=checked(host.get(HOST+'/guest-token',timeout=30))
        assert query('sales_jalali',['jalali_month_label'],'SUM(amount)',other['token'])['data'][0]['jalali_month_label']=='1403-08 آبان'
    print('SMOKE_OK: monthly, map, region + date RLS, and cached range isolation')

if __name__=='__main__': run()
