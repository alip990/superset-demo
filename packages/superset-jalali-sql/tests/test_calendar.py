from datetime import date, timedelta
import jdatetime
import pytest
from superset_jalali_sql import g2j, j2g, month_length, parse_jalali

def test_every_supported_day():
    d = date(1971,3,21)
    while d < date(2172,3,20):
        try:
            actual = g2j(d)
        except ValueError:
            break
        oracle = jdatetime.date.fromgregorian(date=d)
        assert actual == (oracle.year,oracle.month,oracle.day)
        assert j2g(*actual) == d
        d += timedelta(days=1)
    assert d.year == 2172

def test_boundaries_and_digits():
    assert j2g(1403,12,30) == date(2025,3,20)
    assert month_length(1403,12) == 30
    with pytest.raises(ValueError): j2g(1404,12,30)
    assert parse_jalali('۱۴۰۳/۰۷/۱۸') == (1403,7,18)
    assert parse_jalali('١٤٠٣-٠٧-١٨') == (1403,7,18)
    for value in ('1403/7/18', '1403/07-18', None, '1403/07/18; DROP TABLE sales'):
        with pytest.raises(ValueError): parse_jalali(value)
    for d in (date(1971,3,20),date(2200,1,1)):
        with pytest.raises(ValueError): g2j(d)
