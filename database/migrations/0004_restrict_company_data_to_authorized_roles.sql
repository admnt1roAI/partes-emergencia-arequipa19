-- Active accounts with an unsupported role (for example, viewer) must not
-- receive company-wide data access through the public Supabase API.
begin;

create or replace function app_private.current_company_id()
returns uuid language sql stable security definer
set search_path = '' as $$
  select p.company_id from public.profiles p
  where p.user_id = (select auth.uid())
    and p.is_active
    and p.role in ('reporter', 'company_admin', 'general_admin')
$$;

commit;
