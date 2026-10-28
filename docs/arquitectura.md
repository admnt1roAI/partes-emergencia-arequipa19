# Arquitectura inicial

## Objetivo

Sistema de partes de emergencia para la Benemérita y Centenaria Compañía de Bomberos Arequipa 19, con aislamiento por compañía desde el primer esquema.

## Componentes

- `web/`: React + TypeScript + Vite para registro y administración web.
- `database/migrations/`: esquema PostgreSQL, funciones transaccionales y políticas RLS versionadas para Supabase.
- `desktop/`: futura aplicación Windows en PySide6, separada en UI, servicios, repositorios, sincronización y documentos.
- `docs/`: decisiones, instalación, operación y manuales.

Supabase Auth identifica al usuario. La tabla `profiles` vincula ese UUID con un rol y una compañía. PostgreSQL aplica RLS en los datos de negocio; la interfaz no es un límite de seguridad. La clave `service_role` solo podrá existir en procesos de servidor y nunca en el cliente web o escritorio.

## Datos y numeración

Los partes y sus filas relacionadas llevan `company_id`. La función `create_emergency_report` verifica la compañía del usuario, asigna el número bajo bloqueo transaccional y crea el registro. Los cambios de numeración quedan aislados por compañía y año. Las correcciones documentales se modelarán como versiones inmutables en una migración posterior.

## Seguridad y límites de esta fase

Las migraciones `0001` y `0002` configuran compañías, perfiles, numeración, catálogos, datos relacionados del parte, control RLS y registro transaccional. El frontend ya incluye acceso por correo/contraseña y solo habilita el formulario a perfiles activos autorizados. Aún no se ha conectado una instancia Supabase, creado usuarios reales ni validado las políticas con una cuenta de prueba; tampoco hay una interfaz web de consulta y administración de usuarios.

## Secuencia de implementación

1. Estructura, decisiones y esquema mínimo con aislamiento por compañía.
2. Catálogos, relaciones del parte, correcciones, auditoría y pruebas RLS.
3. Inicio de sesión y gestión de roles en web.
4. Formulario transaccional y consultas administrativas.
5. Reportes, estadísticas y documentos.
6. Aplicación PySide6, sincronización incremental y archivo local.
7. Integración, empaquetado y manuales operativos.

## Decisiones pendientes

- Confirmar versión objetivo de Windows y validar PySide6 en el equipo de instalación.
- Configurar el proyecto Supabase, URL y clave pública mediante variables de entorno.
- Incorporar emblema oficial solo cuando la compañía proporcione el recurso autorizado.
