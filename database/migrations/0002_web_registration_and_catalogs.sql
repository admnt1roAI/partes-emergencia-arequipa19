begin;

-- Full report fields used by the responsive web form.
alter table public.emergency_reports
  add column materials text not null default '',
  add column uniformed text not null default 'Sí' check (uniformed in ('Sí', 'No')),
  add column equipment_orderly text not null default 'Sí' check (equipment_orderly in ('Sí', 'No')),
  add column logbook_recorded text not null default 'Sí' check (logbook_recorded in ('Sí', 'No')),
  add column shift_operator text not null default '',
  add column filled_by text not null default '',
  add column signature_name text not null default '';

create table public.report_victims (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  full_name text,
  dni text,
  age text,
  injury text
);

create table public.report_vehicles (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  plate text,
  make text,
  model text,
  color text,
  year text
);

create table public.report_units (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  unit text,
  pilot text,
  command text,
  kms_out text,
  kms_in text,
  hour_out text,
  hour_in text,
  soat text,
  citv text
);

create table public.report_personnel (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  firefighter text,
  condition text
);

create table public.report_support_vehicles (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  company_name text,
  unit text,
  command text
);

create table public.report_pnp_support (
  id bigint generated always as identity primary key,
  report_id uuid not null references public.emergency_reports(id) on delete cascade,
  company_id uuid not null references public.companies(id),
  institution text,
  vehicle text,
  command text
);

create table public.report_catalogs (
  id bigint generated always as identity primary key,
  company_id uuid not null references public.companies(id) on delete cascade,
  category text not null check (category in (
    'district', 'emergency_type', 'codification', 'unit', 'firefighter',
    'personnel_condition', 'company', 'police_station', 'shift_operator'
  )),
  value text not null check (length(btrim(value)) > 0),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (company_id, category, value)
);

alter table public.report_victims enable row level security;
alter table public.report_vehicles enable row level security;
alter table public.report_units enable row level security;
alter table public.report_personnel enable row level security;
alter table public.report_support_vehicles enable row level security;
alter table public.report_pnp_support enable row level security;
alter table public.report_catalogs enable row level security;

create policy victims_read_company on public.report_victims for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy vehicles_read_company on public.report_vehicles for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy units_read_company on public.report_units for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy personnel_read_company on public.report_personnel for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy support_vehicles_read_company on public.report_support_vehicles for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy pnp_support_read_company on public.report_pnp_support for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy catalogs_read_company on public.report_catalogs for select to authenticated
  using (company_id = (select app_private.current_company_id()));
create policy catalogs_manage_admin on public.report_catalogs for all to authenticated
  using (company_id = (select app_private.current_company_id()) and
         (select app_private.current_role()) in ('company_admin', 'general_admin'))
  with check (company_id = (select app_private.current_company_id()) and
              (select app_private.current_role()) in ('company_admin', 'general_admin'));

grant select on public.report_victims, public.report_vehicles, public.report_units,
  public.report_personnel, public.report_support_vehicles, public.report_pnp_support,
  public.report_catalogs to authenticated;
grant insert, update, delete on public.report_catalogs to authenticated;
grant usage, select on sequence public.report_catalogs_id_seq to authenticated;

-- Replace the initial minimal registration RPC with one atomic operation for the complete report.
drop function public.create_emergency_report(timestamptz, text, text, text, text, text, text);

create or replace function public.register_emergency_report(p_report jsonb)
returns public.emergency_reports
language plpgsql security definer
set search_path = '' as $$
declare
  v_profile public.profiles;
  v_company uuid;
  v_year integer;
  v_sequence bigint;
  v_created public.emergency_reports;
  v_occurred_at timestamptz;
