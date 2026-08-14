import { useEffect, useState } from 'react'

const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent)
const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches ||
  window.navigator.standalone === true

export default function InstallPrompt() {
  const [installEvent, setInstallEvent] = useState(null)
  const [showIosHelp, setShowIosHelp] = useState(false)
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('jarvis_install_dismissed') === '1',
  )

  useEffect(() => {
    const handleInstall = event => {
      event.preventDefault()
      setInstallEvent(event)
    }
    window.addEventListener('beforeinstallprompt', handleInstall)
    return () => window.removeEventListener('beforeinstallprompt', handleInstall)
  }, [])

  if (dismissed || isStandalone() || (!isIos() && !installEvent)) return null

  const dismiss = () => {
    localStorage.setItem('jarvis_install_dismissed', '1')
    setDismissed(true)
  }

  const install = async () => {
    if (isIos()) {
      setShowIosHelp(true)
      return
    }
    await installEvent.prompt()
    setInstallEvent(null)
  }

  return (
    <div className="install-card" role="status">
      <div className="install-icon">J</div>
      <div className="install-copy">
        <strong>Instala Jarvis en tu iPhone</strong>
        <span>Acceso rápido desde tu pantalla de inicio.</span>
        {showIosHelp && (
          <span className="ios-help">
            En Safari toca <b>Compartir</b> <span aria-hidden="true">⇧</span> y después
            <b> Añadir a pantalla de inicio</b>.
          </span>
        )}
      </div>
      <button className="install-action" onClick={install}>
        {showIosHelp ? 'Entendido' : 'Instalar'}
      </button>
      <button className="install-close" onClick={dismiss} aria-label="Cerrar">×</button>
    </div>
  )
}
