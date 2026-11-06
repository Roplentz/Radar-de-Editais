// Radar de Editais — descadastro de alertas via link do e-mail (?token=uuid).
// Redireciona para o site com ?alertas=cancelado (ou devolve texto simples se não houver site).
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

Deno.serve(async (req) => {
  const token = new URL(req.url).searchParams.get("token") ?? "";
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: cfg } = await db.from("radar_config").select("valor").eq("chave", "site_url").maybeSingle();
  const site = Deno.env.get("RADAR_SITE_URL") ?? cfg?.valor;
  let ok = false;
  if (UUID.test(token)) {
    const { data } = await db.rpc("cancelar_assinatura", { p_token: token });
    ok = data === true;
  }
  if (site) {
    return Response.redirect(`${site}${site.includes("?") ? "&" : "?"}alertas=${ok ? "cancelado" : "invalido"}`, 302);
  }
  return new Response(ok ? "Pronto: você não receberá mais alertas do Radar de Editais." : "Link inválido ou já utilizado.",
    { headers: { "content-type": "text/plain; charset=utf-8" } });
});
