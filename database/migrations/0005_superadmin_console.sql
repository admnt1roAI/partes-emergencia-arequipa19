begin;

create or replace function app_private.is_general_admin()
returns boolean
language sql stable security definer
set search_path = '' as $$
  select exists (
    select 1 from public.profiles p
    where p.user_id = (select auth.uid())
      and p.is_active
      and p.role = 'general_admin'
  )
$$;

revoke all on function app_private.is_general_admin() from public, anon;
grant execute on function app_private.is_general_admin() to authenticated;

-- A general administrator can see related rows across every company. Other roles
-- remain limited to the company assigned in their active profile.
drop policy if exists victims_read_company on public.report_victims;
create policy victims_read_authorized on public.report_victims for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists vehicles_read_company on public.report_vehicles;
create policy vehicles_read_authorized on public.report_vehicles for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists units_read_company on public.report_units;
create policy units_read_authorized on public.report_units for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists personnel_read_company on public.report_personnel;
create policy personnel_read_authorized on public.report_personnel for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists support_vehicles_read_company on public.report_support_vehicles;
create policy support_vehicles_read_authorized on public.report_support_vehicles for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists pnp_support_read_company on public.report_pnp_support;
create policy pnp_support_read_authorized on public.report_pnp_support for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists catalogs_read_company on public.report_catalogs;
create policy catalogs_read_authorized on public.report_catalogs for select to authenticated
  using (company_id = (select app_private.current_company_id()) or (select app_private.is_general_admin()));
drop policy if exists catalogs_manage_admin on public.report_catalogs;
create policy catalogs_manage_admin on public.report_catalogs for all to authenticated
  using ((company_id = (select app_private.current_company_id()) and (select app_private.current_role()) = 'company_admin')
      or (select app_private.is_general_admin()))
  with check ((company_id = (select app_private.current_company_id()) and (select app_private.current_role()) = 'company_admin')
      or (select app_private.is_general_admin()));

create table public.admin_report_events (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id),
  actor_id uuid not null references auth.users(id),
  action text not null check (action in ('updated', 'voided')),
  reason text not null,
  report_snapshot jsonb not null,
  created_at timestamptz not null default now()
);
alter table public.admin_report_events enable row level security;
create policy admin_report_events_read on public.admin_report_events for select to authenticated
  using ((select app_private.is_general_admin()));
grant select on public.admin_report_events to authenticated;

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
    'this_month', (select count(*) from public.emergency_reports
      where status <> 'voided' and occurred_at >= date_trunc('month', now())),
    'total_victims', (select count(*) from public.report_victims v
      join public.emergency_reports r on r.id = v.report_id where r.status <> 'voided'),
    'total_units', (select count(*) from public.report_units u
      join public.emergency_reports r on r.id = u.report_id where r.status <> 'voided'),
    'by_emergency', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count)
      order by q.count desc, q.label) from (
        select emergency_type as label, count(*)::bigint as count from public.emergency_reports
        where status <> 'voided' group by emergency_type order by count(*) desc limit 8
      ) q), '[]'::jsonb),
    'by_district', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count)
      order by q.count desc, q.label) from (
        select district as label, count(*)::bigint as count from public.emergency_reports
        where status <> 'voided' group by district order by count(*) desc limit 10
      ) q), '[]'::jsonb),
    'by_month', coalesce((select jsonb_agg(jsonb_build_object('label', q.label, 'count', q.count)
      order by q.month_start) from (
        select date_trunc('month', occurred_at)::date as month_start,
          to_char(date_trunc('month', occurred_at), 'YYYY-MM') as label,
          count(*)::bigint as count
        from public.emergency_reports
        where status <> 'voided' and occurred_at >= date_trunc('month', now()) - interval '11 months'
        group by date_trunc('month', occurred_at)
      ) q), '[]'::jsonb)
  ) into v_result;

  return v_result;
end;
$$;
revoke all on function public.admin_report_statistics() from public, anon;
grant execute on function public.admin_report_statistics() to authenticated;

create or replace function public.admin_search_reports(p_query text default '', p_limit integer default 50, p_offset integer default 0)
returns table (
  id uuid, report_number text, occurred_at timestamptz, emergency_type text,
  address text, district text, status text, created_at timestamptz, total_count bigint
)
language plpgsql stable security definer
set search_path = '' as $$
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede buscar partes' using errcode = '42501';
  end if;
  if p_limit < 1 or p_limit > 100 or p_offset < 0 then
    raise exception 'Paginación no válida' using errcode = '22023';
  end if;
  return query
  with matching as (
    select r.id, r.report_number, r.occurred_at, r.emergency_type,
      r.address, r.district, r.status, r.created_at
    from public.emergency_reports r
    where nullif(btrim(coalesce(p_query, '')), '') is null
      or r.report_number ilike '%' || btrim(p_query) || '%'
      or r.emergency_type ilike '%' || btrim(p_query) || '%'
      or r.address ilike '%' || btrim(p_query) || '%'
      or r.district ilike '%' || btrim(p_query) || '%'
  ), counted as (
    select count(*)::bigint as total_count from matching
  )
  select m.id, m.report_number, m.occurred_at, m.emergency_type,
    m.address, m.district, m.status, m.created_at, c.total_count
  from matching m cross join counted c
  order by m.occurred_at desc
  limit p_limit offset p_offset;
