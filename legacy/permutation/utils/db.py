import duckdb
from dataclasses import dataclass

@dataclass
class LocalDB:
    db_name: str = ""
    conn = duckdb.connect(db_name)


class DBConnection(duckdb.DuckDBPyConnection):
    pass
