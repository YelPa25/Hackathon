import { ArrowUpRight, Database, Menu, Orbit, Radio, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router'
import { DataScience, MissionOverview, MissionReplay } from '../pages/MissionData'
import { screens } from '../pages/screens'
import { useHealth } from '../services/health'
import type { Connection } from '../services/health'

const CrewHealth = lazy(() => import('../pages/CrewHealth'))
const ResearchPrototypes = lazy(() => import('../pages/ResearchPrototypes'))

const statuses = {
  checking: { label: 'Checking backend', storage: 'Checking SQLite', tone: 'neutral' },
  connected: { label: 'Backend connected', storage: 'SQLite ready', tone: 'good' },
  'storage-unavailable': { label: 'Backend connected', storage: 'SQLite unavailable', tone: 'warn' },
  unavailable: { label: 'Backend unavailable', storage: 'SQLite status unknown', tone: 'warn' },
} satisfies Record<Connection, { label: string; storage: string; tone: string }>

function Navigation({ onNavigate }: { onNavigate: () => void }) {
  const [open, setOpen] = useState(false)
  const button = useRef<HTMLButtonElement>(null)

  function chooseDestination() {
    setOpen(false)
    onNavigate()
  }

  return <aside className="sidebar" onKeyDown={(event) => {
    if (event.key === 'Escape' && open) {
      setOpen(false)
      button.current?.focus()
    }
  }}>
    <div className="brand-row">
      <Link to="/" className="brand" onClick={chooseDestination} aria-label="ASTRA 2.0 home">
        <span className="brand-mark"><Orbit aria-hidden="true" size={22} /></span>
        <span>ASTRA <small>2.0</small></span>
      </Link>
      <button ref={button} className="menu" type="button" aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-controls="primary-nav" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? <X aria-hidden="true" size={21} /> : <Menu aria-hidden="true" size={21} />}
      </button>
    </div>
    <nav id="primary-nav" aria-label="Primary" className={open ? 'nav is-open' : 'nav'}>
      {screens.map(({ path, title, icon: Icon }) => <NavLink key={path} end to={path} onClick={chooseDestination}>
        <Icon aria-hidden="true" size={18} />
        <span>{title}</span>
      </NavLink>)}
    </nav>
  </aside>
}

function Readiness({ connection }: { connection: Connection }) {
  const { label, storage, tone } = statuses[connection]
  return <section className="readiness surface" aria-labelledby="readiness-title">
    <div className="panel-heading">
      <span className="panel-symbol"><Database size={21} aria-hidden="true" /></span>
      <h2 id="readiness-title">API and storage</h2>
    </div>
    <dl>
      <div><dt><Radio size={16} aria-hidden="true" /> Local API</dt><dd data-tone={connection === 'storage-unavailable' ? 'good' : tone}>{label}</dd></div>
      <div><dt><Database size={16} aria-hidden="true" /> Storage</dt><dd data-tone={tone}>{storage}</dd></div>
    </dl>
  </section>
}

function Screen({ screen, connection }: { screen: typeof screens[number]; connection: Connection }) {
  const { title, description } = screen
  const content = {
    '/': <MissionOverview readiness={<Readiness connection={connection} />} />,
    '/crew-health': <Suspense fallback={<p role="status">Loading Crew Health…</p>}><CrewHealth /></Suspense>,
    '/mission-replay': <MissionReplay />,
    '/data-and-science': <DataScience />,
    '/research-prototypes': <Suspense fallback={<p role="status">Loading research prototypes</p>}>
      <ResearchPrototypes />
    </Suspense>,
  }[screen.path]
  return <section className="screen workspace-inner" aria-labelledby="screen-title" data-enter>
    <header className="screen-heading">
      <h1 id="screen-title">{title}</h1>
      <p>{description}</p>
    </header>
    {content}
  </section>
}

export function App() {
  const connection = useHealth()
  const { label, tone } = statuses[connection]
  const location = useLocation()
  const main = useRef<HTMLElement>(null)
  const previousPath = useRef(location.pathname)

  useEffect(() => {
    const screen = screens.find(({ path }) => path === location.pathname)
    document.title = screen ? screen.title + ' | ASTRA 2.0' : 'ASTRA 2.0'
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname
      main.current?.focus()
    }
  }, [location.pathname])

  return <div className="app-frame">
    <a className="skip" href="#main">Skip to content</a>
    <Navigation onNavigate={() => main.current?.focus()} />
    <div className="workspace min-w-0">
      <header className="status-bar">
        <div className="workspace-inner status-content">
          <span className="console-name">Mission console</span>
          <span className="connection" data-tone={tone} role="status">
            <span className="status-dot" aria-hidden="true" />
            {connection === 'storage-unavailable' ? 'Backend connected · SQLite unavailable' : label}
          </span>
        </div>
      </header>
      <main className="content" id="main" tabIndex={-1} ref={main}>
        <Routes>
          {screens.map((screen) => <Route key={screen.path} path={screen.path}
            element={<Screen key={screen.path} screen={screen} connection={connection} />} />)}
          <Route path="*" element={<section className="screen workspace-inner" aria-labelledby="screen-title">
            <h1 id="screen-title">Page not found</h1>
            <Link className="return-link" to="/">Mission Overview <ArrowUpRight size={16} aria-hidden="true" /></Link>
          </section>} />
        </Routes>
      </main>
    </div>
  </div>
}
