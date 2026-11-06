#!/usr/bin/env python3
"""
Radar de Editais — coletor + extrator por IA.

Uso:
  python extractor/radar.py coletar            # varre as fontes e lista links novos
  python extractor/radar.py extrair <URL>      # lê um edital (HTML ou PDF) e gera o registro
  python extractor/radar.py semanal [--max 10] # coletar + extrair os novos (usado no GitHub Actions)
  python extractor/radar.py match perfil.json  # ranqueia os editais para um perfil

Saídas:
  data/candidatos.json  — links novos encontrados nas fontes
  data/pendentes.json   — editais extraídos pela IA aguardando revisão humana
  (após revisar, mova o item para data/editais.json com "revisado": true)

Variáveis de ambiente:
  ANTHROPIC_API_KEY   — obrigatória para `extrair`/`semanal`
  RADAR_MODEL         — modelo Claude (padrão: claude-sonnet-5-5)
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = DATA / "editais.json"
CANDIDATOS = DATA / "candidatos.json"
PENDENTES = DATA / "pendentes.json"
FONTES = Path(__file__).with_name("sources.yaml")

HEADERS = {"User-Agent": "RadarEditais/0.1 (+https://github.com/Roplentz/radar-editais)"}
PALAVRAS = re.compile(r"edital|chamada|chamamento|sele[cç][aã]o p[uú]blica|programa|subven", re.I)

TIPOS = ["Subvenção", "Investimento", "Bolsa/Auxílio", "Parceria", "Prêmio", "Crédito"]
PUBLICOS = ["Startup", "Empresa", "ICT/Pesquisador", "Pessoa física"]
ESTAGIOS = ["Ideação", "Pré-seed", "Seed", "Crescimento", "P&D"]


# ---------------------------------------------------------------- utilidades
def ler(path: Path, padrao):
    return json.loads(path.read_text("utf-8")) if path.exists() else padrao


def salvar(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def slug(txt: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:70]


def urls_conhecidas() -> set[str]:
    base = ler(BASE, {"editais": []})["editais"] + ler(PENDENTES, [])
    s = set()
    for e in base:
        s.update(u for u in (e.get("fonte_url"), e.get("pdf_url")) if u)
    return s


def baixar_texto(url: str, limite: int = 60_000) -> str:
    r = requests.get(url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        txt = "\n".join((p.extract_text() or "") for p in reader.pages[:40])
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header"]):
            t.decompose()
        txt = soup.get_text("\n")
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt[:limite]


# ---------------------------------------------------------------- coletar
def coletar() -> list[dict]:
    fontes = yaml.safe_load(FONTES.read_text("utf-8"))["fontes"]
    conhecidas = urls_conhecidas()
    novos: list[dict] = []
    for f in fontes:
        try:
            r = requests.get(f["url"], headers=HEADERS, timeout=40)
            r.raise_for_status()
        except Exception as exc:  # fonte fora do ar não derruba a rodada
            print(f"[aviso] {f['nome']}: {exc}", file=sys.stderr)
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            texto = " ".join(a.get_text(" ").split())
            href = urljoin(f["url"], a["href"])
            if href in conhecidas or not (PALAVRAS.search(texto) or href.lower().endswith(".pdf")):
                continue
            if len(texto) < 12:
                continue
            novos.append({"fonte": f["nome"], "orgao": f["orgao"], "abrangencia": f["abrangencia"],
                          "texto": texto[:200], "url": href, "encontrado_em": str(date.today())})
            conhecidas.add(href)
    salvar(CANDIDATOS, novos)
    print(f"{len(novos)} link(s) novo(s) em {CANDIDATOS.relative_to(ROOT)}")
    return novos


# ---------------------------------------------------------------- extrair (IA)
SCHEMA = {
    "name": "registrar_edital",
    "description": "Registra os dados estruturados de um edital/chamada de fomento brasileiro.",
    "input_schema": {
        "type": "object",
        "properties": {
            "eh_edital": {"type": "boolean", "description": "false se a página não for um edital/chamada com inscrição"},
            "titulo": {"type": "string"},
            "orgao": {"type": "string"},
            "tipo_recurso": {"type": "string", "enum": TIPOS},
            "valor_max": {"type": "string", "description": "valor por proposta ou global, em texto, como no edital"},
            "publico": {"type": "array", "items": {"type": "string", "enum": PUBLICOS}},
            "estagio": {"type": "array", "items": {"type": "string", "enum": ESTAGIOS}},
            "areas": {"type": "array", "items": {"type": "string"}, "description": "temas/setores; use 'Saúde' quando aplicável"},
            "abrangencia": {"type": "string", "description": "'Nacional' ou sigla da UF"},
            "trl_min": {"type": ["integer", "null"]},
            "trl_max": {"type": ["integer", "null"]},
            "contrapartida": {"type": ["string", "null"]},
            "inscricao_inicio": {"type": ["string", "null"], "description": "AAAA-MM-DD"},
            "inscricao_fim": {"type": ["string", "null"], "description": "AAAA-MM-DD; null se fluxo contínuo ou não informado"},
            "fluxo_continuo": {"type": "boolean"},
            "documentos": {"type": "array", "items": {"type": "string"}},
            "observacoes": {"type": "string"},
        },
        "required": ["eh_edital", "titulo", "orgao", "tipo_recurso", "publico", "estagio",
                     "areas", "abrangencia", "fluxo_continuo"],
    },
}

PROMPT = """Você é um analista de fomento à inovação no Brasil. Leia o texto abaixo (página ou PDF de um edital)
e preencha a ferramenta registrar_edital. Regras:
- Use SOMENTE o que está no texto. Se um campo não aparece, use null (ou lista vazia). Nunca invente datas ou valores.
- Datas no formato AAAA-MM-DD. Considere como prazo final a data-limite de submissão da proposta (fase 1, se houver fases).
- Se o texto não for um edital/chamada com inscrição (ex.: notícia de resultado), marque eh_edital=false.
URL de origem: {url}

