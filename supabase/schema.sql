-- Radar de Editais — esquema Supabase/Postgres
-- Rode no SQL Editor do Supabase (ou via `supabase db push`).

create extension if not exists "pgcrypto";

-- Fontes que o coletor varre (páginas de listagem de editais)
create table if not exists fontes (
  id           uuid primary key default gen_random_uuid(),
  nome         text not null,
  url          text not null unique,
  orgao        text,
  abrangencia  text default 'Nacional',
  ativa        boolean default true,
  ultima_coleta timestamptz
);

-- Editais extraídos e normalizados
create table if not exists editais (
  id               text primary key,               -- slug estável
  titulo           text not null,
  orgao            text not null,
  tipo_recurso     text check (tipo_recurso in ('Subvenção','Investimento','Bolsa/Auxílio','Parceria','Prêmio','Crédito')),
  valor_max        text,
  valor_global_reais numeric,                      -- quando a IA conseguir numerar
  publico          text[] default '{}',            -- Startup, Empresa, ICT/Pesquisador, Pessoa física
  estagio          text[] default '{}',            -- Ideação, Pré-seed, Seed, Crescimento, P&D
  areas            text[] default '{}',
  abrangencia      text default 'Nacional',        -- 'Nacional' ou sigla da UF
  trl_min          int,
  trl_max          int,
  contrapartida    text,
  inscricao_inicio date,
  inscricao_fim    date,
  fluxo_continuo   boolean default false,
  status_manual    text,                           -- força 'Encerrado' quando a data não basta
  fonte_url        text not null,
  pdf_url          text,
  documentos       text[] default '{}',            -- checklist de documentos exigidos
  observacoes      text,
  origem           text default 'manual',          -- manual | ia
  revisado         boolean default false,          -- revisão humana feita?
  verificado_em    date default current_date,
  criado_em        timestamptz default now()
);

create index if not exists editais_fim_idx  on editais (inscricao_fim);
create index if not exists editais_areas_idx on editais using gin (areas);

-- Status calculado (evita guardar "aberto/encerrado" que envelhece)
create or replace view editais_status as
select e.*,
  case
    when e.status_manual = 'Encerrado' then 'encerrado'
    when e.fluxo_continuo then 'fluxo_continuo'
    when e.inscricao_inicio > current_date then 'em_breve'
    when e.inscricao_fim is null then 'a_confirmar'
    when e.inscricao_fim < current_date then 'encerrado'
    else 'aberto'
  end as status,
  (e.inscricao_fim - current_date) as dias_restantes
from editais e;

-- Perfis de usuários (para match e alertas)
create table if not exists perfis (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade,
  nome        text,
  publico     text,      -- Startup, Empresa, ICT/Pesquisador...
  estagio     text,
  areas       text[] default '{}',
  uf          text,
  trl         int,
  email_alerta boolean default true,
  criado_em   timestamptz default now()
);

-- Registro de alertas enviados (não mandar o mesmo edital duas vezes)
create table if not exists alertas_enviados (
  perfil_id uuid references perfis(id) on delete cascade,
  edital_id text references editais(id) on delete cascade,
  enviado_em timestamptz default now(),
  primary key (perfil_id, edital_id)
);

-- RLS: editais são públicos para leitura; perfis só do próprio usuário
alter table editais enable row level security;
alter table perfis  enable row level security;
alter table alertas_enviados enable row level security;

drop policy if exists "editais leitura publica" on editais;
create policy "editais leitura publica" on editais for select using (true);

drop policy if exists "perfil proprio" on perfis;
create policy "perfil proprio" on perfis for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- Escrita em editais/alertas: apenas service_role (coletor), que ignora RLS.
