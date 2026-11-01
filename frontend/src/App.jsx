import { useEffect, useMemo, useState } from 'react'
import { getSatellites } from './api'
import MapView from './components/MapView'
import CheckPanel from './components/CheckPanel'
import PlanPanel from './components/PlanPanel'
import OrbitBar from './components/OrbitBar'

export default function App() {
  const [tab, setTab] = useState('check')
  const [orbits, setOrbits] = useState(null)
  const [orbitError, setOrbitError] = useState('')
  const [target, setTarget] = useState(null)
  const [area, setArea] = useState(500)
  const [days, setDays] = useState(7)
  const [requests, setRequests] = useState([])
  const [focus, setFocus] = useState(null)
  const [fit, setFit] = useState(0)

  useEffect(() => {
    getSatellites().then(setOrbits).catch((e) => setOrbitError(e.message))
  }, [])

  const satNames = useMemo(() => (orbits ? orbits.satellites.map((s) => s.name) : []), [orbits])

  const onPick = (lat, lon) => {
    const p = { lat: Number(lat.toFixed(3)), lon: Number(lon.toFixed(3)) }
    if (tab === 'check') {
      setTarget(p)
      setFocus(p)
    } else if (requests.length < 30) {
      const n = requests.length + 1
      setRequests([...requests, { id: `t${Date.now()}`, name: `Target ${n}`, ...p, area_km2: 500, priority: 3 }])
    }
  }

  const points = tab === 'check'
    ? (target ? [{ ...target, area_km2: Number(area) || 1, label: 'Target' }] : [])
    : requests.map((r) => ({ lat: r.lat, lon: r.lon, area_km2: Number(r.area_km2) || 1, label: r.name }))

  return (
    <div className="app">
      <header>
        <div>
          <h1>Acquisition planner</h1>
          <p>Can a Firefly satellite image this place, and when? Built on public orbit data.</p>
        </div>
        {orbitError ? <div className="pill warn">{orbitError}</div> : <OrbitBar info={orbits} satNames={satNames} />}
      </header>
      <main>
        <MapView points={points} onPick={onPick} focus={focus} fitSignal={`${tab}-${fit}`} />
        <aside>
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'check'} onClick={() => setTab('check')}>Check one target</button>
            <button role="tab" aria-selected={tab === 'plan'} onClick={() => setTab('plan')}>Plan several</button>
          </div>
          <div className="panel">
            {tab === 'check'
              ? <CheckPanel {...{ target, setTarget, area, setArea, days, setDays, satNames }} />
              : <PlanPanel {...{ requests, setRequests, days, setDays, satNames }} onBulkChange={() => setFit((n) => n + 1)} />}
          </div>
        </aside>
      </main>
    </div>
  )
}
