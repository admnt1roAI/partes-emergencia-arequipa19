-- Permite conservar el número de parte digitado desde el formulario web.
-- La secuencia interna sigue incrementando para generar números automáticos.
begin;

alter table public.emergency_reports
  alter column report_number drop expression;

create unique index emergency_reports_company_report_number_uidx
  on public.emergency_reports(company_id, report_number);

alter function public.register_emergency_report(jsonb)
  rename to register_emergency_report_with_sequence;
revoke all on function public.register_emergency_report_with_sequence(jsonb) from public, anon, authenticated;

create function public.register_emergency_report(p_report jsonb)
returns public.emergency_reports
language plpgsql security definer
set search_path = '' as $$
declare
  v_created public.emergency_reports;
  v_report_number text;
begin
  if p_report is null or jsonb_typeof(p_report) <> 'object' then
    raise exception 'El parte no tiene un formato válido' using errcode = '22023';
  end if;
  v_report_number := nullif(btrim(p_report->>'report_number'), '');
  if v_report_number is not null and length(v_report_number) > 80 then
    raise exception 'El número de parte no puede exceder 80 caracteres' using errcode = '22023';
  end if;

  v_created := public.register_emergency_report_with_sequence(p_report);
  update public.emergency_reports
    set report_number = coalesce(v_report_number, v_created.report_number)
    where id = v_created.id
    returning * into v_created;
  return v_created;
end;
$$;

revoke all on function public.register_emergency_report(jsonb) from public, anon;
grant execute on function public.register_emergency_report(jsonb) to authenticated;

commit;
