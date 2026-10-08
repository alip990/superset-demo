"""Idempotent isolated fixture. Never points at the production deployment."""
import json
import os
from superset.app import create_app

app = create_app()
with app.app_context():
    from superset import db, security_manager
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
    from superset.connectors.sqla.models import SqlaTable
    admin = security_manager.find_user(username='lab-admin')
    if not admin:
        admin = security_manager.add_user('lab-admin', 'Lab', 'Admin', 'lab@example.invalid',
            security_manager.find_role('Admin'), os.environ['LAB_ADMIN_PASSWORD'])
    database = db.session.query(Database).filter_by(database_name='Calendar acceptance').one_or_none()
    if not database:
        database = Database(database_name='Calendar acceptance',
            sqlalchemy_uri='postgresql+psycopg2://lab:lab-only@db:5432/lab', expose_in_sqllab=True)
        db.session.add(database)
        db.session.flush()
    dataset = db.session.query(SqlaTable).filter_by(table_name='calendar_events', database_id=database.id).one_or_none()
    if not dataset:
        dataset = SqlaTable(table_name='calendar_events', schema='public', database=database,
                            main_dttm_col='occurred_at')
        db.session.add(dataset)
        db.session.flush()
        dataset.fetch_metadata()
    chart = db.session.query(Slice).filter_by(slice_name='Calendar boundary sum').one_or_none()
    if not chart:
        chart = Slice(slice_name='Calendar boundary sum', datasource_id=dataset.id,
                      datasource_type='table', viz_type='table', owners=[admin])
        db.session.add(chart)
        db.session.flush()
    chart.params = json.dumps({'viz_type': 'table', 'datasource': f'{dataset.id}__table',
        'slice_id': chart.id, 'granularity_sqla': 'occurred_at', 'time_range': 'No filter',
        'query_mode': 'aggregate', 'groupby': [], 'all_columns': [],
        'metrics': [{'expressionType': 'SQL', 'sqlExpression': 'SUM(amount)',
                     'label': 'total', 'optionName': 'metric_total'}],
        'adhoc_filters': [], 'row_limit': 1000, 'server_page_length': 10,
        'order_desc': True})
    dashboard = db.session.query(Dashboard).filter_by(slug='jalali-acceptance').one_or_none()
    if not dashboard:
        dashboard = Dashboard(dashboard_title='Jalali acceptance', slug='jalali-acceptance',
                              published=True, owners=[admin])
        db.session.add(dashboard)
    dashboard.slices = [chart]
    dashboard.position_json = json.dumps({
        'DASHBOARD_VERSION_KEY': 'v2',
        'ROOT_ID': {'id': 'ROOT_ID', 'type': 'ROOT', 'children': ['GRID_ID']},
        'GRID_ID': {'id': 'GRID_ID', 'type': 'GRID', 'children': ['ROW-1'], 'parents': ['ROOT_ID']},
        'HEADER_ID': {'id': 'HEADER_ID', 'type': 'HEADER', 'meta': {'text': 'Jalali acceptance'}},
        'ROW-1': {'id': 'ROW-1', 'type': 'ROW', 'children': ['CHART-1'],
                  'parents': ['ROOT_ID', 'GRID_ID'], 'meta': {'background': 'BACKGROUND_TRANSPARENT'}},
        'CHART-1': {'id': 'CHART-1', 'type': 'CHART', 'children': [],
                    'parents': ['ROOT_ID', 'GRID_ID', 'ROW-1'],
                    'meta': {'chartId': chart.id, 'width': 12, 'height': 50,
                             'sliceName': chart.slice_name}},
    })
    dashboard.json_metadata = json.dumps({'native_filter_configuration': [{
        'id': 'NATIVE_FILTER-calendar', 'name': 'Calendar range', 'filterType': 'filter_time',
        'targets': [{}], 'defaultDataMask': {'extraFormData': {}, 'filterState': {'value': 'No filter'}},
        'controlValues': {}, 'cascadeParentIds': [],
        'scope': {'rootPath': ['ROOT_ID'], 'excluded': []}, 'type': 'NATIVE_FILTER',
    }]})
    db.session.commit()
    print(json.dumps({'dashboard_id': dashboard.id, 'chart_id': chart.id, 'dataset_id': dataset.id}))
