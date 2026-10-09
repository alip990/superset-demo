class PostgreSQL:
    def date_of(self, col): return f"CAST({col} AS DATE)"
    def values_table(self, rows, alias, columns):
        values = ", ".join(f"({y}, DATE '{a}', DATE '{b}')" for y,a,b in rows)
        return f"(VALUES {values}) AS {alias}({', '.join(columns)})"
    def days_between(self, a, b): return f"({a} - {b})"
    def lpad2(self, x): return f"LPAD(CAST({x} AS TEXT), 2, '0')"
    def to_text(self, x): return f"CAST({x} AS TEXT)"
    def concat(self, *parts): return "(" + " || ".join(parts) + ")"
    def persian_digits(self, x): return f"TRANSLATE({x}, '0123456789', '۰۱۲۳۴۵۶۷۸۹')"
    def sat_weekday(self, date): return f"(CAST((EXTRACT(DOW FROM {date}) + 1) AS INT) % 7)"
