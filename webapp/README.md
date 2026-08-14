# Jarvis Remoto

Centro de control móvil de Jarvis construido con React, Vite y Supabase.

## Funciones

- Tareas con calendario, prioridad y estado.
- Notas con búsqueda y edición.
- Sincronización en tiempo real mediante Supabase Realtime.
- Inicio con agenda, métricas y presencia real del PC.
- Órdenes remotas con seguimiento de ejecución y confirmación de acciones delicadas.
- PWA instalable en iPhone y otros dispositivos.
- Interfaz adaptada a las zonas seguras de iOS.
- Caché de la interfaz para mostrar la aplicación aunque la conexión se interrumpa.

## Desarrollo

```bash
npm install
npm run dev
```

Para compilar:

```bash
npm run build
```

## Variables

Copia `.env.example` como `.env` y completa:

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_APP_PIN=
```

El PIN actual es solamente una barrera visual del cliente. Antes de dar acceso a
otras personas se debe migrar a Supabase Auth y aplicar políticas RLS por usuario.

## Instalar en iPhone

1. Abre la dirección desplegada usando Safari.
2. Pulsa el botón Compartir.
3. Selecciona **Añadir a pantalla de inicio**.
4. Abre Jarvis desde el nuevo icono.

Las actualizaciones en tareas y notas se reflejan automáticamente entre el iPhone,
la web y Jarvis siempre que las tablas estén incluidas en Supabase Realtime.
