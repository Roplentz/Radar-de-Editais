# Supabase — projeto `radar-editais` (hdolmwxpnzdybcgdpuyk, sa-east-1)

Aplicado via MCP em 05/11/2026:
1. `radar_schema_inicial` — tabelas `editais`, `assinantes`, `alertas_enviados`, view `editais_status`,
   funções `assinar_radar` (anônimo, sem expor e-mails), `cancelar_assinatura`, `aderencia`, RLS.
2. `radar_config_e_cron` — tabela `radar_config` (cron_secret, site_url, remetente), pg_cron + pg_net,
   job `radar-alertas-semanais` (segundas 11:23 UTC = 08:23 BRT) → edge function `enviar-alertas`.
3. `seed.sql` — 15 editais iniciais.
4. `radar_ajustes_seguranca` — descadastro só via edge function; search_path fixo em `aderencia`.

Edge functions (código em `supabase/functions/`):
- `enviar-alertas` — calcula aderência ≥ 75% e envia por Resend; sem `RESEND_API_KEY` só simula.
- `cancelar` — link de descadastro do e-mail (redireciona para o site com `?alertas=cancelado`).

Para ativar o envio real: Supabase → Edge Functions → Secrets → `RESEND_API_KEY`.
Remetente próprio: `update radar_config` com chave `remetente` (ex.: `Radar <alertas@seudominio.com.br>`)
após verificar o domínio no Resend.
