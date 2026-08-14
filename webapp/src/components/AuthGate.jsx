import { useState } from 'react'

const PIN = import.meta.env.VITE_APP_PIN || '1234'

export default function AuthGate({ children }) {
  const [authed, setAuthed] = useState(() => !!sessionStorage.getItem('jarvis_authed'))
  const [pin, setPin] = useState('')
  const [err, setErr] = useState(false)

  if (authed) return children

  const submit = () => {
    if (pin === PIN) {
      sessionStorage.setItem('jarvis_authed', '1')
      setAuthed(true)
    } else {
      setErr(true)
      setPin('')
      setTimeout(() => setErr(false), 1500)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0c14] p-4">
      <div className="bg-[#11141f] border border-[#1e2333] rounded-2xl p-8 w-full max-w-sm text-center">
        <div className="text-4xl mb-2">🛡️</div>
        <h1 className="text-xl font-bold text-[#00e676] mb-1">JARVIS</h1>
        <p className="text-sm text-[#5e6a7e] mb-6">Acceso remoto</p>
        <input
          type="password"
          inputMode="numeric"
          maxLength={4}
          value={pin}
          onChange={e => { setPin(e.target.value); setErr(false) }}
          onKeyDown={e => e.key === 'Enter' && submit()}
          placeholder="PIN"
          className="w-full bg-[#0a0c14] border border-[#1e2333] rounded-xl px-4 py-3 text-center text-2xl text-[#dde3ed] tracking-[8px] outline-none focus:border-[#00e676] mb-4"
          autoFocus
        />
        {err && <p className="text-[#f87171] text-sm mb-3">PIN incorrecto</p>}
        <button
          onClick={submit}
          className="w-full bg-[#00e676] text-black font-bold py-3 rounded-xl text-sm tracking-widest hover:opacity-90 transition-opacity"
        >
          ENTRAR
        </button>
      </div>
    </div>
  )
}
