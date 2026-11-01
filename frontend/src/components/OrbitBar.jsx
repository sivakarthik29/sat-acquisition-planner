import { satColor } from '../format'

// Shows where the orbit data came from and checks each satellite against Pixxel's published orbit.
export default function OrbitBar({ info, satNames }) {
  if (!info) return <div className="pill">Loading orbit data…</div>
  const demo = info.source === 'demo'
  const [lo, hi] = info.published.crossing_local_time_h
  const label = demo ? 'Synthetic demo orbits' : info.source === 'live' ? 'Live orbit data' : 'Cached orbit data'

  return (
    <details className="orbit">
      <summary className={`pill ${demo ? 'warn' : ''}`}>
        <span className="live-dot" />{label} · {info.satellites.length} satellites
      </summary>
      <div className="popover">
        <p className="hint">{info.note}{demo && ' These are not real satellites.'}</p>
        <table>
          <thead>
            <tr><th>Satellite</th><th>Altitude</th><th>Crossing</th><th>Age</th></tr>
          </thead>
          <tbody>
            {info.satellites.map((s) => {
              const altOff = Math.abs(s.altitude_km - info.published.altitude_km)
              const inWindow = s.descending_crossing_local_h !== null && s.descending_crossing_local_h >= lo && s.descending_crossing_local_h <= hi
              return (
                <tr key={s.norad_id}>
                  <td><span className="dot" style={{ background: satColor(satNames, s.name) }} />{s.name}</td>
                  <td className={altOff > 15 ? 'off' : ''}>{s.altitude_km} km</td>
                  <td className={inWindow ? '' : 'off'}>{s.descending_crossing_local_h?.toFixed(1)} h</td>
                  <td>{s.tle_age_days} d</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="hint">
          Published: {info.published.altitude_km} km altitude, descending node {lo}–{hi} h local time. Values outside that
          are marked; orbit decay or phasing manoeuvres can explain a difference.
        </p>
      </div>
    </details>
  )
}
