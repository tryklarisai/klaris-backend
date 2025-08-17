import os
import json
import glob
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

try:
    import gspread
except Exception:  # pragma: no cover
    gspread = None  # type: ignore


@dataclass
class Dataset:
    connector_id: str
    name: str            # human name (e.g., "public.users" or "Leads")
    path: str            # canonical path (e.g., pg_main.public.users, sheets_payroll.<book>::Leads, csv_finance.<file>)
    kind: str            # "table" | "sheet" | "file" | "endpoint"
    columns: Optional[List[Dict[str, Any]]] = None  # [{"name":"id","dtype":"int"}]


class BaseConnector:
    def list_datasets(self) -> List[Dataset]:
        raise NotImplementedError

    def fetch_df(self, dataset: str, *, columns: Optional[List[str]] = None,
                 where: Optional[Dict[str, Any]] = None, limit: int = 2000) -> pd.DataFrame:
        raise NotImplementedError


# ---------- SQL ----------
class SQLConnector(BaseConnector):
    def __init__(self, connector_id: str, url: str, schemas: List[str]):
        self.id = connector_id
        self.url = url
        self.schemas = schemas
        self.engine = create_engine(url, future=True)

    def list_datasets(self) -> List[Dataset]:
        out: List[Dataset] = []
        with self.engine.connect() as conn:
            for schema in self.schemas:
                rows = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema=:s"),
                    {"s": schema},
                ).scalars().all()
                for t in rows:
                    cols = conn.execute(
                        text(
                            "SELECT column_name, data_type FROM information_schema.columns "
                            "WHERE table_schema=:s AND table_name=:t"
                        ),
                        {"s": schema, "t": t},
                    ).all()
                    out.append(
                        Dataset(
                            connector_id=self.id,
                            name=f"{schema}.{t}",
                            path=f"{self.id}.{schema}.{t}",
                            kind="table",
                            columns=[{"name": c[0], "dtype": c[1]} for c in cols],
                        )
                    )
        return out

    def fetch_df(self, dataset: str, *, columns=None, where=None, limit=2000) -> pd.DataFrame:
        # dataset expected as "<schema>.<table>"
        schema, table = dataset.split(".", 1)
        sel = ", ".join([f'"{c}"' for c in columns]) if columns else "*"
        sql = f'SELECT {sel} FROM "{schema}"."{table}"'
        params: Dict[str, Any] = {}
        # simple equality filters
        if where:
            clauses = []
            for i, (k, v) in enumerate(where.items()):
                key = f"p{i}"
                clauses.append(f'"{k}" = :{key}')
                params[key] = v
            sql += " WHERE " + " AND ".join(clauses)
        if "limit" not in sql.lower():
            sql += f" LIMIT {int(limit)}"
        with self.engine.connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params or None)


# ---------- Google Sheets ----------
class GSheetsConnector(BaseConnector):
    def __init__(self, connector_id: str, spreadsheet_ids: List[str], creds_file: Optional[str] = None):
        if gspread is None:
            raise RuntimeError("gspread not installed. Please add gspread to requirements.")
        self.id = connector_id
        self.spreadsheet_ids = spreadsheet_ids
        self.creds_file = creds_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
        self._gc = gspread.service_account(filename=self.creds_file)

    def list_datasets(self) -> List[Dataset]:
        out: List[Dataset] = []
        for sid in self.spreadsheet_ids:
            try:
                sh = self._gc.open_by_key(sid)
                for ws in sh.worksheets():
                    # fetch header row for columns
                    headers = ws.row_values(1)
                    out.append(
                        Dataset(
                            connector_id=self.id,
                            name=f"{sh.title}::{ws.title}",
                            path=f"{self.id}.{sid}::{ws.title}",
                            kind="sheet",
                            columns=[{"name": h, "dtype": "text"} for h in headers if h],
                        )
                    )
            except Exception:
                continue
        return out

    def fetch_df(self, dataset: str, *, columns=None, where=None, limit=2000) -> pd.DataFrame:
        # dataset format: "<spreadsheet_id>::<worksheet_title>"
        sid, sheet = dataset.split("::", 1)
        sh = self._gc.open_by_key(sid)
        ws = sh.worksheet(sheet)
        values = sh.values_get(f"'{ws.title}'!A1:Z{int(limit)+1}").get("values", [])
        if not values:
            return pd.DataFrame()
        headers = values[0]
        data = [row + [""] * (len(headers) - len(row)) for row in values[1:]]
        df = pd.DataFrame(data, columns=headers)
        if columns:
            cols = [c for c in columns if c in df.columns]
            df = df[cols]
        if where:
            for k, v in where.items():
                if k in df.columns:
                    df = df[df[k] == str(v)]
        return df.head(limit)


# ---------- CSV / Parquet directory ----------
class CSVDirConnector(BaseConnector):
    def __init__(self, connector_id: str, path: str, globpat: str = "*.csv"):
        self.id = connector_id
        self.path = path
        self.globpat = globpat

    def list_datasets(self) -> List[Dataset]:
        out: List[Dataset] = []
        for f in glob.glob(os.path.join(self.path, self.globpat)):
            name = os.path.basename(f)
            # peek header
            try:
                df = pd.read_csv(f, nrows=1)
                cols = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
            except Exception:
                cols = None
            out.append(
                Dataset(
                    connector_id=self.id,
                    name=name,
                    path=f"{self.id}.{name}",
                    kind="file",
                    columns=cols,
                )
            )
        return out

    def fetch_df(self, dataset: str, *, columns=None, where=None, limit=2000) -> pd.DataFrame:
        # dataset is filename
        fname = dataset
        fpath = os.path.join(self.path, fname)
        df = pd.read_csv(fpath, nrows=limit)
        if columns:
            cols = [c for c in columns if c in df.columns]
            df = df[cols]
        if where:
            for k, v in where.items():
                if k in df.columns:
                    df = df[df[k] == v]
        return df.head(limit)


# ---------- Registry ----------
class ConnectorRegistry:
    def __init__(self):
        self._cons: Dict[str, BaseConnector] = {}

    @classmethod
    def from_config(cls, config_path: Optional[str] = None):
        cfgp = config_path or os.getenv("CONNECTORS_CONFIG", "connectors.json")
        with open(cfgp, "r") as f:
            cfg = json.load(f)
        reg = cls()
        for s in cfg.get("sources", []):
            t = s["type"]
            cid = s["id"]
            if t == "sql":
                reg._cons[cid] = SQLConnector(cid, s["url"], s.get("schemas", ["public"]))
            elif t == "gsheets":
                reg._cons[cid] = GSheetsConnector(cid, s["spreadsheet_ids"])
            elif t == "csvdir":
                reg._cons[cid] = CSVDirConnector(cid, s["path"], s.get("glob", "*.csv"))
        return reg

    def list_all(self) -> Dict[str, List[Dataset]]:
        out: Dict[str, List[Dataset]] = {}
        for cid, con in self._cons.items():
            out[cid] = con.list_datasets()
        return out

    def fetch_df(self, connector_id: str, dataset: str, **kw) -> pd.DataFrame:
        return self._cons[connector_id].fetch_df(dataset, **kw)

    def to_catalog_json(self) -> Dict[str, Any]:
        cat: Dict[str, Any] = {}
        for cid, con in self._cons.items():
            items = []
            for d in con.list_datasets():
                items.append({
                    "name": d.name,
                    "path": d.path,   # canonical address for the agent
                    "kind": d.kind,
                    "columns": d.columns,
                })
            cat[cid] = items
        return cat