TEXTO:
{texto}"""


def extrair(url: str, contexto: dict | None = None) -> dict | None:
    import anthropic

    texto = baixar_texto(url)
    cliente = anthropic.Anthropic()
    resp = cliente.messages.create(
        model=os.getenv("RADAR_MODEL", "claude-sonnet-5-5"),
        max_tokens=2000,
        tools=[SCHEMA],
        tool_choice={"type": "tool", "name": "registrar_edital"},
        messages=[{"role": "user", "content": PROMPT.format(url=url, texto=texto)}],
    )
    dados = next(b.input for b in resp.content if b.type == "tool_use")
    if not dados.pop("eh_edital", True):
        print(f"[pulado] não parece edital: {url}")
        return None
    dados.update({
        "id": slug(dados["titulo"]),
        "fonte_url": url,
        "pdf_url": url if url.lower().endswith(".pdf") else None,
        "origem": "ia",
        "revisado": False,
        "verificado_em": str(date.today()),
    })
    if contexto and not dados.get("abrangencia"):
        dados["abrangencia"] = contexto.get("abrangencia", "Nacional")
    pend = ler(PENDENTES, [])
    pend = [p for p in pend if p["id"] != dados["id"]] + [dados]
    salvar(PENDENTES, pend)
    print(f"[ok] {dados['titulo']} → pendentes.json")
    return dados


# ---------------------------------------------------------------- match
def aderencia(e: dict, p: dict) -> int:
    crit = pontos = 0
    if p.get("publico"):
        crit += 1; pontos += p["publico"] in e.get("publico", [])
    if p.get("estagio"):
        crit += 1; pontos += p["estagio"] in e.get("estagio", [])
    if p.get("areas"):
        crit += 1
        ea = [a.lower() for a in e.get("areas", [])]
        pontos += any(a.lower() in ea for a in p["areas"]) or any("qualquer" in a for a in ea)
    if p.get("uf"):
        crit += 1; pontos += e.get("abrangencia") in ("Nacional", p["uf"])
    return round(100 * pontos / crit) if crit else 0


def match(perfil_path: str) -> None:
    perfil = json.loads(Path(perfil_path).read_text("utf-8"))
    hoje = str(date.today())
    abertos = [e for e in ler(BASE, {"editais": []})["editais"]
               if e.get("status_manual") != "Encerrado"
               and (e.get("fluxo_continuo") or not e.get("inscricao_fim") or e["inscricao_fim"] >= hoje)]
    for e in sorted(abertos, key=lambda e: -aderencia(e, perfil)):
        print(f"{aderencia(e, perfil):>3}%  {e.get('inscricao_fim') or 'contínuo/?':<11} {e['titulo']}")


# ---------------------------------------------------------------- CLI
def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__); return
    cmd = argv[0]
    if cmd == "coletar":
        coletar()
    elif cmd == "extrair" and len(argv) > 1:
        extrair(argv[1])
    elif cmd == "semanal":
        maximo = int(argv[argv.index("--max") + 1]) if "--max" in argv else 10
        for c in coletar()[:maximo]:
            try:
                extrair(c["url"], c)
            except Exception as exc:
                print(f"[erro] {c['url']}: {exc}", file=sys.stderr)
    elif cmd == "match" and len(argv) > 1:
        match(argv[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
