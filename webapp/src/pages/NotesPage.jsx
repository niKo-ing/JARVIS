import { useState, useEffect, useCallback } from 'react'
import { supabase } from '../lib/supabase.js'
import { useRealtimeRefresh } from '../hooks/useRealtimeRefresh.js'

export default function NotesPage() {
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', content: '' })
  const [detail, setDetail] = useState(null)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    let q = supabase.from('notes').select('*')
      .neq('title', '__JARVIS_STATUS__')
      .order('created_at', { ascending: false })
    if (search.trim()) {
      q = q.or(`title.ilike.%${search.trim()}%,content.ilike.%${search.trim()}%`)
    }
    const { data } = await q
    if (data) setNotes(data)
    setLoading(false)
  }, [search])

  useEffect(() => { load() }, [load])
  useRealtimeRefresh('notes', load)

  const create = async () => {
    if (!form.title.trim() || !form.content.trim()) return
    await supabase.from('notes').insert({
      title: form.title.trim(),
      content: form.content.trim(),
    })
    setForm({ title: '', content: '' })
    setShowForm(false)
    load()
  }

  const remove = async (id) => {
    await supabase.from('notes').delete().eq('id', id)
    if (detail?.id === id) setDetail(null)
    load()
  }

  const update = async () => {
    if (!detail) return
    await supabase.from('notes').update({ title: detail.title, content: detail.content }).eq('id', detail.id)
    setDetail(null)
    load()
  }

  if (loading) return <p className="text-[#5e6a7e] text-sm text-center py-12">Cargando notas…</p>

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
      <div>
        <div className="flex items-center gap-2 mb-4">
          <input
            placeholder="🔍 Buscar notas…"
            value={search}
            onChange={e => { setSearch(e.target.value); setLoading(true) }}
            className="flex-1 bg-[#0a0c14] border border-[#1e2333] rounded-xl px-4 py-2.5 text-sm text-[#dde3ed] outline-none focus:border-[#00e676]"
          />
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-[#00e676] text-black font-semibold px-4 py-2.5 rounded-xl text-sm hover:opacity-90 transition-opacity whitespace-nowrap"
          >
            {showForm ? '✕' : '+ Nota'}
          </button>
        </div>

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
              placeholder="Contenido"
              value={form.content}
              onChange={e => setForm({ ...form, content: e.target.value })}
              rows={4}
              className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676] mb-3 resize-none"
            />
            <button
              onClick={create}
              className="w-full bg-[#00e676] text-black font-semibold py-2 rounded-xl text-sm hover:opacity-90 transition-opacity"
            >
              Guardar
            </button>
          </div>
        )}

        {notes.length === 0 ? (
          <div className="text-center py-12 text-[#5e6a7e] text-sm">
            <p className="text-2xl mb-2">📝</p>
            <p>{search ? 'Sin resultados' : 'Sin notas aún'}</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {notes.map(n => (
              <div
                key={n.id}
                onClick={() => setDetail(n)}
                className={`bg-[#11141f] border rounded-xl p-3 cursor-pointer transition-colors ${
                  detail?.id === n.id ? 'border-[#00e676]' : 'border-[#1e2333] hover:border-[#2a3040]'
                }`}
              >
                <p className="text-sm font-semibold text-[#dde3ed] truncate">{n.title}</p>
                <p className="text-xs text-[#5e6a7e] mt-1 line-clamp-2">{n.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {detail && (
        <div className="bg-[#11141f] border border-[#1e2333] rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-[#dde3ed]">Editar nota</h3>
            <button
              onClick={() => setDetail(null)}
              className="text-[#5e6a7e] hover:text-[#dde3ed] text-lg leading-none"
            >
              ✕
            </button>
          </div>
          <input
            value={detail.title}
            onChange={e => setDetail({ ...detail, title: e.target.value })}
            className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676] mb-2"
          />
          <textarea
            value={detail.content}
            onChange={e => setDetail({ ...detail, content: e.target.value })}
            rows={6}
            className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-lg px-3 py-2 text-sm text-[#dde3ed] outline-none focus:border-[#00e676] mb-3 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={update}
              className="flex-1 bg-[#00e676] text-black font-semibold py-2 rounded-xl text-sm hover:opacity-90 transition-opacity"
            >
              Guardar cambios
            </button>
            <button
              onClick={() => remove(detail.id)}
              className="bg-[#f87171]/10 text-[#f87171] border border-[#f87171]/30 font-semibold px-4 py-2 rounded-xl text-sm hover:bg-[#f87171]/20 transition-colors"
            >
              Eliminar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
