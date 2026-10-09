from bisect import bisect_right
from datetime import date, timedelta
import re
from .nowruz import NOWRUZ

STARTS = {y: date.fromisoformat(d) for y,d in NOWRUZ.items()}
YEARS = sorted(STARTS)
DATES = [STARTS[y] for y in YEARS]
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def month_length(jy, jm):
    if type(jy) is not int or type(jm) is not int or not 1350 <= jy <= 1550 or not 1 <= jm <= 12:
        raise ValueError("Jalali year/month outside supported range (1350–1550)")
    return 31 if jm <= 6 else 30 if jm < 12 else (STARTS[jy+1]-STARTS[jy]).days-336

def j2g(jy, jm, jd):
    length = month_length(jy, jm)
    if type(jd) is not int or not 1 <= jd <= length:
        raise ValueError("Invalid Jalali day")
    offset = (jm-1)*31 if jm <= 6 else 186+(jm-7)*30
    return STARTS[jy]+timedelta(days=offset+jd-1)

def g2j(d):
    if not isinstance(d, date) or not DATES[0] <= d < DATES[-1]:
        raise ValueError("Gregorian date outside supported Jalali range (1350–1550)")
    jy = YEARS[bisect_right(DATES,d)-1]
    doy = (d-STARTS[jy]).days
    return (jy,doy//31+1,doy%31+1) if doy < 186 else (jy,(doy-186)//30+7,(doy-186)%30+1)

def parse_jalali(s):
    if not isinstance(s,str):
        raise ValueError("Expected YYYY/MM/DD")
    match = re.fullmatch(r"([0-9]{4})([/\-])([0-9]{2})\2([0-9]{2})", s.translate(DIGITS).strip())
    if not match:
        raise ValueError("Expected YYYY/MM/DD or YYYY-MM-DD")
    parts = tuple(int(match[i]) for i in (1,3,4))
    j2g(*parts)
    return parts
