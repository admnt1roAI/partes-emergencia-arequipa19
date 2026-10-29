begin;

create table if not exists app_private.active_user_sessions (
  user_id uuid primary key references auth.users(id) on delete cascade,
  session_id uuid not null,
  claimed_at timestamptz not null default now()
);
alter table app_private.active_user_sessions enable row level security;
revoke all on app_private.active_user_sessions from public, anon, authenticated;

create or replace function app_private.is_current_session()
returns boolean
language sql stable security definer
set search_path = '' as $$
  select exists (
    select 1 from app_private.active_user_sessions s
    where s.user_id = (select auth.uid())
      and s.session_id = nullif((select auth.jwt())->>'session_id', '')::uuid
  )
$$;
revoke all on function app_private.is_current_session() from public, anon;
grant execute on function app_private.is_current_session() to authenticated;

create or replace function public.claim_single_user_session()
returns void
language plpgsql security definer
set search_path = '' as $$
declare
  v_user_id uuid := (select auth.uid());
  v_session_id uuid := nullif((select auth.jwt())->>'session_id', '')::uuid;
begin
  if v_user_id is null or v_session_id is null then
    raise exception 'No se pudo identificar la sesión. Vuelve a iniciar sesión.' using errcode = '42501';
  end if;
  insert into app_private.active_user_sessions(user_id, session_id, claimed_at)
  values (v_user_id, v_session_id, now())
  on conflict (user_id) do update set session_id = excluded.session_id, claimed_at = excluded.claimed_at;
end;
$$;
revoke all on function public.claim_single_user_session() from public, anon;
grant execute on function public.claim_single_user_session() to authenticated;

create or replace function public.is_current_user_session()
returns boolean
language sql stable security definer
set search_path = '' as $$ select (select app_private.is_current_session()) $$;
revoke all on function public.is_current_user_session() from public, anon;
grant execute on function public.is_current_user_session() to authenticated;

create or replace function app_private.current_company_id()
returns uuid language sql stable security definer
set search_path = '' as $$
  select p.company_id from public.profiles p
  where p.user_id = (select auth.uid()) and p.is_active
    and p.role in ('reporter', 'company_admin', 'general_admin')
    and (select app_private.is_current_session())
$$;
create or replace function app_private.current_role()
returns text language sql stable security definer
set search_path = '' as $$
  select p.role from public.profiles p
  where p.user_id = (select auth.uid()) and p.is_active
    and (select app_private.is_current_session())
$$;
revoke all on function app_private.current_company_id() from public, anon;
revoke all on function app_private.current_role() from public, anon;
grant execute on function app_private.current_company_id() to authenticated;
grant execute on function app_private.current_role() to authenticated;

create or replace function app_private.is_general_admin()
returns boolean
language sql stable security definer
set search_path = '' as $$
  select exists (
    select 1 from public.profiles p
    where p.user_id = (select auth.uid()) and p.is_active and p.role = 'general_admin'
      and (select app_private.is_current_session())
  )
$$;
revoke all on function app_private.is_general_admin() from public, anon;
grant execute on function app_private.is_general_admin() to authenticated;

