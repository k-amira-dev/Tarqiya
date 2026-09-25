"""Export the model metadata to docs/schema.json (used to build the schema document and ER diagram).

The document is generated from the code, so it cannot drift from the real schema:
    python scripts/export_schema.py
"""
import inspect
import json
import re
from pathlib import Path

from sqlalchemy import Enum
from sqlalchemy.dialects import postgresql

import promoflow.db.models as models
from promoflow.db.base import Base
from promoflow.db.seed import CRITERIA, LOOKUPS, SERVICE_ITEMS, SERVICE_PASS_POINTS, TEACHING_ITEMS

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {  # module -> (domain title, spec sections)
    "org": ("Organisation, users & access", "§0 identity, login"),
    "reference": ("Reference data & policy", "Policy thresholds, Appendix E/F rubrics, journal rankings, lists, RAG"),
    "case": ("Promotion case & applicant record", "§0, §1, §3, §4, §5F, §8"),
    "research": ("Research (§5)", "§5A–5H"),
    "teaching": ("Teaching & advising (§6)", "§6A–6I"),
    "service": ("University & community service (§7)", "§7A, §7B"),
    "assessment": ("Assessment, reports & decisions", "Agents, Report Builder, HoD/Dean gates, Appendix D"),
    "referees": ("Researcher profiles & referees", "Chancellor's Office Agent, worker, Appendix J/K"),
    "audit": ("Audit", "All actions"),
}


def column_comments(cls) -> dict[str, str]:
    """Trailing '# ...' comments on Mapped[] lines of the model class source."""
    out = {}
    for line in inspect.getsource(cls).splitlines():
        m = re.match(r"\s+(\w+): Mapped\[.*#\s*(.+)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def type_str(col) -> str:
    try:
        return col.type.compile(dialect=postgresql.dialect())
    except Exception:
        return type(col.type).__name__


def main() -> None:
    tables = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        t = cls.__table__
        module = cls.__module__.rsplit(".", 1)[-1]
        comments = column_comments(cls)
        cols = []
        for c in t.columns:
            fks = [f"{fk.column.table.name}.{fk.column.name}" + (f" ({fk.ondelete})" if fk.ondelete else "")
                   for fk in c.foreign_keys]
            key = "PK" if c.primary_key else ("FK → " + ", ".join(fks) if fks else "")
            if c.unique:
                key = (key + " · " if key else "") + "unique"
            default = ""
            if c.server_default is not None:
                default = "now()" if "now" in str(getattr(c.server_default, "arg", "")) else "server default"
            if c.computed is not None:
                default = f"generated: {c.computed.sqltext}"
            cols.append({
                "name": c.name, "type": type_str(c), "nullable": bool(c.nullable) and not c.primary_key,
                "key": key, "default": default, "note": comments.get(c.name, ""),
                "enum": c.type.name if isinstance(c.type, Enum) else None,
            })
        constraints = []
        for con in t.constraints:
            kind = type(con).__name__
            if kind == "CheckConstraint":
                constraints.append(f"CHECK {con.name}: {con.sqltext}")
            elif kind == "UniqueConstraint" and len(con.columns) > 0 and not (
                    len(con.columns) == 1 and list(con.columns)[0].unique):
                constraints.append("UNIQUE (" + ", ".join(c.name for c in con.columns) + ")")
        for ix in t.indexes:
            using = ix.dialect_options["postgresql"].get("using")
            constraints.append(f"INDEX {ix.name}" + (f" USING {using}" if using else "")
                               + " (" + ", ".join(c.name for c in ix.columns) + ")")
        doc = inspect.cleandoc(cls.__doc__) if cls.__doc__ else ""
        refs = sorted({fk.column.table.name for fk in t.foreign_keys} - {t.name})
        tables.append({"name": t.name, "class": cls.__name__, "module": module, "doc": doc, "refs": refs,
                       "line": inspect.getsourcelines(cls)[1],
                       "columns": cols, "constraints": constraints})

    enums = {}
    for t in Base.metadata.tables.values():
        for c in t.columns:
            if isinstance(c.type, Enum):
                enums.setdefault(c.type.name, {"values": list(c.type.enums), "used_in": set()})
                enums[c.type.name]["used_in"].add(f"{t.name}.{c.name}")
    for e in enums.values():
        e["used_in"] = sorted(e["used_in"])

    order = list(DOMAINS)
    tables.sort(key=lambda x: (order.index(x["module"]), x["line"]))
    data = {
        "domains": [{"module": k, "title": v[0], "spec": v[1]} for k, v in DOMAINS.items()],
        "tables": tables,
        "enums": dict(sorted(enums.items())),
        "criteria": {k.value: {kk: str(vv) for kk, vv in v.items()} for k, v in CRITERIA.items()},
        "teaching_items": TEACHING_ITEMS, "service_items": SERVICE_ITEMS,
        "service_pass_points": str(SERVICE_PASS_POINTS),
        "lookups": LOOKUPS,
    }
    out = ROOT / "docs" / "schema.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}: {len(tables)} tables, {len(enums)} enum types")


if __name__ == "__main__":
    main()
