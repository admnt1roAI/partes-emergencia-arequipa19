import { createClient, type SupabaseClient } from 'npm:@supabase/supabase-js@2';

type Role = 'general_admin' | 'company_admin' | 'reporter' | 'viewer';
type Action = 'list' | 'create' | 'update' | 'delete';
type Payload = {
  action: Action;
  user_id?: string;
  email?: string;
  password?: string;
  full_name?: string;
  role?: Role;
  company_id?: string;
  is_active?: boolean;
};

const allowedRoles = new Set<Role>(['general_admin', 'company_admin', 'reporter', 'viewer']);
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

function required(value: unknown, label: string, max = 200): string {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > max) {
    throw new Error(`${label} es obligatorio y no puede exceder ${max} caracteres.`);
  }
  return value.trim();
}

function validateRole(value: unknown): Role {
  if (typeof value !== 'string' || !allowedRoles.has(value as Role)) {
    throw new Error('El rol indicado no es válido.');
  }
  return value as Role;
}

async function listAllUsers(admin: SupabaseClient) {
  const users = [];
  for (let page = 1; page <= 20; page += 1) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 500 });
    if (error) throw error;
    users.push(...data.users);
    if (data.users.length < 500) break;
  }
  const { data: profiles, error: profileError } = await admin
    .from('profiles')
    .select('user_id, company_id, role, full_name, is_active, created_at');
  if (profileError) throw profileError;
  const { data: companies, error: companyError } = await admin
    .from('companies')
    .select('id, name, short_name, is_active')
    .order('short_name');
  if (companyError) throw companyError;
  const profileById = new Map((profiles ?? []).map((profile) => [profile.user_id, profile]));
  return {
    users: users.map((user) => ({
      id: user.id,
      email: user.email ?? '',
      created_at: user.created_at,
      last_sign_in_at: user.last_sign_in_at,
      profile: profileById.get(user.id) ?? null,
    })),
    companies: companies ?? [],
  };
}

async function ensureAnotherSuperadmin(admin: SupabaseClient, userId: string) {
  const { count, error } = await admin
    .from('profiles')
    .select('user_id', { count: 'exact', head: true })
    .eq('role', 'general_admin')
    .eq('is_active', true)
    .neq('user_id', userId);
  if (error) throw error;
  if (!count) throw new Error('No se puede retirar al último superadministrador activo.');
}

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'POST') return response({ error: 'Método no permitido.' }, 405);

  const supabaseUrl = Deno.env.get('SUPABASE_URL');
  const publicKey = Deno.env.get('SUPABASE_ANON_KEY') ?? Deno.env.get('SUPABASE_PUBLISHABLE_KEY');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  if (!supabaseUrl || !publicKey || !serviceKey) {
    return response({ error: 'Falta configurar el entorno seguro de Supabase Functions.' }, 500);
  }
  const authorization = request.headers.get('Authorization');
  if (!authorization?.startsWith('Bearer ')) return response({ error: 'Sesión requerida.' }, 401);

  try {
    const callerClient = createClient(supabaseUrl, publicKey, {
      global: { headers: { Authorization: authorization } },
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data: callerData, error: callerError } = await callerClient.auth.getUser();
    if (callerError || !callerData.user) return response({ error: 'La sesión no es válida.' }, 401);

    const admin = createClient(supabaseUrl, serviceKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data: callerProfile, error: profileError } = await admin
      .from('profiles')
      .select('role, is_active')
      .eq('user_id', callerData.user.id)
      .maybeSingle();
    if (profileError) throw profileError;
    if (!callerProfile?.is_active || callerProfile.role !== 'general_admin') {
      return response({ error: 'Solo el superadministrador activo puede administrar cuentas.' }, 403);
    }

    const body = await request.json() as Payload;
    if (body.action === 'list') return response(await listAllUsers(admin));

    if (body.action === 'create') {
      const email = required(body.email, 'El correo', 320).toLowerCase();
      const password = required(body.password, 'La contraseña', 200);
      const fullName = required(body.full_name, 'El nombre', 160);
      const role = validateRole(body.role);
      const companyId = required(body.company_id, 'La compañía');
      if (password.length < 12) throw new Error('La contraseña debe tener al menos 12 caracteres.');
      const { data: created, error: createError } = await admin.auth.admin.createUser({
        email, password, email_confirm: true, user_metadata: { full_name: fullName },
      });
      if (createError) throw createError;
      if (!created.user) throw new Error('Supabase no devolvió la nueva cuenta.');
      const { error: insertError } = await admin.from('profiles').insert({
        user_id: created.user.id, company_id: companyId, role, full_name: fullName, is_active: true,
      });
      if (insertError) {
        await admin.auth.admin.deleteUser(created.user.id);
        throw insertError;
      }
      return response({ ok: true, user_id: created.user.id });
    }

    const userId = required(body.user_id, 'El usuario', 80);
    if (body.action === 'update') {
      const { data: current, error: currentError } = await admin.from('profiles')
        .select('role, is_active').eq('user_id', userId).maybeSingle();
      if (currentError) throw currentError;
      if (!current) throw new Error('No se encontró el perfil del usuario.');
      const role = validateRole(body.role);
      const isActive = body.is_active === true;
      if (userId === callerData.user.id && (role !== 'general_admin' || !isActive)) {
        throw new Error('No puedes quitarte a ti mismo el acceso de superadministrador.');
      }
      if (current.role === 'general_admin' && current.is_active && (role !== 'general_admin' || !isActive)) {
        await ensureAnotherSuperadmin(admin, userId);
      }
      const email = required(body.email, 'El correo', 320).toLowerCase();
      const fullName = required(body.full_name, 'El nombre', 160);
      const companyId = required(body.company_id, 'La compañía');
      const authUpdate: { email: string; user_metadata: { full_name: string }; password?: string } = {
        email, user_metadata: { full_name: fullName },
      };
      if (typeof body.password === 'string' && body.password.length) {
        if (body.password.length < 12) throw new Error('La nueva contraseña debe tener al menos 12 caracteres.');
        authUpdate.password = body.password;
      }
      const { error: authUpdateError } = await admin.auth.admin.updateUserById(userId, authUpdate);
      if (authUpdateError) throw authUpdateError;
      const { error: updateError } = await admin.from('profiles').update({
        full_name: fullName, role, company_id: companyId, is_active: isActive,
      }).eq('user_id', userId);
      if (updateError) throw updateError;
      return response({ ok: true });
    }

    if (body.action === 'delete') {
      if (userId === callerData.user.id) throw new Error('No puedes eliminar la cuenta del superadministrador activo.');
      const { data: profile, error: targetError } = await admin.from('profiles')
        .select('role, is_active').eq('user_id', userId).maybeSingle();
      if (targetError) throw targetError;
      if (profile?.role === 'general_admin' && profile.is_active) await ensureAnotherSuperadmin(admin, userId);
      const { count: reportCount, error: reportError } = await admin.from('emergency_reports')
        .select('id', { count: 'exact', head: true }).eq('created_by', userId);
      if (reportError) throw reportError;
      if (reportCount) {
        return response({ error: 'Esta cuenta tiene partes asociados. Desactívala para conservar el historial.' }, 409);
      }
      const { error: deleteError } = await admin.auth.admin.deleteUser(userId);
      if (deleteError) throw deleteError;
      return response({ ok: true });
    }

    return response({ error: 'Acción no reconocida.' }, 400);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Ocurrió un error al administrar la cuenta.';
    return response({ error: message }, 400);
  }
});
