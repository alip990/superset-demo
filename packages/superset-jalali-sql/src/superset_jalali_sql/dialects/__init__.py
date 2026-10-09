from .postgresql import PostgreSQL

def get_dialect(name):
    if name != "postgresql": raise ValueError(f"Unsupported dialect: {name}")
    return PostgreSQL()