create or replace function public.admin_report_statistics()
returns jsonb
language plpgsql stable security definer
set search_path = '' as $$
declare
  v_result jsonb;
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede consultar estas estadísticas' using errcode = '42501';
  end if;
  select jsonb_build_object(
    'total_reports', (select count(*) from public.emergency_reports where status <> 'voided'),
    'this_month', (select count(*) from public.emergency_reports where status <> 'voided' and occurred_at >= date_trunc('month', now())),
    'total_victims', (select count(*) from public.report_victims v join public.emergency_reports r on r.id = v.report_id where r.status <> 'voided'),
    'total_units', (select count(*) from public.report_units u join public.emergency_reports r on r.id = u.report_id where r.status <> 'voided'),
    'unique_firefighters', (select count(distinct nullif(btrim(p.firefighter), '')) from public.report_personnel p join public.emergency_reports r on r.id = p.report_id where r.status <> 'voided' and nullif(btrim(p.firefighter), '') is not null),
    'by_emergency', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count) order by q.count desc, q.label) from (select emergency_type as label, count(*)::bigint as count from public.emergency_reports where status <> 'voided' group by emergency_type order by count(*) desc limit 8) q), '[]'::jsonb),
    'by_district', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count) order by q.count desc, q.label) from (select district as label, count(*)::bigint as count from public.emergency_reports where status <> 'voided' group by district order by count(*) desc limit 10) q), '[]'::jsonb),
    'by_month', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count) order by q.month_start) from (select date_trunc('month', occurred_at)::date as month_start, to_char(date_trunc('month', occurred_at), 'YYYY-MM') as label, count(*)::bigint as count from public.emergency_reports where status <> 'voided' and occurred_at >= date_trunc('month', now()) - interval '11 months' group by date_trunc('month', occurred_at)) q), '[]'::jsonb),
    'by_firefighter', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count) order by q.count desc, q.label) from (select btrim(p.firefighter) as label, count(distinct r.id)::bigint as count from public.report_personnel p join public.emergency_reports r on r.id = p.report_id where r.status <> 'voided' and nullif(btrim(p.firefighter), '') is not null group by btrim(p.firefighter) order by count(distinct r.id) desc limit 25) q), '[]'::jsonb),
    'by_firefighter_emergency', coalesce((select jsonb_agg(jsonb_build_object('firefighter', q.firefighter, 'emergency_type', q.emergency_type, 'count', q.count) order by q.firefighter, q.count desc, q.emergency_type) from (select btrim(p.firefighter) as firefighter, r.emergency_type, count(distinct r.id)::bigint as count from public.report_personnel p join public.emergency_reports r on r.id = p.report_id where r.status <> 'voided' and nullif(btrim(p.firefighter), '') is not null group by btrim(p.firefighter), r.emergency_type) q), '[]'::jsonb)
  ) into v_result;
  return v_result;
end;
$$;
revoke all on function public.admin_report_statistics() from public, anon;
grant execute on function public.admin_report_statistics() to authenticated;

create table if not exists public.company_numbering_settings (
  company_id uuid not null references public.companies(id) on delete cascade,
  report_year integer not null check (report_year between 2000 and 9999),
  number_prefix text not null default '',
  padding integer not null default 6 check (padding between 1 and 12),
  updated_by uuid not null references auth.users(id),
  updated_at timestamptz not null default now(),
  primary key (company_id, report_year)
);
alter table public.company_numbering_settings enable row level security;
revoke all on public.company_numbering_settings from public, anon, authenticated;

create or replace function public.admin_get_numbering_configuration(p_report_year integer)
returns table (
  company_id uuid,
  company_name text,
  report_year integer,
  next_number bigint,
  number_prefix text,
  padding integer
)
language plpgsql stable security definer
set search_path = '' as $$
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede consultar la numeración' using errcode = '42501';
  end if;
  if p_report_year < 2000 or p_report_year > 9999 then
    raise exception 'El año no es válido' using errcode = '22023';
  end if;
  return query
    select c.id, c.short_name, p_report_year,
      greatest(coalesce(rc.last_number, 0), coalesce(mx.max_sequence, 0)) + 1,
      coalesce(ns.number_prefix, p_report_year::text || '-'),
      coalesce(ns.padding, 6)
    from public.companies c
    left join public.report_counters rc on rc.company_id = c.id and rc.report_year = p_report_year
    left join (
      select r.company_id, r.report_year, max(r.sequence_number) as max_sequence
      from public.emergency_reports r group by r.company_id, r.report_year
    ) mx on mx.company_id = c.id and mx.report_year = p_report_year
    left join public.company_numbering_settings ns on ns.company_id = c.id and ns.report_year = p_report_year
    where c.is_active
    order by c.short_name;
end;
$$;
revoke all on function public.admin_get_numbering_configuration(integer) from public, anon;
grant execute on function public.admin_get_numbering_configuration(integer) to authenticated;

