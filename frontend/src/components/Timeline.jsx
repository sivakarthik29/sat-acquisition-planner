import { fmtTime, satColor } from '../format'

const W = 560, LANE = 26, TOP = 8, LEFT = 74, RIGHT = 8

// One lane per satellite across the planning window. Each mark is one capture.
export default function Timeline({ captures, window: win, satNames }) {
  const t0 = new Date(win.start).getTime()
  const t1 = new Date(win.end).getTime()
  const x = (iso) => LEFT + ((new Date(iso).getTime() - t0) / (t1 - t0)) * (W - LEFT - RIGHT)
  const lanes = satNames.length
  const H = TOP + lanes * LANE + 22
  const totalDays = Math.round((t1 - t0) / 864e5)
  const step = totalDays > 14 ? 5 : totalDays > 7 ? 2 : 1
  const ticks = []
  for (let d = 0; d <= totalDays; d += step) ticks.push(d)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="timeline" role="img" aria-label={`${captures.length} captures across ${lanes} satellites`}>
      {ticks.map((d) => {
        const gx = LEFT + (d / totalDays) * (W - LEFT - RIGHT)
        return (
          <g key={d}>
            <line x1={gx} x2={gx} y1={TOP} y2={TOP + lanes * LANE} className="grid" />
            <text x={gx} y={H - 6} textAnchor="middle" className="tick">{d === 0 ? 'now' : `+${d}d`}</text>
          </g>
        )
      })}
      {satNames.map((name, i) => (
        <g key={name}>
          <rect x={LEFT} y={TOP + i * LANE + 3} width={W - LEFT - RIGHT} height={LANE - 6} rx="3" className="lane" />
          <text x={LEFT - 8} y={TOP + i * LANE + LANE / 2 + 4} textAnchor="end" className="lane-label">{name}</text>
          {captures.filter((c) => c.sat_name === name).map((c, k) => (
            <rect key={k} x={x(c.time) - 2.5} y={TOP + i * LANE + 4} width="5" height={LANE - 8} rx="2" fill={satColor(satNames, name)}>
              <title>{`${c.name} · ${fmtTime(c.time)} · ${c.off_nadir_deg}° off-nadir`}</title>
            </rect>
          ))}
        </g>
      ))}
    </svg>
  )
}
