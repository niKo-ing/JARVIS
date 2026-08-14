import { useState, useEffect, useCallback } from 'react'
import { supabase } from '../lib/supabase.js'
import Calendar from 'react-calendar'
import { format, isSameDay } from 'date-fns'
import { es } from 'date-fns/locale/es'
import { useRealtimeRefresh } from '../hooks/useRealtimeRefresh.js'

const toInputDate = (d) => format(d, 'yyyy-MM-dd')
const fromInputDate = (value) => new Date(`${value}T00:00:00`)

export default function TasksPage() {
  const [tasks, setTasks] = useState([])
  const [date, setDate] = useState(new Date())
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', due_date: '', priority: 'media' })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    const { data } = await supabase
      .from('tasks')
      .select('*')
      .not('title', 'like', '[JARVIS_CMD] %')
      .eq('completed', false)
      .order('due_date', { ascending: true, nullsLast: true })
      .order('created_at', { ascending: false })
    if (data) setTasks(data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])
  useRealtimeRefresh('tasks', load)

  const create = async () => {
    if (!form.title.trim()) return
    await supabase.from('tasks').insert({
      title: form.title.trim(),
      description: form.description.trim(),
      due_date: form.due_date || null,
      priority: form.priority,
    })
    setForm({ title: '', description: '', due_date: '', priority: 'media' })
    setShowForm(false)
    load()
  }

  const complete = async (id) => {
    await supabase.from('tasks').update({ completed: true }).eq('id', id)
    load()
  }

  const remove = async (id) => {
    await supabase.from('tasks').delete().eq('id', id)
    load()
  }

  const openForm = () => {
    setForm(prev => ({ ...prev, due_date: toInputDate(date) }))
    setShowForm(true)
  }

  const handleDateChange = (nextDate) => {
    setDate(nextDate)
    if (showForm) {
      setForm(prev => ({ ...prev, due_date: toInputDate(nextDate) }))
    }
  }

  const dayTasks = tasks.filter(t => t.due_date && isSameDay(fromInputDate(t.due_date), date))
  const tileContent = ({ date: d }) => {
    const has = tasks.some(t => t.due_date && isSameDay(fromInputDate(t.due_date), d))
    if (!has) return null
    return <div className="task-dot" />
  }

  const PRIORITY_STYLES = {
    alta:  'text-[#f87171] border-[#f87171] bg-[#2a000a]',
    media: 'text-[#fbbf24] border-[#fbbf24] bg-[#1a1a00]',
    baja:  'text-[#6ee7b7] border-[#6ee7b7] bg-[#001a0a]',
  }

  if (loading) return <p className="text-[#5e6a7e] text-sm text-center py-12">Cargando tareas…</p>

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4">
      <div>
        <Calendar
          locale="es-ES"
          value={date}
          onChange={handleDateChange}
          tileContent={tileContent}
          className="!bg-[#11141f] !border-[#1e2333]"
        />
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => showForm ? setShowForm(false) : openForm()}
            className="flex-1 bg-[#00e676] text-black font-semibold py-2.5 rounded-xl text-sm hover:opacity-90 transition-opacity"
          >
            {showForm ? '✕ Cancelar' : '+ Nueva tarea'}
          </button>
        </div>
      </div>

      <div>
        {showForm && (
          <div className="bg-[#11141f] border border-[#1e2333] rounded-xl p-4 mb-4">
            <input
              placeholder="Título"
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676] mb-2"
              autoFocus
            />
            <textarea
              placeholder="Descripción (opcional)"
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676] mb-2 resize-none"
            />
            <div className="flex gap-2 mb-3">
              <input
                type="date"
                value={form.due_date}
                onChange={e => setForm({ ...form, due_date: e.target.value })}
                className="flex-1 bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676]"
              />
              <select
                value={form.priority}
                onChange={e => setForm({ ...form, priority: e.target.value })}
                className="bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676]"
              >
                <option value="alta">Alta</option>
                <option value="media">Media</option>
                <option value="baja">Baja</option>
              </select>
            </div>
            <button
              onClick={create}
              className="w-full bg-[#00e676] text-black font-semibold py-2 rounded-xl text-sm hover:opacity-90 transition-opacity"
            >
              Guardar tarea
            </button>
          </div>
        )}

        <h2 className="text-sm text-[#5e6a7e] uppercase tracking-wider font-semibold mb-3">
          {isSameDay(date, new Date()) ? '📅 Hoy' : `📅 ${format(date, "d 'de' MMMM", { locale: es })}`}
          <span className="text-xs ml-2 text-[#5e6a7e]">({dayTasks.length} tareas)</span>
        </h2>

        {dayTasks.length === 0 ? (
          <div className="text-center py-12 text-[#5e6a7e] text-sm">
            <p className="text-2xl mb-2">✨</p>
            <p>Sin tareas para este día</p>
          </div>
        ) : (
          <div className="space-y-2">
            {dayTasks.map(t => (
              <div key={t.id} className="bg-[#11141f] border border-[#1e2333] rounded-xl p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${PRIORITY_STYLES[t.priority] || 'text-[#5e6a7e] border-[#1e2333]'}`}>
                        {t.priority}
                      </span>
                      {t.due_date && (
                        <span className="text-[11px] text-[#5e6a7e]">
                          {format(fromInputDate(t.due_date), 'd MMM', { locale: es })}
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-semibold text-[#dde3ed] truncate">{t.title}</p>
                    {t.description && (
                      <p className="text-xs text-[#5e6a7e] mt-1 line-clamp-2">{t.description}</p>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={() => complete(t.id)}
                      className="text-xs bg-[#00e676]/10 text-[#00e676] border border-[#00e676]/30 px-2.5 py-1.5 rounded-lg hover:bg-[#00e676]/20 transition-colors"
                      title="Completar"
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => remove(t.id)}
                      className="text-xs bg-[#f87171]/10 text-[#f87171] border border-[#f87171]/30 px-2.5 py-1.5 rounded-lg hover:bg-[#f87171]/20 transition-colors"
                      title="Eliminar"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
