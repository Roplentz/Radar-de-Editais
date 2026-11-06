#!/usr/bin/env python3
"""Gera SQL de upsert dos editais de data/editais.json (para colar no Supabase ou usar em migração)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT/"data"/"editais.json").read_text("utf-8"))["editais"]
def q(v):
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, list): return "array[" + ",".join(q(x) for x in v) + "]::text[]" if v else "'{}'::text[]"
    return "'" + str(v).replace("'", "''") + "'"
cols = ["id","titulo","orgao","tipo_recurso","valor_max","publico","estagio","areas","abrangencia",
        "inscricao_inicio","inscricao_fim","fluxo_continuo","status_manual","fonte_url","observacoes","verificado_em"]
rows = [ "(" + ",".join(q(e.get(c)) for c in cols) + ")" for e in d ]
upd = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
print(f"insert into public.editais ({','.join(cols)}) values\n" + ",\n".join(rows) + f"\non conflict (id) do update set {upd};")