create or replace function public.admin_save_numbering_configuration(
  p_company_id uuid,
  p_report_year integer,
  p_next_number bigint,
  p_number_prefix text,
  p_padding integer
)
returns void
language plpgsql security definer
set search_path = '' as $$
declare
  v_current bigint;
  v_max_sequence bigint;
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede cambiar la numeración' using errcode = '42501';
  end if;
  if p_report_year < 2000 or p_report_year > 9999 or p_next_number < 1
     or p_padding < 1 or p_padding > 12
     or length(coalesce(p_number_prefix, '')) > 24 then
    raise exception 'Revise el año, el siguiente número, el prefijo y el formato' using errcode = '22023';
  end if;
  if not exists (select 1 from public.companies c where c.id = p_company_id and c.is_active) then
    raise exception 'La compañía no existe o está inactiva' using errcode = '22023';
  end if;
  select coalesce(rc.last_number, 0) into v_current
    from public.report_counters rc where rc.company_id = p_company_id and rc.report_year = p_report_year;
  v_current := coalesce(v_current, 0);
  select coalesce(max(r.sequence_number), 0) into v_max_sequence
    from public.emergency_reports r where r.company_id = p_company_id and r.report_year = p_report_year;
  if p_next_number <= greatest(v_current, v_max_sequence) then
    raise exception 'El siguiente número debe ser mayor que los números ya utilizados o reservados' using errcode = '22023';
  end if;

  insert into public.report_counters(company_id, report_year, last_number)
    values (p_company_id, p_report_year, p_next_number - 1)
    on conflict (company_id, report_year) do update set last_number = excluded.last_number;
  insert into public.company_numbering_settings(company_id, report_year, number_prefix, padding, updated_by, updated_at)
    values (p_company_id, p_report_year, coalesce(p_number_prefix, ''), p_padding, (select auth.uid()), now())
    on conflict (company_id, report_year) do update set number_prefix = excluded.number_prefix,
      padding = excluded.padding, updated_by = excluded.updated_by, updated_at = excluded.updated_at;
end;
$$;
revoke all on function public.admin_save_numbering_configuration(uuid, integer, bigint, text, integer) from public, anon;
grant execute on function public.admin_save_numbering_configuration(uuid, integer, bigint, text, integer) to authenticated;

-- Preserve manually typed report numbers. Automatically assigned numbers use
-- the global administrator's company prefix and padding settings.
create or replace function public.register_emergency_report(p_report jsonb)
returns public.emergency_reports
language plpgsql security definer
set search_path = '' as $$
declare
  v_created public.emergency_reports;
  v_manual_number text;
  v_prefix text;
  v_padding integer;
  v_final_number text;
begin
  if not (select app_private.is_current_session()) then
    raise exception 'Esta cuenta inició sesión en otro equipo. Vuelve a iniciar sesión.' using errcode = '42501';
  end if;
  if p_report is null or jsonb_typeof(p_report) <> 'object' then
    raise exception 'El parte no tiene un formato válido' using errcode = '22023';
  end if;
  v_manual_number := nullif(btrim(p_report->>'report_number'), '');
  if v_manual_number is not null and length(v_manual_number) > 80 then
    raise exception 'El número de parte no puede exceder 80 caracteres' using errcode = '22023';
  end if;

  v_created := public.register_emergency_report_with_sequence(p_report);
  if v_manual_number is not null then
    v_final_number := v_manual_number;
  else
    select ns.number_prefix, ns.padding into v_prefix, v_padding
      from public.company_numbering_settings ns where ns.company_id = v_created.company_id
        and ns.report_year = v_created.report_year;
    v_prefix := coalesce(nullif(v_prefix, ''), v_created.report_year::text || '-');
    v_padding := coalesce(v_padding, 6);
    v_final_number := v_prefix || lpad(v_created.sequence_number::text, v_padding, '0');
  end if;
  update public.emergency_reports set report_number = v_final_number
    where id = v_created.id returning * into v_created;
  return v_created;
end;
$$;
revoke all on function public.register_emergency_report(jsonb) from public, anon;
grant execute on function public.register_emergency_report(jsonb) to authenticated;

commit;
