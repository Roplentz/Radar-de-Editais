# 📡 Radar de Editais

Banco de dados vivo de editais de fomento à inovação, saúde e pesquisa no Brasil
(Finep, CNPq, FAPs, Embrapii, Sebrae, Ministério da Saúde…), com filtros, status
calculado automaticamente, aderência ao perfil do usuário e coleta semanal por IA.

Inspirado nas "Grant Programs Databases" europeias, mas com recorte brasileiro e foco
inicial em **saúde, healthtechs e fisioterapia**.

## O que já funciona (MVP)

| Peça | Arquivo | O que faz |
|---|---|---|
| Base inicial | `data/editais.json` | 15 editais reais com fonte (abertos, contínuos e encerrados de 2026) |
| Interface | `web/index.html` | Visões (Abertos, Fecham em 30 dias, Saúde, Startups, Pesquisadores, Fluxo contínuo), busca, filtros e "Meu perfil" com % de aderência |
| Página pronta | `dist/index.html` | Mesma interface com os dados embutidos (abre direto, sem servidor) |
| Coletor + extrator IA | `extractor/radar.py` | Varre as fontes de `sources.yaml`, encontra links novos e usa Claude para extrair os campos do edital (HTML ou PDF) |
| Match | `radar.py match perfil.json` | Ranqueia os editais abertos para um perfil |
| Automação | `.github/workflows/radar-semanal.yml` | Toda segunda: coleta, extrai, gera a página e faz commit |
| Banco | `supabase/schema.sql` | Tabelas `editais`, `fontes`, `perfis`, `alertas_enviados`, view `editais_status` e RLS |

## Rodando

```bash
pip install -r extractor/requirements.txt
python scripts/build.py                 # gera dist/index.html
open dist/index.html                    # ou sirva a pasta e abra web/index.html

export ANTHROPIC_API_KEY=...
python extractor/radar.py coletar       # links novos → data/candidatos.json
python extractor/radar.py extrair <URL> # edital → data/pendentes.json
python extractor/radar.py match data/perfil-exemplo.json
```

### Fluxo de curadoria
1. O coletor acha links novos (`candidatos.json`).
2. A IA extrai os campos e grava em `pendentes.json` com `"revisado": false`.
3. Uma pessoa confere datas e valores no edital oficial e move o item para `editais.json`.

A IA nunca publica sozinha: datas e valores de edital erram fácil e custam caro.

## Modelo de dados (resumo)

`titulo · orgao · tipo_recurso (Subvenção/Investimento/Bolsa-Auxílio/Parceria/Prêmio/Crédito) ·
valor_max · publico[] · estagio[] · areas[] · abrangencia (Nacional/UF) · trl_min/max ·
contrapartida · inscricao_inicio/fim · fluxo_continuo · documentos[] · fonte_url · verificado_em`

O **status não é salvo**: é calculado pela data (aberto, fecha em X dias, contínuo,
a confirmar, encerrado), então a base nunca fica com status velho.

## Roadmap

- **Fase 1 — MVP (agora):** base curada + página com filtros + extrator IA.
- **Fase 2 — Produto:** Supabase como fonte única, login, perfil salvo, alertas por e-mail/WhatsApp
  dos editais compatíveis, checklist de documentos por edital.
- **Fase 3 — Monetização:** versão grátis (lista) como isca de captação; plano pago com alertas,
  match detalhado e rascunho de proposta gerado por IA a partir do edital + perfil.
- **Fontes a adicionar:** todas as FAPs estaduais, BNDES, Diário Oficial da União (seção 3),
  chamadas internacionais com elegibilidade para o Brasil (EIT Health, Horizon Europe, Wellcome).

---
Projeto do ecossistema FISIOIA / Prof. Rodrigo Della Méa Plentz.
