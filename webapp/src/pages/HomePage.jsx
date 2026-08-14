import { useCallback, useEffect, useMemo, useState } from 'react'
import { format, isBefore, isSameDay, parseISO } from 'date-fns'
import { es } from 'date-fns/locale/es'
import { supabase } from '../lib/supabase.js'
import { useRealtimeRefresh } from '../hooks/useRealtimeRefresh.js'

const stateLabels = {
  online: 'En línea',
  idle: 'Disponible',
  listening: 'Escuchando',
  working: 'Trabajando',
  speaking: 'Hablando',
  offline: 'Desconectado',
}

export default function HomePage({ onNavigate }) {
  const [tasks, setTasks] = useState([])
  const [notes, setNotes] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)

  const load = useCallback(async () => {
    const [taskResult, noteResult, statusResult] = await Promise.all([
      supabase.from('tasks').select('*').eq('completed', false)
        .order('due_date', { ascending: true, nullsLast: true }).limit(20),
      supabase.from('notes').select('id,title,created_at')
        .neq('title', '__JARVIS_STATUS__')
        .order('created_at', { ascending: false }).limit(3),
      supabase.from('notes').select('content').eq('title', '__JARVIS_STATUS__').maybeSingle(),
    ])
    setTasks(taskResult.data || [])
    setNotes(noteResult.data || [])
    try {
      setStatus(statusResult.data?.content ? JSON.parse(statusResult.data.content) : null)
    } catch {
      setStatus(null)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])
  useRealtimeRefresh('tasks', load)
  useRealtimeRefresh('notes', load)

  const summary = useMemo(() => {
    const now = new Date()
    return {
      today: tasks.filter(t => t.due_date && isSameDay(parseISO(t.due_date), now)),
      overdue: tasks.filter(t => t.due_date && isBefore(parseISO(t.due_date), now)
        && !isSameDay(parseISO(t.due_date), now)),
      next: tasks.find(t => t.due_date),
    }
  }, [tasks])

  const lastSeen = status?.last_seen ? new Date(status.last_seen) : null
  const jarvisOnline = lastSeen && Date.now() - lastSeen.getTime() < 45000
  const checkConnection = async () => {
    setChecking(true)
    await load()
    window.setTimeout(() => setChecking(false), 350)
  }

  if (loading) return <p className="muted-message">Preparando tu panel…</p>

  return (
    <div className="home-page">
      <section className="hero-card">
        <div>
          <span className="eyebrow">CENTRO DE CONTROL</span>
          <h1>Buenos días, señor.</h1>
          <p>{summary.today.length
            ? `Tienes ${summary.today.length} ${summary.today.length === 1 ? 'tarea' : 'tareas'} para hoy.`
            : 'No tienes tareas programadas para hoy.'}</p>
        </div>
        <div className={`jarvis-orb ${jarvisOnline ? 'connected' : ''}`}><span>J</span></div>
      </section>

      <section className="stats-grid">
        <article><span>HOY</span><strong>{summary.today.length}</strong><small>tareas</small></article>
        <article className={summary.overdue.length ? 'warning' : ''}>
          <span>ATRASADAS</span><strong>{summary.overdue.length}</strong><small>pendientes</small>
        </article>
        <article><span>TOTAL</span><strong>{tasks.length}</strong><small>pendientes</small></article>
      </section>

      <section className="panel status-panel">
        <div className="panel-title">
          <div><span className={`live-dot ${jarvisOnline ? 'on' : ''}`} />
            <b>Jarvis en el PC</b></div>
          <strong>{jarvisOnline ? stateLabels[status?.state] || 'En línea' : 'Desconectado'}</strong>
        </div>
        {jarvisOnline ? (
          <div className="metric-row">
            <span>CPU <b>{status.cpu_percent ?? 0}%</b></span>
            <span>RAM <b>{status.ram_percent ?? 0}%</b></span>
            <span>Equipo <b>{status.hostname || 'PC'}</b></span>
          </div>
        ) : <p className="panel-empty">Abre Jarvis en el PC para conectarlo.</p>}
        {status?.current_command && jarvisOnline &&
          <p className="current-command">Ejecutando: {status.current_command}</p>}
        <div className="connection-actions">
          <span>
            {lastSeen
              ? `Última señal: ${lastSeen.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
              : 'Todavía no se ha recibido una señal del PC'}
          </span>
          <button onClick={checkConnection} disabled={checking}>
            <i className={checking ? 'spinning' : ''}>↻</i>
            {checking ? 'Comprobando…' : 'Comprobar conexión'}
          </button>
        </div>
      </section>

      <div className="quick-grid">
        <button onClick={() => onNavigate('commands')}><span>⌁</span><b>Dar una orden</b><small>Controla tu PC</small></button>
        <button onClick={() => onNavigate('tasks')}><span>＋</span><b>Nueva tarea</b><small>Organiza tu día</small></button>
      </div>

      <section className="panel">
        <div className="panel-title"><b>Próximo</b><button onClick={() => onNavigate('tasks')}>Ver agenda</button></div>
        {summary.next ? (
          <div className="next-task">
            <span className={`priority-mark ${summary.next.priority}`} />
            <div><b>{summary.next.title}</b><small>
              {format(parseISO(summary.next.due_date), "EEEE d 'de' MMMM", { locale: es })}
            </small></div>
          </div>
        ) : <p className="panel-empty">No hay entregas próximas.</p>}
      </section>

      <section className="panel">
        <div className="panel-title"><b>Notas recientes</b><button onClick={() => onNavigate('notes')}>Ver todas</button></div>
        {notes.length ? notes.map(note => <div className="recent-note" key={note.id}>⌑ <span>{note.title}</span></div>)
          : <p className="panel-empty">Todavía no tienes notas.</p>}
      </section>
    </div>
  )
}
