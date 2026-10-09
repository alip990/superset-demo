from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
from .calendar import g2j, j2g, parse_jalali, month_length
from .nowruz import NOWRUZ
from .names import MONTHS, SEASONS, WEEKDAYS
from .dialects import get_dialect

IDENT = r'(?:[A-Za-z_][A-Za-z_0-9]*|"[A-Za-z_][A-Za-z_0-9]*")'

def validate(value, qualified=False):
    pattern = IDENT + (r'(?:\.'+IDENT+r')*' if qualified else '')
    if not isinstance(value,str) or not re.fullmatch(pattern,value):
        raise ValueError("Unsafe SQL identifier")
    return value

def settings():
    cfg = {"dialect":"postgresql", "min_year":1350, "max_year":1550, "digits":"latin"}
    try:
        from flask import current_app, has_app_context
        if has_app_context(): cfg.update(current_app.config.get("JALALI_SQL", {}))
    except ImportError: pass
    if not (type(cfg['min_year']) is int and type(cfg['max_year']) is int and 1350 <= cfg['min_year'] <= cfg['max_year'] <= 1550):
        raise ValueError("Invalid calendar year bounds")
    return cfg, get_dialect(cfg['dialect'])

def jalali_join(col, alias='_jy'):
    validate(col, True); validate(alias)
    cfg, d = settings()
    rows = [(y,NOWRUZ[y],NOWRUZ[y+1]) for y in range(cfg['min_year'],cfg['max_year']+1)]
    return f"LEFT JOIN {d.values_table(rows,alias,('jy','start_date','next_start_date'))} ON {d.date_of(col)} >= {alias}.start_date AND {d.date_of(col)} < {alias}.next_start_date"

def jalali_columns(col, alias='_jy', prefix='jalali_', digits=None):
    validate(col, True); validate(alias)
    if not isinstance(prefix,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*|',prefix): raise ValueError("Unsafe prefix")
    cfg,d = settings(); digits = cfg['digits'] if digits is None else digits
    if digits not in ('latin','persian'): raise ValueError("Invalid digits")
    date = d.date_of(col); year = f'{alias}.jy'; doy = d.days_between(date,f'{alias}.start_date')
    month = f'(CASE WHEN {doy} < 186 THEN {doy} / 31 + 1 ELSE ({doy} - 186) / 30 + 7 END)'
    day = f'(CASE WHEN {doy} < 186 THEN {doy} % 31 + 1 ELSE ({doy} - 186) % 30 + 1 END)'
    season = f'(({month} - 1) / 3 + 1)'; weekday = d.sat_weekday(date)
    def names(expr, items, start=1):
        return '(CASE ' + expr + ' ' + ' '.join(f"WHEN {i} THEN '{name}'" for i,name in enumerate(items,start)) + ' END)'
    mn = names(month, MONTHS); sn = names(season, SEASONS)
    ym = d.concat(d.to_text(year),"'-'",d.lpad2(month))
    exprs = {
        'year':year, 'month_num':month,'day':day,
        'date':d.concat(d.to_text(year),"'/'",d.lpad2(month),"'/'",d.lpad2(day)),
        'date_int':f'({year} * 10000 + {month} * 100 + {day})',
        'month':ym,'month_name':mn,'month_label':d.concat(ym,"' '",mn),
        'season':sn,'season_key':d.concat(d.to_text(year),"'-'",d.to_text(season),"' '",sn),
        'weekday':names(weekday,WEEKDAYS,0),'weekday_num':weekday,
        'week_start':f'({date} - {weekday})'
    }
    numeric = {'year','month_num','day','date_int','weekday_num','week_start'}
    result=[]
    for key,expr in exprs.items():
        if digits == 'persian' and key not in numeric: expr = d.persian_digits(expr)
        # Every output is NULL when the LEFT JOIN did not find a calendar year.
        result.append(f'CASE WHEN {year} IS NULL THEN NULL ELSE {expr} END AS {prefix}{key}')
    return ',\n'.join(result)

def jalali_to_gregorian(value):
    return f"DATE '{j2g(*parse_jalali(value)).isoformat()}'"

def jalali_period_sql(col, kind):
    validate(col, True)
    today = datetime.now(ZoneInfo('Asia/Tehran')).date(); y,m,_ = g2j(today)
    if kind in ('this_month','last_month'):
        if kind == 'last_month': y,m = (y-1,12) if m == 1 else (y,m-1)
        start = j2g(y,m,1); end = start+timedelta(days=month_length(y,m))
    elif kind in ('this_year','last_year','ytd'):
        if kind == 'last_year': y -= 1
        start = j2g(y,1,1)
        end = today+timedelta(days=1) if kind == 'ytd' else j2g(y,12,month_length(y,12))+timedelta(days=1)
    else: raise ValueError('Unknown Jalali period')
    return f"{col} >= DATE '{start}' AND {col} < DATE '{end}'"

JINJA_ADDONS = {name: globals()[name] for name in ('jalali_join','jalali_columns','jalali_to_gregorian','jalali_period_sql')}
