-- Datos institucionales iniciales proporcionados por el proyecto.
insert into public.companies (name, short_name)
values (
  'Benemérita y Centenaria Compañía de Bomberos Arequipa 19',
  'Arequipa 19'
)
on conflict (name) do nothing;