begin
  if p_report is null or jsonb_typeof(p_report) <> 'object' then
    raise exception 'El parte no tiene un formato válido' using errcode = '22023';
  end if;

  select p.* into v_profile
  from public.profiles p
  where p.user_id = (select auth.uid()) and p.is_active
    and p.role in ('general_admin', 'company_admin', 'reporter');
  if v_profile.user_id is null or v_profile.company_id is null then
    raise exception 'Usuario sin autorización o sin compañía asignada' using errcode = '42501';
  end if;
  v_company := v_profile.company_id;

  if nullif(btrim(p_report->>'emergency_type'), '') is null
    or nullif(btrim(p_report->>'codification'), '') is null
    or nullif(btrim(p_report->>'address'), '') is null
    or nullif(btrim(p_report->>'district'), '') is null
    or nullif(btrim(p_report->>'work_description'), '') is null
    or nullif(btrim(p_report->>'signature_name'), '') is null then
    raise exception 'Complete todos los campos obligatorios' using errcode = '22023';
  end if;
  v_occurred_at := (p_report->>'occurred_at')::timestamptz;
  v_year := extract(year from v_occurred_at)::integer;

  insert into public.report_counters(company_id, report_year, last_number)
    values (v_company, v_year, 1)
    on conflict (company_id, report_year) do update
      set last_number = public.report_counters.last_number + 1
    returning last_number into v_sequence;

  insert into public.emergency_reports(
    company_id, report_year, sequence_number, occurred_at, emergency_type, codification,
    address, district, work_description, observations, materials, uniformed,
    equipment_orderly, logbook_recorded, shift_operator, filled_by, signature_name, created_by
  ) values (
    v_company, v_year, v_sequence, v_occurred_at,
    btrim(p_report->>'emergency_type'), btrim(p_report->>'codification'),
    btrim(p_report->>'address'), btrim(p_report->>'district'), btrim(p_report->>'work_description'),
    coalesce(p_report->>'observations', ''), coalesce(p_report->>'materials', ''),
    coalesce(p_report->>'uniformed', 'Sí'), coalesce(p_report->>'equipment_orderly', 'Sí'),
    coalesce(p_report->>'logbook_recorded', 'Sí'), coalesce(p_report->>'shift_operator', ''),
    coalesce(p_report->>'filled_by', ''), coalesce(p_report->>'signature_name', ''), v_profile.user_id
  ) returning * into v_created;

  if jsonb_typeof(coalesce(p_report->'victims', '[]'::jsonb)) <> 'array'
    or jsonb_typeof(coalesce(p_report->'vehicles', '[]'::jsonb)) <> 'array'
    or jsonb_typeof(coalesce(p_report->'units', '[]'::jsonb)) <> 'array'
    or jsonb_typeof(coalesce(p_report->'personnel', '[]'::jsonb)) <> 'array'
    or jsonb_typeof(coalesce(p_report->'supports', '[]'::jsonb)) <> 'array'
    or jsonb_typeof(coalesce(p_report->'pnp_support', '[]'::jsonb)) <> 'array' then
    raise exception 'Las secciones del parte deben ser listas' using errcode = '22023';
  end if;

  insert into public.report_victims(report_id, company_id, full_name, dni, age, injury)
  select v_created.id, v_company, nullif(btrim(x.full_name), ''), nullif(btrim(x.dni), ''),
         nullif(btrim(x.age), ''), nullif(btrim(x.injury), '')
  from jsonb_to_recordset(coalesce(p_report->'victims', '[]'::jsonb)) as x(full_name text, dni text, age text, injury text)
  where nullif(btrim(x.full_name), '') is not null or nullif(btrim(x.dni), '') is not null
    or nullif(btrim(x.age), '') is not null or nullif(btrim(x.injury), '') is not null;

  insert into public.report_vehicles(report_id, company_id, plate, make, model, color, year)
  select v_created.id, v_company, nullif(btrim(x.plate), ''), nullif(btrim(x.make), ''),
         nullif(btrim(x.model), ''), nullif(btrim(x.color), ''), nullif(btrim(x.year), '')
  from jsonb_to_recordset(coalesce(p_report->'vehicles', '[]'::jsonb)) as x(plate text, make text, model text, color text, year text)
  where nullif(btrim(x.plate), '') is not null or nullif(btrim(x.make), '') is not null
    or nullif(btrim(x.model), '') is not null or nullif(btrim(x.color), '') is not null
    or nullif(btrim(x.year), '') is not null;

  insert into public.report_units(report_id, company_id, unit, pilot, command, kms_out, kms_in, hour_out, hour_in, soat, citv)
  select v_created.id, v_company, nullif(btrim(x.unit), ''), nullif(btrim(x.pilot), ''),
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
  select v_created.id, v_company, nullif(btrim(x.firefighter), ''), nullif(btrim(x.condition), '')
  from jsonb_to_recordset(coalesce(p_report->'personnel', '[]'::jsonb)) as x(firefighter text, condition text)
  where nullif(btrim(x.firefighter), '') is not null or nullif(btrim(x.condition), '') is not null;

  insert into public.report_support_vehicles(report_id, company_id, company_name, unit, command)
  select v_created.id, v_company, nullif(btrim(x.company_name), ''), nullif(btrim(x.unit), ''), nullif(btrim(x.command), '')
  from jsonb_to_recordset(coalesce(p_report->'supports', '[]'::jsonb)) as x(company_name text, unit text, command text)
  where nullif(btrim(x.company_name), '') is not null or nullif(btrim(x.unit), '') is not null
    or nullif(btrim(x.command), '') is not null;

  insert into public.report_pnp_support(report_id, company_id, institution, vehicle, command)
  select v_created.id, v_company, nullif(btrim(x.institution), ''), nullif(btrim(x.vehicle), ''), nullif(btrim(x.command), '')
  from jsonb_to_recordset(coalesce(p_report->'pnp_support', '[]'::jsonb)) as x(institution text, vehicle text, command text)
  where nullif(btrim(x.institution), '') is not null or nullif(btrim(x.vehicle), '') is not null
    or nullif(btrim(x.command), '') is not null;

  return v_created;