end;
$$;
revoke all on function public.admin_search_reports(text, integer, integer) from public, anon;
grant execute on function public.admin_search_reports(text, integer, integer) to authenticated;

create or replace function public.admin_update_emergency_report(p_report_id uuid, p_report jsonb, p_reason text)
returns public.emergency_reports
language plpgsql security definer
set search_path = '' as $$
declare
  v_actor uuid := (select auth.uid());
  v_before public.emergency_reports;
  v_after public.emergency_reports;
  v_occurred_at timestamptz;
  v_report_number text;
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede corregir partes' using errcode = '42501';
  end if;
  if nullif(btrim(coalesce(p_reason, '')), '') is null then
    raise exception 'Indique el motivo de la modificación' using errcode = '22023';
  end if;
  if p_report is null or jsonb_typeof(p_report) <> 'object' then
    raise exception 'El parte no tiene un formato válido' using errcode = '22023';
  end if;
  select * into v_before from public.emergency_reports where id = p_report_id for update;
  if not found then raise exception 'No se encontró el parte' using errcode = 'P0002'; end if;

  if nullif(btrim(p_report->>'emergency_type'), '') is null
    or nullif(btrim(p_report->>'codification'), '') is null
    or nullif(btrim(p_report->>'address'), '') is null
    or nullif(btrim(p_report->>'district'), '') is null
    or nullif(btrim(p_report->>'work_description'), '') is null
    or nullif(btrim(p_report->>'signature_name'), '') is null then
    raise exception 'Complete todos los campos obligatorios' using errcode = '22023';
  end if;
  v_occurred_at := (p_report->>'occurred_at')::timestamptz;
  v_report_number := coalesce(nullif(btrim(p_report->>'report_number'), ''), v_before.report_number);

  update public.emergency_reports set
    report_number = v_report_number,
    report_year = extract(year from v_occurred_at)::integer,
    occurred_at = v_occurred_at,
    emergency_type = btrim(p_report->>'emergency_type'),
    codification = btrim(p_report->>'codification'),
    address = btrim(p_report->>'address'),
    district = btrim(p_report->>'district'),
    work_description = btrim(p_report->>'work_description'),
    observations = coalesce(p_report->>'observations', ''),
    materials = coalesce(p_report->>'materials', ''),
    uniformed = coalesce(p_report->>'uniformed', 'Sí'),
    equipment_orderly = coalesce(p_report->>'equipment_orderly', 'Sí'),
    logbook_recorded = coalesce(p_report->>'logbook_recorded', 'Sí'),
    shift_operator = coalesce(p_report->>'shift_operator', ''),
    filled_by = coalesce(p_report->>'filled_by', ''),
    signature_name = btrim(p_report->>'signature_name'),
    status = 'corrected', updated_at = now()
  where id = p_report_id returning * into v_after;

  delete from public.report_victims where report_id = p_report_id;
  delete from public.report_vehicles where report_id = p_report_id;
  delete from public.report_units where report_id = p_report_id;
  delete from public.report_personnel where report_id = p_report_id;
  delete from public.report_support_vehicles where report_id = p_report_id;
  delete from public.report_pnp_support where report_id = p_report_id;

  insert into public.report_victims(report_id, company_id, full_name, dni, age, injury)
  select p_report_id, v_after.company_id, nullif(btrim(x.full_name), ''), nullif(btrim(x.dni), ''),
    nullif(btrim(x.age), ''), nullif(btrim(x.injury), '')
  from jsonb_to_recordset(coalesce(p_report->'victims', '[]'::jsonb)) as x(full_name text, dni text, age text, injury text)
  where nullif(btrim(x.full_name), '') is not null or nullif(btrim(x.dni), '') is not null
    or nullif(btrim(x.age), '') is not null or nullif(btrim(x.injury), '') is not null;

  insert into public.report_vehicles(report_id, company_id, plate, make, model, color, year)
  select p_report_id, v_after.company_id, nullif(btrim(x.plate), ''), nullif(btrim(x.make), ''),
    nullif(btrim(x.model), ''), nullif(btrim(x.color), ''), nullif(btrim(x.year), '')
  from jsonb_to_recordset(coalesce(p_report->'vehicles', '[]'::jsonb)) as x(plate text, make text, model text, color text, year text)
  where nullif(btrim(x.plate), '') is not null or nullif(btrim(x.make), '') is not null
    or nullif(btrim(x.model), '') is not null or nullif(btrim(x.color), '') is not null
    or nullif(btrim(x.year), '') is not null;

  insert into public.report_units(report_id, company_id, unit, pilot, command, kms_out, kms_in, hour_out, hour_in, soat, citv)
  select p_report_id, v_after.company_id, nullif(btrim(x.unit), ''), nullif(btrim(x.pilot), ''),
    nullif(btrim(x.command), ''), nullif(btrim(x.kms_out), ''), nullif(btrim(x.kms_in), ''),
    nullif(btrim(x.hour_out), ''), nullif(btrim(x.hour_in), ''), nullif(btrim(x.soat), ''), nullif(btrim(x.citv), '')
  from jsonb_to_recordset(coalesce(p_report->'units', '[]'::jsonb)) as x(
    unit text, pilot text, command text, kms_out text, kms_in text, hour_out text, hour_in text, soat text, citv text)
  where nullif(btrim(x.unit), '') is not null or nullif(btrim(x.pilot), '') is not null
    or nullif(btrim(x.command), '') is not null or nullif(btrim(x.kms_out), '') is not null
    or nullif(btrim(x.kms_in), '') is not null or nullif(btrim(x.hour_out), '') is not null
    or nullif(btrim(x.hour_in), '') is not null or nullif(btrim(x.soat), '') is not null
    or nullif(btrim(x.citv), '') is not null;

  insert into public.report_personnel(report_id, company_id, firefighter, condition)
  select p_report_id, v_after.company_id, nullif(btrim(x.firefighter), ''), nullif(btrim(x.condition), '')
  from jsonb_to_recordset(coalesce(p_report->'personnel', '[]'::jsonb)) as x(firefighter text, condition text)
  where nullif(btrim(x.firefighter), '') is not null or nullif(btrim(x.condition), '') is not null;

  insert into public.report_support_vehicles(report_id, company_id, company_name, unit, command)
  select p_report_id, v_after.company_id, nullif(btrim(x.company_name), ''), nullif(btrim(x.unit), ''), nullif(btrim(x.command), '')
  from jsonb_to_recordset(coalesce(p_report->'supports', '[]'::jsonb)) as x(company_name text, unit text, command text)
  where nullif(btrim(x.company_name), '') is not null or nullif(btrim(x.unit), '') is not null
    or nullif(btrim(x.command), '') is not null;

  insert into public.report_pnp_support(report_id, company_id, institution, vehicle, command)
  select p_report_id, v_after.company_id, nullif(btrim(x.institution), ''), nullif(btrim(x.vehicle), ''), nullif(btrim(x.command), '')
  from jsonb_to_recordset(coalesce(p_report->'pnp_support', '[]'::jsonb)) as x(institution text, vehicle text, command text)
  where nullif(btrim(x.institution), '') is not null or nullif(btrim(x.vehicle), '') is not null
    or nullif(btrim(x.command), '') is not null;

  insert into public.admin_report_events(report_id, actor_id, action, reason, report_snapshot)
  values (p_report_id, v_actor, 'updated', btrim(p_reason), to_jsonb(v_before));
  return v_after;
