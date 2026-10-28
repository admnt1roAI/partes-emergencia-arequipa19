# Sistema de Gestión de Partes de Emergencia

Proyecto para la Benemérita y Centenaria Compañía de Bomberos Arequipa 19.

## Página web adaptable

La aplicación React funciona en computadoras y celulares. Los usuarios ingresan con correo y contraseña; solo los perfiles activos con rol `reporter`, `company_admin` o `general_admin` pueden registrar partes. El formulario incluye las secciones del parte y guarda cada registro y sus filas relacionadas en una transacción del servidor.

Si no existe `web/.env.local`, la página abre en **modo demostración pública** para revisar el diseño y completar el formulario sin cuenta. Ese modo nunca guarda ni envía los datos. Para iniciar registros reales, se requiere la configuración de Supabase y el inicio de sesión autorizado.

Para iniciar el entorno local, instala Node.js 20.19+ o 22.12+, copia `web/.env.example` a `web/.env.local`, completa la URL de Supabase y la clave pública (`publishable` o `anon`), y ejecuta desde `web/`:

```powershell
npm install
npm run dev -- --host 0.0.0.0
```

En una computadora, abre la dirección local indicada por Vite. Para probar en un celular conectado a la misma red, usa la dirección IP local de la computadora y el puerto mostrado por Vite. Para uso fuera de la red local, despliega el frontend con HTTPS.

Antes del primer acceso, crea el proyecto Supabase, ejecuta `0001_initial_security_and_reports.sql`, luego `database/seed/0001_initial_company.sql` y después las migraciones `0002_web_registration_and_catalogs.sql`, `0003_manual_web_report_number.sql`, `0004_restrict_company_data_to_authorized_roles.sql` y `0005_superadmin_console.sql`. El perfil autorizado debe tener el rol `general_admin` para abrir la consola central. La función de Supabase `admin-users` debe desplegarse desde `supabase/functions/admin-users/`; usa la clave de servicio solo como secreto del entorno de Edge Functions, nunca en el repositorio, Pages o el navegador. Consulta la guía de configuración más abajo.

Los catálogos web incluyen una copia de las opciones guardadas actualmente en la aplicación local. La base local y la web todavía no se sincronizan entre sí; los cambios futuros realizados solo en la computadora no aparecerán automáticamente en la web.

## Base de datos

Las migraciones se encuentran en `database/migrations/`. Aplícalas en Supabase con Supabase CLI. El frontend utiliza únicamente la clave publicable (`VITE_SUPABASE_PUBLISHABLE_KEY`); nunca pongas una clave `service_role` o `secret` en el navegador ni en GitHub Pages. El acceso a los datos depende de Supabase Auth y las políticas RLS.

## Consola de superadministración

El rol `general_admin` ve una consola con estadísticas globales, búsqueda de partes, vista e impresión a PDF, retiro lógico de partes con motivo, gestión de cuentas de Supabase Auth y mantenimiento de catálogos. La eliminación de una cuenta que ya registró partes se bloquea para proteger el historial; se debe desactivar. Para habilitar una cuenta inicial como superadministrador, primero crea/inicia la cuenta en Supabase Auth y luego asígnale el rol a su perfil desde SQL Editor:

```sql
update public.profiles p
set role = 'general_admin', is_active = true
from auth.users u
where u.id = p.user_id
  and lower(u.email) = lower('CORREO_DEL_SUPERADMIN');
```

Revisa que el resultado afecte exactamente una fila. La contraseña no se incluye en SQL ni en el repositorio. Para administrar cuentas, despliega la función `admin-users`. Con Supabase CLI instalado y enlazado al proyecto:

```powershell
supabase functions deploy admin-users
```

La función usa `SUPABASE_SERVICE_ROLE_KEY` del entorno seguro de Supabase Functions; nunca copies ese valor a GitHub Actions, `VITE_*`, Pages ni al frontend. La URL y la clave publicable sí pueden usarse en la compilación web.

La aplicación de escritorio todavía guarda los partes y la clave localmente en SQLite, sin conexión con Supabase. Por tanto, esta consola aún no puede administrar ni revocar el acceso de la computadora local; eso requiere una fase posterior para conectar el escritorio con el servicio central.

## Aplicación de escritorio local

La app PySide6 ya permite crear y consultar partes guardados localmente. Consulta [desktop/app/README.md](desktop/app/README.md) para instalación y ejecución. La sincronización y la numeración oficial están pendientes.

### Alta de usuarios web

1. En Supabase Auth, invita al usuario por correo y establece sus credenciales.
2. Copia el UUID del usuario y crea su perfil. Para un registrador:

```sql
insert into public.profiles (user_id, company_id, role, full_name, is_active)
select 'UUID-DEL-USUARIO', c.id, 'reporter', 'Nombre y apellidos', true
from public.companies c where c.short_name = 'Arequipa 19';
```

Asigna `company_admin` solo a responsables autorizados. El rol `viewer` no puede registrar; una pantalla web de consulta queda para una fase posterior.