end;
$$;

revoke all on function public.register_emergency_report(jsonb) from public, anon;
grant execute on function public.register_emergency_report(jsonb) to authenticated;

-- Initial company dropdown values. Administrators can maintain these through RLS-protected table writes.
insert into public.companies (name, short_name)
values ('Benemérita y Centenaria Compañía de Bomberos Arequipa 19', 'Arequipa 19')
on conflict (name) do nothing;

insert into public.report_catalogs(company_id, category, value)
select c.id, seed.category, seed.value
from public.companies c
cross join (values
  ('emergency_type', '10.41 Herido'),
  ('emergency_type', '10.42 Muerto'),
  ('emergency_type', '10.43 Efectivo FF.AA. FF.PP herido'),
  ('emergency_type', '10.46'),
  ('emergency_type', '10.51'),
  ('emergency_type', '20.01'),
  ('emergency_type', '20.02'),
  ('emergency_type', '20.03'),
  ('emergency_type', '20.04'),
  ('emergency_type', 'Accidente vehicular'),
  ('emergency_type', 'Atención prehospitalaria'),
  ('emergency_type', 'Falsa alarma'),
  ('emergency_type', 'Incendio'),
  ('emergency_type', 'Materiales peligrosos'),
  ('emergency_type', 'Rescate'),
  ('emergency_type', 'Otros'),
  ('district', 'Alto Selva Alegre'), ('district', 'Cayma'), ('district', 'Cercado'),
  ('district', 'Cerro Colorado'), ('district', 'Characato'), ('district', 'Chiguata'),
  ('district', 'Hunter (Jacobo Hunter)'), ('district', 'José Luis Bustamante y Rivero'),
  ('district', 'La Joya'), ('district', 'Mariano Melgar'), ('district', 'Miraflores'),
  ('district', 'Mollebaya'), ('district', 'Paucarpata'), ('district', 'Pocsi'),
  ('district', 'Polobaya'), ('district', 'Quequeña'), ('district', 'Sabandía'),
  ('district', 'Sachaca'), ('district', 'San Juan de Siguas'), ('district', 'San Juan de Tarucani'),
  ('district', 'Santa Isabel de Siguas'), ('district', 'Santa Rita de Siguas'),
  ('district', 'Socabaya'), ('district', 'Tiabaya'), ('district', 'Uchumayo'),
  ('district', 'Vítor'), ('district', 'Yanahuara'), ('district', 'Yarabamba'), ('district', 'Yura'),
  ('personnel_condition', 'Asiste'), ('personnel_condition', 'Retén'),
  ('codification', 'CODIGO1'), ('codification', 'CODIGO2'),
  ('codification', 'CODIGO3'), ('codification', 'CODIGO4'),
  ('unit', 'Ambulancia'), ('unit', 'Auxiliar'), ('unit', 'Escala'),
  ('unit', 'Maquina'), ('unit', 'Medica'), ('unit', 'Rescate'),
  ('company', 'B12'), ('company', 'B140'), ('company', 'B19'), ('company', 'B77'), ('company', 'B78'),
  ('police_station', 'Cruz roja'), ('police_station', 'Policia'),
  ('police_station', 'SAMU'), ('police_station', 'Serenazgo')
) as seed(category, value)
where c.short_name = 'Arequipa 19'
on conflict (company_id, category, value) do nothing;

commit;
