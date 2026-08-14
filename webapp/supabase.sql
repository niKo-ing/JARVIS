-- 1. Crear las tablas que comparten Jarvis y la webapp
CREATE TABLE IF NOT EXISTS public.tasks (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  due_date DATE,
  priority TEXT NOT NULL DEFAULT 'media'
    CHECK (priority IN ('alta', 'media', 'baja')),
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.notes (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);·

CREATE TABLE IF NOT EXISTS public.jarvis_status (
  id TEXT PRIMARY KEY DEFAULT 'main',
  state TEXT NOT NULL DEFAULT 'offline',
  hostname TEXT,
  cpu_percent NUMERIC(5, 1) NOT NULL DEFAULT 0,
  ram_percent NUMERIC(5, 1) NOT NULL DEFAULT 0,
  current_command TEXT,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.remote_commands (
  id BIGSERIAL PRIMARY KEY,
  command TEXT NOT NULL CHECK (char_length(command) BETWEEN 1 AND 1000),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'completed', 'error', 'cancelled')),
  approved BOOLEAN NOT NULL DEFAULT FALSE,
  result TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS remote_commands_pending_idx
  ON public.remote_commands (created_at)
  WHERE status = 'pending';

-- 2. Trigger para updated_at automático
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_updated_at ON public.tasks;
CREATE TRIGGER tasks_updated_at
  BEFORE UPDATE ON public.tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS notes_updated_at ON public.notes;
CREATE TRIGGER notes_updated_at
  BEFORE UPDATE ON public.notes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- 3. RLS: permitir acceso anónimo (para la webapp con anon key)
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jarvis_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.remote_commands ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS anon_all_tasks ON public.tasks;
CREATE POLICY anon_all_tasks ON public.tasks
  FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS anon_all_notes ON public.notes;
CREATE POLICY anon_all_notes ON public.notes
  FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS anon_all_jarvis_status ON public.jarvis_status;
CREATE POLICY anon_all_jarvis_status ON public.jarvis_status
  FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS anon_all_remote_commands ON public.remote_commands;
CREATE POLICY anon_all_remote_commands ON public.remote_commands
  FOR ALL USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON
  public.tasks, public.notes, public.jarvis_status, public.remote_commands
  TO anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE
  public.tasks_id_seq, public.notes_id_seq, public.remote_commands_id_seq
  TO anon, authenticated;

-- 4. Activar eventos en tiempo real para que el iPhone y Jarvis se sincronicen
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'tasks'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'notes'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE notes;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'jarvis_status'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE jarvis_status;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'remote_commands'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE remote_commands;
  END IF;
END $$;
