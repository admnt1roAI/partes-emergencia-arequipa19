# Aplicación de escritorio

## Ejecutar en Windows

Desde la raíz del repositorio, activa el entorno virtual e instala las dependencias:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r desktop\requirements.txt
python -m desktop.main
```

La aplicación necesita Windows 10/11 y PySide6. La versión comprobada durante este incremento es PySide6 6.12.0 con Python 3.13.

## Guardado local actual

Los partes se guardan en `%LOCALAPPDATA%\Arequipa19\PartesEmergencia\partes.sqlite3`. El campo N.º Parte acepta un número escrito por el usuario; si se deja vacío, el formulario genera `LOCAL-AAAA-######`. Ambos identifican registros locales y no sustituyen la numeración oficial asignada por Supabase. Los números repetidos se rechazan. Cada registro queda marcado `pending` y la aplicación todavía no sincroniza con Supabase.

Al guardar un parte, **GUARDAR PARTE** solicita una carpeta y crea allí un PDF con el parte organizado por secciones. El registro completo se conserva también en la base local para buscarlo y visualizarlo desde **Buscar / consultar**. Los partes nuevos quedan finalizados y bloqueados para edición normal.

Las correcciones requieren iniciar sesión como administrador. Al corregir se debe indicar un motivo; se genera un PDF de nueva versión en la carpeta elegida y se conservan los archivos PDF y datos de versiones anteriores en el historial del parte.

Cada PDF muestra un código de emisión con fecha, hora y número de parte. Las correcciones de uso interno indican **copia registrada**; el historial conserva las versiones y el motivo de cada cambio.

El almacenamiento usa SQLite local. No se guardan credenciales remotas en la base. Los permisos de Windows para la carpeta del perfil protegen los archivos según la cuenta del sistema; la aplicación aún no cifra la base local.

## Modo administrador local

En el primer acceso a **Modo administrador**, la aplicación pide crear una contraseña de al menos 10 caracteres. En los accesos siguientes pide esa contraseña. La verificación se almacena con salt y PBKDF2; no se puede recuperar desde la interfaz.

Desde el panel de administración se puede cambiar la clave, validando primero la actual. Al cambiarla se cierra el panel administrativo; las sesiones abiertas con la clave anterior dejan de poder modificar catálogos.

La sesión administrativa se cierra automáticamente a los 10 minutos, al entrar a **Nuevo parte**, al salir del panel mediante **Cerrar sesión administrador** o al terminar/cancelar una corrección. Mientras está activa, el administrador puede buscar partes para corregirlos y gestionar catálogos. El cambio a **Buscar / consultar** mantiene la sesión para permitir la corrección; el cierre manual y el temporizador la revocan también desde esa pantalla.

Desde **Escudo y títulos** el administrador puede elegir otro escudo y cambiar los títulos de la aplicación y del parte. La imagen se conserva junto a los datos locales y se usa en el formulario, la consulta y los PDFs que se generen después del cambio.

El administrador puede agregar, modificar, retirar y restaurar valores de las listas desplegables del formulario: distrito, centralista, tipo de emergencia, codificación, unidades, personal, condiciones, compañías de apoyo, comisarías y opciones Sí/No. Los distritos iniciales aparecen alfabéticamente, incluyendo los 29 distritos de la provincia; centralistas también se ordenan alfabéticamente. Las listas de unidades y personal se completan desde Administración.

Las listas desplegables permiten seleccionar un valor predefinido o escribir uno para ese parte. El texto escrito directamente se guarda en ese registro y no se agrega al catálogo; para dejarlo disponible en otros partes, agrégalo desde Administración.

Retirar una opción la oculta de los formularios nuevos y permite restaurarla después. Los partes ya guardados conservan una copia de sus valores, por lo que cambiar un catálogo no cambia esos registros.

Este modo es una protección local de la aplicación; no reemplaza autenticación de usuarios ni permisos de Supabase, todavía pendientes de integración.

Para ejecutar las pruebas locales: `python -m unittest desktop.tests.test_local_reports -v`.
