import { useState } from 'react'
import { postPlan } from '../api'
import { EXAMPLES, fmtTime, windowFor } from '../format'
import Timeline from './Timeline'

export default function PlanPanel({ requests, setRequests, days, setDays, satNames, onBulkChange }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const update = (id, patch) => setRequests(requests.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const remove = (id) => setRequests(requests.filter((r) => r.id !== id))
  const loadExamples = () => {
    setRequests(EXAMPLES.map((e, i) => ({ ...e, id: `ex${i + 1}` })))
    onBulkChange()
  }

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      const w = windowFor(days)
      const body = await postPlan({
        requests: requests.map((r) => ({ id: r.id, name: r.name, lat: r.lat, lon: r.lon, area_km2: Number(r.area_km2), priority: Number(r.priority) })),
        ...w,
      })
      setResult(body)
    } catch (e) {
      setError(e.message)
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const g = result?.solutions.greedy
  const o = result?.solutions.optimized
  const gain = result ? o.total_value - g.total_value : 0

  return (
    <div className="stack">
      <section className="stack">
        <h2>Requests</h2>
        {requests.length === 0 && <p className="hint">Click the map to add targets, or load an example set.</p>}
        {requests.length > 0 && (
          <ul className="reqs">
            {requests.map((r) => (
              <li key={r.id}>
                <input aria-label="Name" className="name" value={r.name} onChange={(e) => update(r.id, { name: e.target.value })} />
                <input aria-label="Area in square kilometres" type="number" min="1" value={r.area_km2} onChange={(e) => update(r.id, { area_km2: e.target.value })} />
                <select aria-label="Priority" value={r.priority} onChange={(e) => update(r.id, { priority: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((p) => <option key={p} value={p}>P{p}</option>)}
                </select>
                <button className="icon" aria-label={`Remove ${r.name}`} onClick={() => remove(r.id)}>×</button>
              </li>
            ))}
          </ul>
        )}
        <div className="row">
          <button className="ghost" onClick={loadExamples}>Load example set</button>
          {requests.length > 0 && <button className="ghost" onClick={() => setRequests([])}>Clear</button>}
        </div>
        <div className="row">
          <label>Window
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? 's' : ''} from now</option>)}
            </select>
          </label>
          <button className="primary" disabled={!requests.length || busy} onClick={run}>{busy ? 'Planning…' : 'Run planner'}</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {result && (
        <section className="stack" aria-live="polite">
          <h2>Optimizer vs greedy</h2>
          <div className="compare">
            <div><span>Greedy</span><strong>{g.captured}</strong><em>captured · value {g.total_value} · {g.runtime_ms} ms</em></div>
            <div className="best"><span>Optimizer</span><strong>{o.captured}</strong><em>captured · value {o.total_value} · {o.runtime_ms} ms · {o.status.toLowerCase()}</em></div>
          </div>
          <p className="hint">
            {gain > 0
              ? `The optimizer found a plan worth ${gain} more than greedy (priority counts 100 per level, so a small gain can still mean an extra capture).`
              : 'Both found the same value: when requests rarely clash, greedy is already optimal. Shorter windows create more clashes, so try 3 days.'}
            {' '}{result.candidates} candidate passes considered.
          </p>

          <h2>Schedule</h2>
          <Timeline captures={result.captures} window={result.window} satNames={satNames} />
          {result.captures.length > 0 && (
            <table>
              <thead><tr><th>Time</th><th>Target</th><th>Satellite</th><th>Off-nadir</th></tr></thead>
              <tbody>
                {result.captures.map((c, i) => (
                  <tr key={i}><td>{fmtTime(c.time)}</td><td>{c.name}</td><td>{c.sat_name}</td><td>{c.off_nadir_deg}°</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {result.unscheduled.length > 0 && (
            <>
              <h2>Not scheduled</h2>
              <ul className="plain">
                {result.unscheduled.map((u) => <li key={u.request_id}><strong>{u.name}</strong> {u.reason}</li>)}
              </ul>
            </>
          )}

          <h2>Commands</h2>
          <div className={`verdict ${result.validation.passed ? 'ok' : 'no'}`}>
            <strong>{result.validation.passed ? 'Validated' : 'Validation failed'}</strong>
            <span>
              {result.validation.checked} commands checked against the dictionary and the operating rules.
              {result.validation.violations.length > 0 && ` ${result.validation.violations.length} finding(s).`}
            </span>
          </div>
          {result.validation.violations.length > 0 && (
            <ul className="plain">
              {result.validation.violations.map((v, i) => <li key={i}><strong>{v.rule}</strong> {v.message}</li>)}
            </ul>
          )}
          <details>
            <summary>Show the command timeline ({result.commands.length})</summary>
            <p className="hint">Notional command set, dictionary v{result.dictionary.version}. It is not Pixxel's real command database.</p>
            <table>
              <thead><tr><th>Time</th><th>Satellite</th><th>Command</th></tr></thead>
              <tbody>
                {result.commands.map((c, i) => (
                  <tr key={i}>
                    <td>{fmtTime(c.time)}</td><td>{c.sat_name}</td>
                    <td>{c.name}{Object.keys(c.params).length > 0 && <span className="params"> {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(', ')}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
      )}
    </div>
  )
}
