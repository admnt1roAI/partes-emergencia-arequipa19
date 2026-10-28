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

Antes del primer acceso, crea el proyecto Supabase, ejecuta `0001_initial_security_and_reports.sql`, luego `database/seed/0001_initial_company.sql` y después las migraciones `0002_web_registration_and_catalogs.sql`, `0003_manual_web_report_number.sql` y `0004_restrict_company_data_to_authorized_roles.sql`. Invita a cada usuario desde Supabase Auth y asígnale un perfil activo vinculado a la compañía. Las cuentas sin perfil autorizado no pueden registrar. Consulta la guía de configuración más abajo.

Los catálogos web incluyen una copia de las opciones guardadas actualmente en la aplicación local. La base local y la web todavía no se sincronizan entre sí; los cambios futuros realizados solo en la computadora no aparecerán automáticamente en la web.

## Base de datos

Las migraciones se encuentran en `database/migrations/`. Aplícalas en Supabase con Supabase CLI. El frontend utiliza únicamente la clave publicable (`VITE_SUPABASE_PUBLISHABLE_KEY`); nunca pongas una clave `service_role` o `secret` en el navegador ni en GitHub Pages. El acceso a los datos depende de Supabase Auth y las políticas RLS.

## Alcance actual

Arquitectura, migraciones de seguridad y registro web, formulario adaptable con sesión y control de perfil, y app PySide6 con guardado local. Aún falta conectar un proyecto Supabase real, ejecutar pruebas RLS con usuarios de prueba y desplegar la web.

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
