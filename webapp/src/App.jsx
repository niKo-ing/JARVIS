import AuthGate from './components/AuthGate.jsx'
import Layout from './components/Layout.jsx'

export default function App() {
  return (
    <AuthGate>
      <Layout />
    </AuthGate>
  )
}
