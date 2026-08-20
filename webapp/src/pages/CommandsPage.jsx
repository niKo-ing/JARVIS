import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase.js'
import { useRealtimeRefresh } from '../hooks/useRealtimeRefresh.js'

const defaultRoutines = [
  { id: 'agenda', icon: '◫', name: 'Leer mi agenda', command: 'Lee mi agenda y dime qué debo hacer hoy' },
  { id: 'codigo', icon: '⌘', name: 'Abrir VS Code', command: 'Abre Visual Studio Code' },
  { id: 'estudio', icon: '◷', name: 'Modo estudio', command: 'Activa el modo estudio y comienza un Pomodoro de 25 minutos' },
  { id: 'estado', icon: '⌁', name: 'Estado del PC', command: 'Dime el estado actual del PC' },
]
const dangerPattern = /\b(apaga|apagar|reinicia|reiniciar|borra|borrar|elimina|eliminar|envía|enviar mensaje)\b/i
const routinesKey = 'jarvis.custom-routines.v1'

export default function CommandsPage() {
  const [text, setText] = useState('')
  const [commands, setCommands] = useState([])
  const [sending, setSending] = useState(false)
  const [removingId, setRemovingId] = useState(null)
  const [message, setMessage] = useState('')
  const [editingRoutines, setEditingRoutines] = useState(false)
  const [routineName, setRoutineName] = useState('')
  const [routineCommand, setRoutineCommand] = useState('')
  const [routines, setRoutines] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(routinesKey) || 'null')
      return Array.isArray(saved) && saved.length ? saved : defaultRoutines
    } catch {
      return defaultRoutines
    }
  })

  const load = useCallback(async () => {
    const { data } = await supabase.from('tasks').select('*')
      .like('title', '[JARVIS_CMD] %')
      .order('created_at', { ascending: false }).limit(12)
    setCommands((data || []).map(row => {
      let metadata = {}
      try { metadata = JSON.parse(row.description || '{}') } catch { /* registro antiguo */ }
      return {
        id: row.id,
        command: row.title.replace('[JARVIS_CMD] ', ''),
        status: metadata.status || (row.completed ? 'completed' : 'pending'),
        result: metadata.result,
        error: metadata.error,
      }
    }))
  }, [])

  useEffect(() => { load() }, [load])
  useRealtimeRefresh('tasks', load)
  useEffect(() => {
    localStorage.setItem(routinesKey, JSON.stringify(routines))
  }, [routines])

  const send = async value => {
    const command = (value || text).trim()
    if (!command || sending) return
    const dangerous = dangerPattern.test(command)
    if (dangerous && !window.confirm(`Esta orden puede realizar una acción delicada:\n\n“${command}”\n\n¿Quieres autorizarla?`)) return
    setSending(true)
    setMessage('')
    const { error } = await supabase.from('tasks').insert({
      title: `[JARVIS_CMD] ${command}`,
      description: JSON.stringify({ status: 'pending', approved: dangerous }),
      priority: 'media',
      completed: false,
    })
    setSending(false)
    if (error) {
      setMessage(`No se pudo enviar: ${error.message}`)
    } else {
      setText('')
      setMessage('Orden enviada a Jarvis.')
      load()
    }
  }

  const statusText = {
    pending: 'Pendiente', running: 'Ejecutando', completed: 'Completada', error: 'Error', cancelled: 'Cancelada',
  }

  const addRoutine = event => {
    event.preventDefault()
    const name = routineName.trim()
    const command = routineCommand.trim()
    if (!name || !command) return
    setRoutines(current => [...current, {
      id: `${Date.now()}`,
      icon: '✦',
      name: name.slice(0, 32),
      command: command.slice(0, 1000),
    }])
    setRoutineName('')
    setRoutineCommand('')
  }

  const removeRoutine = id => {
    setRoutines(current => current.filter(routine => routine.id !== id))
  }

  const dismissCommand = async item => {
    const active = item.status === 'pending' || item.status === 'running'
    const verb = active ? 'cancelar' : 'eliminar'
    if (!window.confirm(`¿Quieres ${verb} esta orden?\n\n“${item.command}”`)) return

    setRemovingId(item.id)
    setMessage('')
    let error
    if (active) {
      const metadata = {
        status: 'cancelled',
        result: 'Cancelada por el usuario',
        finished_at: new Date().toISOString(),
      }
      ;({ error } = await supabase.from('tasks').update({
        completed: true,
        description: JSON.stringify(metadata),
      }).eq('id', item.id))
    } else {
      ;({ error } = await supabase.from('tasks').delete().eq('id', item.id))
    }
    setRemovingId(null)

    if (error) {
      setMessage(`No se pudo ${verb}: ${error.message}`)
      return
    }
    setCommands(current => active
      ? current.map(command => command.id === item.id
        ? { ...command, status: 'cancelled', result: 'Cancelada por el usuario', error: null }
        : command)
      : current.filter(command => command.id !== item.id))
  }

  return (
    <div className="commands-page">
      <div className="command-hero">
        <span className="eyebrow">ENLACE REMOTO</span>
        <h1>¿Qué debe hacer Jarvis?</h1>
        <p>La orden se ejecutará en tu PC cuando Jarvis esté conectado.</p>
      </div>

      <div className="command-box">
        <textarea value={text} onChange={e => setText(e.target.value)}
          placeholder="Ejemplo: abre VS Code y lee mis tareas de hoy…"
          rows={3} maxLength={1000} />
        <button onClick={() => send()} disabled={!text.trim() || sending}>
          {sending ? 'Enviando…' : 'Enviar orden'} <span>↑</span>
        </button>
      </div>
      {message && <p className="command-message">{message}</p>}

      <div className="routine-heading">
        <div><span className="section-label">MIS RUTINAS</span><small>Toca una para ejecutarla</small></div>
        <button onClick={() => setEditingRoutines(value => !value)}>
          {editingRoutines ? 'Listo' : 'Personalizar'}
        </button>
      </div>
      <div className="quick-command-grid">
        {routines.map(routine => (
          <div className="routine-card" key={routine.id}>
            <button className="routine-run" onClick={() => send(routine.command)}>
              <span>{routine.icon}</span>
              <div><b>{routine.name}</b><small>{routine.command}</small></div>
            </button>
            {editingRoutines &&
              <button className="routine-remove" onClick={() => removeRoutine(routine.id)}
                aria-label={`Eliminar ${routine.name}`}>×</button>}
          </div>
        ))}
      </div>
      {editingRoutines && (
        <form className="routine-editor" onSubmit={addRoutine}>
          <strong>Nueva rutina</strong>
          <input value={routineName} onChange={event => setRoutineName(event.target.value)}
            placeholder="Nombre, por ejemplo: Comenzar trabajo" maxLength={32} />
          <textarea value={routineCommand} onChange={event => setRoutineCommand(event.target.value)}
            placeholder="¿Qué debe hacer Jarvis?" rows={2} maxLength={1000} />
          <button disabled={!routineName.trim() || !routineCommand.trim()}>＋ Agregar rutina</button>
        </form>
      )}

      <div className="history-header"><h2>Actividad reciente</h2><button onClick={load}>Actualizar</button></div>
      <div className="command-history">
        {!commands.length && <p className="panel-empty">Aún no has enviado órdenes.</p>}
        {commands.map(item => (
          <article key={item.id}>
            <div className="command-copy"><b>{item.command}</b><small>{item.result || item.error || 'Esperando a Jarvis…'}</small></div>
            <span className={`command-status ${item.status}`}>{statusText[item.status] || item.status}</span>
            <button className="command-remove" onClick={() => dismissCommand(item)}
              disabled={removingId === item.id}
              aria-label={`${item.status === 'pending' || item.status === 'running' ? 'Cancelar' : 'Eliminar'} orden: ${item.command}`}
              title={item.status === 'pending' || item.status === 'running' ? 'Cancelar orden' : 'Eliminar del historial'}>
              {removingId === item.id ? '…' : '×'}
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}
