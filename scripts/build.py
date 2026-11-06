#!/usr/bin/env python3
"""Gera dist/index.html com os dados embutidos (página única, abre sem servidor)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
dados = json.loads((ROOT / "data" / "editais.json").read_text("utf-8"))
html = (ROOT / "web" / "index.html").read_text("utf-8")
html = html.replace("/*__DATA__*/null", json.dumps(dados, ensure_ascii=False))
(ROOT / "dist").mkdir(exist_ok=True)
(ROOT / "dist" / "index.html").write_text(html, "utf-8")
(ROOT / "index.html").write_text(html, "utf-8")  # raiz: servida direto pelo Vercel, sem build
print("dist/index.html gerado com", len(dados["editais"]), "editais")
