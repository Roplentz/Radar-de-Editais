// Radar de Editais — envio semanal de alertas por e-mail.
// Chamado pelo pg_cron (toda segunda) com o cabeçalho x-radar-secret.
// ?dry=1 => não envia nem registra; devolve a prévia. Sem RESEND_API_KEY, sempre simula.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

type Edital = {
  id: string; titulo: string; orgao: string; tipo_recurso: string; valor_max: string | null;
  publico: string[]; estagio: string[]; areas: string[]; abrangencia: string;
  inscricao_fim: string | null; fluxo_continuo: boolean; fonte_url: string;
  status: string; dias_restantes: number | null;
};
type Assinante = {
  id: string; email: string; nome: string | null; publico: string | null; estagio: string | null;
  areas: string[]; uf: string | null; token: string;
};

const MIN_ADERENCIA = 75;

function aderencia(e: Edital, a: Assinante): number {
  let crit = 0, pts = 0;
  if (a.publico) { crit++; if (e.publico.includes(a.publico)) pts++; }
  if (a.estagio) { crit++; if (e.estagio.includes(a.estagio)) pts++; }
  if (a.areas?.length) {
    crit++;
    if (e.areas.some((x) => a.areas.includes(x) || /^qualquer/i.test(x))) pts++;
  }
  if (a.uf) { crit++; if (e.abrangencia === "Nacional" || e.abrangencia === a.uf) pts++; }
  return crit ? Math.round((100 * pts) / crit) : 0;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
const fmt = (d: string | null) => d ? d.split("-").reverse().join("/") : "";

function prazo(e: Edital) {
  if (e.fluxo_continuo) return "Fluxo contínuo";
  if (e.dias_restantes != null) return `Fecha em ${fmt(e.inscricao_fim)} (${e.dias_restantes} dias)`;
  return "Prazo a confirmar";
}

function html(a: Assinante, itens: { e: Edital; m: number }[], cancelarUrl: string, site: string) {
  const linhas = itens.map(({ e, m }) => `
    <tr><td style="padding:14px 0;border-bottom:1px solid #e5e7eb">
      <div style="font-weight:600;font-size:15px;color:#111827">${esc(e.titulo)}</div>
      <div style="color:#6b7280;font-size:13px">${esc(e.orgao)} · ${esc(e.tipo_recurso)} · ${esc(e.abrangencia)}</div>
      <div style="font-size:13px;margin-top:4px">💰 ${esc(e.valor_max ?? "Ver edital")}</div>
      <div style="font-size:13px;margin-top:2px">⏰ ${prazo(e)} · <b style="color:#15803d">${m}% aderência</b></div>
      <a href="${e.fonte_url}" style="font-size:13px;color:#2563eb">Ver fonte →</a>
    </td></tr>`).join("");
  return `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#111827">
    <h2 style="margin-bottom:4px">📡 Radar de Editais</h2>
    <p style="color:#374151">Olá${a.nome ? " " + esc(a.nome) : ""}! Encontramos ${itens.length} edital(is) compatível(is) com o seu perfil.</p>
    <table width="100%" cellspacing="0" cellpadding="0">${linhas}</table>
    <p style="font-size:12px;color:#6b7280;margin-top:18px">Confira sempre o edital oficial antes de submeter. ${site ? `<a href="${site}">Abrir o radar</a> · ` : ""}<a href="${cancelarUrl}">Cancelar alertas</a></p>
  </div>`;
}

Deno.serve(async (req) => {
  const base = Deno.env.get("SUPABASE_URL")!;
  const db = createClient(base, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  // Configuração: variáveis de ambiente têm prioridade; senão, tabela radar_config
  const { data: cfgRows } = await db.from("radar_config").select("chave,valor");
  const cfg = Object.fromEntries((cfgRows ?? []).map((r) => [r.chave, r.valor]));
  const segredo = Deno.env.get("RADAR_CRON_SECRET") ?? cfg.cron_secret;
  if (!segredo || req.headers.get("x-radar-secret") !== segredo) {
    return new Response("unauthorized", { status: 401 });
  }
  const url = new URL(req.url);
  const resendKey = Deno.env.get("RESEND_API_KEY");
  const dry = url.searchParams.get("dry") === "1" || !resendKey;
  const remetente = Deno.env.get("RADAR_FROM") ?? cfg.remetente ?? "Radar de Editais <onboarding@resend.dev>";
  const site = Deno.env.get("RADAR_SITE_URL") ?? cfg.site_url ?? "";

  const [{ data: editais, error: e1 }, { data: assinantes, error: e2 }, { data: enviados, error: e3 }] = await Promise.all([
    db.from("editais_status").select("*").in("status", ["aberto", "fluxo_continuo"]),
    db.from("assinantes").select("id,email,nome,publico,estagio,areas,uf,token").eq("ativo", true),
    db.from("alertas_enviados").select("assinante_id,edital_id"),
  ]);
  if (e1 || e2 || e3) return Response.json({ erro: e1 ?? e2 ?? e3 }, { status: 500 });

  const ja = new Set((enviados ?? []).map((r) => `${r.assinante_id}|${r.edital_id}`));
  const relatorio: unknown[] = [];

  for (const a of (assinantes ?? []) as Assinante[]) {
    const itens = (editais as Edital[])
      .filter((e) => !ja.has(`${a.id}|${e.id}`))
      .map((e) => ({ e, m: aderencia(e, a) }))
      .filter((x) => x.m >= MIN_ADERENCIA)
      .sort((x, y) => y.m - x.m || (x.e.dias_restantes ?? 9999) - (y.e.dias_restantes ?? 9999));
    if (!itens.length) continue;

    const cancelarUrl = `${base}/functions/v1/cancelar?token=${a.token}`;
    const assunto = `📡 ${itens.length} edital(is) para você — Radar de Editais`;

    if (dry) {
      relatorio.push({ email: a.email, editais: itens.map((x) => `${x.m}% ${x.e.titulo}`) });
      continue;
    }
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${resendKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: remetente, to: [a.email], subject: assunto, html: html(a, itens, cancelarUrl, site),
        headers: { "List-Unsubscribe": `<${cancelarUrl}>` } }),
    });
    if (!r.ok) { relatorio.push({ email: a.email, erro: await r.text() }); continue; }
    await db.from("alertas_enviados").insert(itens.map((x) => ({ assinante_id: a.id, edital_id: x.e.id })));
    relatorio.push({ email: a.email, enviados: itens.length });
  }

  return Response.json({ modo: dry ? "simulacao" : "envio", assinantes: assinantes?.length ?? 0, relatorio });
});
