import { useEffect, useState } from 'react'
import TasksPage from '../pages/TasksPage.jsx'
import NotesPage from '../pages/NotesPage.jsx'
import InstallPrompt from './InstallPrompt.jsx'
import HomePage from '../pages/HomePage.jsx'
import CommandsPage from '../pages/CommandsPage.jsx'

const TABS = [
  { id: 'home', label: 'Inicio', icon: '⌂' },
  { id: 'tasks', label: '📋 Tareas', icon: '📋' },
  { id: 'notes', label: '📝 Notas',  icon: '📝' },
  { id: 'commands', label: 'Órdenes', icon: '⌁' },
]

export default function Layout() {
  const [tab, setTab] = useState('home')
  const [online, setOnline] = useState(navigator.onLine)

  useEffect(() => {
    const connected = () => setOnline(true)
    const disconnected = () => setOnline(false)
    window.addEventListener('online', connected)
    window.addEventListener('offline', disconnected)
    return () => {
      window.removeEventListener('online', connected)
      window.removeEventListener('offline', disconnected)
    }
  }, [])

  return (
    <div className="app-shell flex flex-col min-h-screen bg-[#0a0c14]">
      <header className="app-header flex items-center gap-3 px-4 py-3 border-b border-[#1e2333] bg-[#0a0c14]/95">
        <div className="text-lg font-bold tracking-widest">
          <span className="text-[#00e676]">J</span>ARVIS
        </div>
        <span className={`connection-pill ${online ? 'online' : 'offline'}`}>
          <i /> {online ? 'EN LÍNEA' : 'SIN CONEXIÓN'}
        </span>
        <div className="flex-1" />
        <nav className="desktop-nav flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'bg-[#00e676] text-black'
                  : 'text-[#5e6a7e] hover:text-[#dde3ed] hover:bg-[#11141f]'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 p-4 max-w-5xl w-full mx-auto">
        <InstallPrompt />
        {tab === 'home' && <HomePage onNavigate={setTab} />}
        {tab === 'tasks' && <TasksPage />}
        {tab === 'notes' && <NotesPage />}
        {tab === 'commands' && <CommandsPage />}
      </main>

      <nav className="mobile-nav" aria-label="Navegación principal">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={tab === t.id ? 'active' : ''}
          >
            <span>{t.icon}</span>
            {t.label.replace(/[📋📝]/gu, '').trim()}
          </button>
        ))}
      </nav>
    </div>
  )
}
