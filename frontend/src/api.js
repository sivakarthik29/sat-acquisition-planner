// Thin wrapper around the backend. Errors become readable messages.
async function call(path, options) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error('Cannot reach the planner service. Is the backend running?')
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body.detail
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : `Request failed (${res.status})`)
  }
  return body
}

const post = (path, data) =>
  call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })

export const getSatellites = () => call('/api/satellites')
export const postFeasibility = (data) => post('/api/feasibility', data)
export const postPlan = (data) => post('/api/plan', data)
