import { useState } from 'react'
import { postFeasibility } from '../api'
import { fmtTime, pct, satColor, windowFor } from '../format'

const MARK = { true: '✓', false: '✕' }

export default function CheckPanel({ target, setTarget, area, setArea, days, setDays, satNames }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [all, setAll] = useState(false)

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      setResult(await postFeasibility({ lat: target.lat, lon: target.lon, area_km2: Number(area), ...windowFor(days) }))
      setAll(false)
    } catch (e) {
      setError(e.message)
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const lit = result ? result.opportunities.filter((o) => o.sun_ok).length : 0
  const shown = result ? (all ? result.opportunities : result.opportunities.slice(0, 8)) : []

  return (
    <div className="stack">
      <section className="stack">
        <h2>Target</h2>
        {target ? (
          <div className="row">
            <label>Latitude<input type="number" step="0.01" value={target.lat} onChange={(e) => setTarget({ ...target, lat: Number(e.target.value) })} /></label>
            <label>Longitude<input type="number" step="0.01" value={target.lon} onChange={(e) => setTarget({ ...target, lon: Number(e.target.value) })} /></label>
          </div>
        ) : (
          <p className="hint">Click the map to choose where to image.</p>
        )}
        <div className="row">
          <label>Area (km²)<input type="number" min="1" value={area} onChange={(e) => setArea(e.target.value)} /></label>
          <label>Window
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? 's' : ''} from now</option>)}
            </select>
          </label>
        </div>
        <button className="primary" disabled={!target || busy} onClick={run}>{busy ? 'Checking…' : 'Check feasibility'}</button>
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {result && (
        <section className="stack" aria-live="polite">
          <div className={`verdict ${result.feasible ? 'ok' : 'no'}`}>
            <strong>{result.feasible ? 'Feasible' : 'Not feasible'}</strong>
            <span>
              {result.opportunities.length === 0
                ? 'No usable pass found.'
                : `${result.opportunities.length} pass${result.opportunities.length > 1 ? 'es' : ''} in view, ${lit} in daylight.`}
            </span>
          </div>

          {result.probability !== null && result.feasible && (
            <div className="meter">
              <div className="meter-head">
                <span>Chance of a clear capture in this window</span>
                <strong>{pct(result.probability)}</strong>
              </div>
              <div className="meter-bar"><i style={{ width: pct(result.probability), backgroundSize: `${100 / Math.max(result.probability, 0.02)}% 100%` }} /></div>
              <p className="hint">{result.probability_detail.note} Under 20% cloud counts as clear.</p>
            </div>
          )}
          {result.probability === null && result.feasible && <p className="hint">{result.probability_detail.note}</p>}

          <h2>Why</h2>
          <ul className="checks">
            {result.checks.map((c) => (
              <li key={c.id} className={c.passed ? 'pass' : c.blocking ? 'fail' : 'warn'}>
                <span className="mark" aria-label={c.passed ? 'passed' : 'failed'}>{c.passed ? MARK.true : c.blocking ? MARK.false : '!'}</span>
                <div>
                  <div className="check-title">{c.label}<em className={`chip ${c.source}`}>{c.source}</em></div>
                  <p>{c.detail}</p>
                </div>
              </li>
            ))}
          </ul>

          {result.opportunities.length > 0 && (
            <>
              <h2>Passes</h2>
              <table>
                <thead><tr><th>Time</th><th>Satellite</th><th>Off-nadir</th><th>Sun</th></tr></thead>
                <tbody>
                  {shown.map((o, i) => (
                    <tr key={i} className={o.sun_ok ? '' : 'dim'}>
                      <td>{fmtTime(o.time)}</td>
                      <td><span className="dot" style={{ background: satColor(satNames, o.sat_name) }} />{o.sat_name}</td>
                      <td>{o.off_nadir_deg}°</td>
                      <td>{o.sun_elev_deg}°{o.sun_ok ? '' : ' (too low)'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.opportunities.length > 8 && (
                <button className="link" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${result.opportunities.length}`}</button>
              )}
            </>
          )}
        </section>
      )}
    </div>
  )
}
