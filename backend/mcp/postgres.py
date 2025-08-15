"""
Postgres MCP Adapter
Implements: fetch_schema(config: dict, metadata: dict = None) -> dict
- Lists tables and columns (optionally filtered by selected_table_names in metadata).
- Returns sample rows from each table as a preview.
"""
from typing import Dict, Any, Optional
import sqlalchemy
from sqlalchemy import create_engine, inspect, text
import random

class PostgresMCPAdapter:
    @staticmethod
    def list_tables(config: Dict[str, Any]) -> list[Dict[str, Any]]:
        """
        Lightweight listing of user tables without fetching sample rows.
        Returns a list of {schema, table, name} where name is "schema.table".
        """
        user = config.get("user")
        password = config.get("password")
        host = config.get("host")
        port = config.get("port") or 5432
        database = config.get("database")

        if not all([user, password, host, database]):
            raise RuntimeError("Missing Postgres connection config.")

        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        engine = create_engine(url)
        inspector = inspect(engine)
        out: list[Dict[str, Any]] = []
        try:
            for schema in inspector.get_schema_names():
                if schema.startswith("pg_") or schema == "information_schema":
                    continue
                for table_name in inspector.get_table_names(schema=schema):
                    out.append({
                        "schema": schema,
                        "table": table_name,
                        "name": f"{schema}.{table_name}",
                    })
        finally:
            engine.dispose()
        return out

    @staticmethod
    def fetch_schema(config: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetches table and column info (limited to optional metadata['selected_table_names'] list),
        and includes up to 10 sample rows per table.
        """
        # Expected config keys: host, port, user, password, database
        user = config.get("user")
        password = config.get("password")
        host = config.get("host")
        port = config.get("port") or 5432
        database = config.get("database")

        if not all([user, password, host, database]):
            raise RuntimeError("Missing Postgres connection config.")

        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        engine = create_engine(url)
        inspector = inspect(engine)

        # Metadata filter (enforce selected tables if provided)
        selected_tables = None
        if metadata and isinstance(metadata.get("selected_table_names"), list) and metadata["selected_table_names"]:
            selected_tables = set(metadata["selected_table_names"])
        
        # Collect tables
        table_schemas = []
        entities = []
        for schema in inspector.get_schema_names():
            # Only include public/user schemas
            if schema.startswith("pg_") or schema == "information_schema":
                continue
            for table_name in inspector.get_table_names(schema=schema):
                if selected_tables and f"{schema}.{table_name}" not in selected_tables and table_name not in selected_tables:
                    continue
                columns = [
                    {
                        "name": col["name"],
                        "type": str(col["type"])
                    }
                    for col in inspector.get_columns(table_name, schema=schema)
                ]
                # Get sample rows
                try:
                    with engine.connect() as conn:
                        sql = text(f'SELECT * FROM "{schema}"."{table_name}" LIMIT 20')
                        result = conn.execute(sql)
                        rows = [dict(row._mapping) for row in result]
                        # Randomly sample up to 10 rows
                        if rows:
                            sample_size = min(10, len(rows))
                            sample_rows = random.sample(rows, sample_size) if len(rows) > sample_size else rows
                        else:
                            sample_rows = []
                except Exception as e:
                    sample_rows = [{"error": str(e)}]
                # Legacy shape kept for now? Per instructions: not needed; but preserve until callers updated.
                table_schemas.append({
                    "schema": schema,
                    "table": table_name,
                    "columns": columns,
                    "sample_rows": sample_rows
                })
                entities.append({
                    "id": f"{schema}.{table_name}",
                    "name": f"{schema}.{table_name}",
                    "kind": "table",
                    "source": {"provider": "postgres", "schema": schema},
                    "fields": [{"name": c["name"], "type": c["type"]} for c in columns],
                    "samples": [{"rows": sample_rows}] if sample_rows else []
                })
        engine.dispose()
        return {"entities": entities}
