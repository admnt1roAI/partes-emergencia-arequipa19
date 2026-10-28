-- Esquema inicial multi-compañía para Supabase. Ejecutar con Supabase CLI.
begin;

create schema if not exists app_private;
revoke all on schema app_private from public, anon, authenticated;

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  short_name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  company_id uuid references public.companies(id),
  role text not null check (role in ('general_admin', 'company_admin', 'reporter', 'viewer')),
  full_name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
create index profiles_company_id_idx on public.profiles(company_id);

create table public.report_counters (
  company_id uuid not null references public.companies(id),
  report_year integer not null check (report_year between 2000 and 9999),
  last_number bigint not null default 0 check (last_number >= 0),
  primary key (company_id, report_year)
);

create table public.emergency_reports (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id),
  report_year integer not null,
  sequence_number bigint not null,
  report_number text generated always as (report_year::text || '-' || lpad(sequence_number::text, 6, '0')) stored,
  occurred_at timestamptz not null,
  emergency_type text not null,
  codification text not null,
  address text not null,
  district text not null,
  work_description text not null,
  observations text not null default '',
  status text not null default 'registered' check (status in ('registered', 'corrected', 'voided')),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, report_year, sequence_number)
);
create index emergency_reports_company_time_idx on public.emergency_reports(company_id, occurred_at desc);
create index emergency_reports_company_type_idx on public.emergency_reports(company_id, emergency_type);

create or replace function app_private.current_company_id()
returns uuid language sql stable security definer
set search_path = '' as $$
  select p.company_id from public.profiles p
  where p.user_id = (select auth.uid()) and p.is_active
$$;

create or replace function app_private.current_role()
returns text language sql stable security definer
set search_path = '' as $$
  select p.role from public.profiles p
  where p.user_id = (select auth.uid()) and p.is_active
$$;

revoke all on function app_private.current_company_id() from public;
revoke all on function app_private.current_role() from public;
grant usage on schema app_private to authenticated;
grant execute on function app_private.current_company_id() to authenticated;
grant execute on function app_private.current_role() to authenticated;

alter table public.companies enable row level security;
alter table public.profiles enable row level security;
alter table public.report_counters enable row level security;
alter table public.emergency_reports enable row level security;

create policy companies_read_assigned on public.companies for select to authenticated
using (id = (select app_private.current_company_id()) or (select app_private.current_role()) = 'general_admin');

create policy profiles_read_self_or_company_admin on public.profiles for select to authenticated
using (user_id = (select auth.uid()) or
  (company_id = (select app_private.current_company_id()) and (select app_private.current_role()) in ('company_admin', 'general_admin')) or
  (select app_private.current_role()) = 'general_admin');

create policy reports_read_company on public.emergency_reports for select to authenticated
using (company_id = (select app_private.current_company_id()) or (select app_private.current_role()) = 'general_admin');

create policy counters_read_company on public.report_counters for select to authenticated
using (company_id = (select app_private.current_company_id()) or (select app_private.current_role()) = 'general_admin');

grant select on public.companies, public.profiles, public.report_counters, public.emergency_reports to authenticated;

-- La inserción directa queda denegada; el RPC controla pertenencia y asigna secuencia atómicamente.
create or replace function public.create_emergency_report(
  p_occurred_at timestamptz,
  p_emergency_type text,
  p_codification text,
  p_address text,
  p_district text,
  p_work_description text,
  p_observations text default ''
)
returns public.emergency_reports
language plpgsql security definer
set search_path = '' as $$
declare
  v_company uuid;
  v_year integer;
  v_seq bigint;
  v_report public.emergency_reports;
begin
  select p.company_id into v_company from public.profiles p
    where p.user_id = (select auth.uid()) and p.is_active
      and p.role in ('general_admin', 'company_admin', 'reporter');
  if v_company is null then
    raise exception 'Usuario sin compañía activa o sin permiso para registrar partes' using errcode = '42501';
  end if;
  if nullif(btrim(p_emergency_type), '') is null or nullif(btrim(p_codification), '') is null
    or nullif(btrim(p_address), '') is null or nullif(btrim(p_district), '') is null
    or nullif(btrim(p_work_description), '') is null then
    raise exception 'Complete los campos obligatorios' using errcode = '22023';
  end if;
  v_year := extract(year from p_occurred_at)::integer;
  insert into public.report_counters(company_id, report_year, last_number)
    values (v_company, v_year, 1)
    on conflict (company_id, report_year) do update
      set last_number = public.report_counters.last_number + 1
    returning last_number into v_seq;
  insert into public.emergency_reports(company_id, report_year, sequence_number, occurred_at,
      emergency_type, codification, address, district, work_description, observations, created_by)
    values (v_company, v_year, v_seq, p_occurred_at, btrim(p_emergency_type), btrim(p_codification),
      btrim(p_address), btrim(p_district), btrim(p_work_description), coalesce(p_observations, ''), (select auth.uid()))
    returning * into v_report;
  return v_report;
end;
$$;
revoke all on function public.create_emergency_report(timestamptz,text,text,text,text,text,text) from public, anon;
grant execute on function public.create_emergency_report(timestamptz,text,text,text,text,text,text) to authenticated;

commit;