end;
$$;
revoke all on function public.admin_update_emergency_report(uuid, jsonb, text) from public, anon;
grant execute on function public.admin_update_emergency_report(uuid, jsonb, text) to authenticated;

create or replace function public.admin_void_emergency_report(p_report_id uuid, p_reason text)
returns void
language plpgsql security definer
set search_path = '' as $$
declare
  v_before public.emergency_reports;
begin
  if not (select app_private.is_general_admin()) then
    raise exception 'Solo el superadministrador puede retirar partes' using errcode = '42501';
  end if;
  if nullif(btrim(coalesce(p_reason, '')), '') is null then
    raise exception 'Indique el motivo para retirar el parte' using errcode = '22023';
  end if;
  select * into v_before from public.emergency_reports where id = p_report_id for update;
  if not found then raise exception 'No se encontró el parte' using errcode = 'P0002'; end if;
  update public.emergency_reports set status = 'voided', updated_at = now() where id = p_report_id;
  insert into public.admin_report_events(report_id, actor_id, action, reason, report_snapshot)
  values (p_report_id, (select auth.uid()), 'voided', btrim(p_reason), to_jsonb(v_before));
end;
$$;
revoke all on function public.admin_void_emergency_report(uuid, text) from public, anon;
grant execute on function public.admin_void_emergency_report(uuid, text) to authenticated;

commit;
