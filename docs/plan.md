# Plan de implementación

| Fase | Alcance | Estado |
|---|---|---|
| 1. Base | Estructura, arquitectura y primer esquema con RLS | Completado |
| 2. Datos y seguridad | Catálogos, relaciones, numeración y RPC de registro; faltan pruebas de aislamiento conectadas | En curso |
| 3. Autenticación | Sesiones Supabase y autorización por perfil/rol en la página de registro | En curso |
| 4. Registro web | Formulario completo adaptable y RPC de guardado atómico | En curso |
| 5. Administración | Búsqueda, estadísticas, gestión y reportes | Pendiente |
| 6. Escritorio | PySide6, consulta local, sincronización y exportación | Pendiente |
| 7. Documentos | PDF versionado y Excel | Pendiente |
| 8. Integración | Pruebas de seguridad, conexión y recuperación | Pendiente |
| 9. Despliegue | Instalación, empaquetado, operación y copias de seguridad | Pendiente |

## Primer incremento

- Crear estructura separada por componente.
- Definir compañías y perfiles vinculados a Supabase Auth.
- Asegurar registros por compañía con RLS.
- Crear parte de emergencia mediante una función transaccional que asigna número.
- Dejar documentadas las dependencias externas necesarias para validar la integración real.

## Registro web

- Inicio de sesión por correo/contraseña de Supabase Auth; sin registro público.
- Autorización basada en `profiles.is_active` y roles `reporter`, `company_admin` y `general_admin`.
- Formulario responsive con filas repetibles y envío transaccional al RPC `register_emergency_report`.
- El despliegue y las pruebas de RLS requieren credenciales y un proyecto Supabase del usuario.
