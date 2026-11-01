// A spectral ramp (violet to red), one hue per satellite, like the bands of a hyperspectral image.
export const SPECTRUM = ['#6D4AFF', '#2F7DE1', '#12A5A0', '#5FB04A', '#E6A700', '#E4572E']

export const satColor = (names, name) => SPECTRUM[Math.max(0, names.indexOf(name)) % SPECTRUM.length]

export const fmtTime = (iso) =>
  new Date(iso).toLocaleString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC'

export const pct = (p) => `${Math.round(p * 100)}%`

// The window always starts now, so the live orbit data is as fresh as it can be.
export const windowFor = (days) => {
  const start = new Date()
  start.setSeconds(0, 0)
  return { start: start.toISOString(), end: new Date(start.getTime() + days * 864e5).toISOString() }
}

export const EXAMPLES = [
  { name: 'Bengaluru', lat: 12.97, lon: 77.59, area_km2: 400, priority: 3 },
  { name: 'Mysuru', lat: 12.3, lon: 76.64, area_km2: 300, priority: 5 },
  { name: 'Tumakuru', lat: 13.34, lon: 77.1, area_km2: 250, priority: 2 },
  { name: 'Mandya', lat: 12.52, lon: 76.9, area_km2: 350, priority: 4 },
  { name: 'Chennai', lat: 13.08, lon: 80.27, area_km2: 500, priority: 3 },
  { name: 'Hyderabad', lat: 17.38, lon: 78.48, area_km2: 600, priority: 4 },
  { name: 'Pune', lat: 18.52, lon: 73.86, area_km2: 450, priority: 2 },
  { name: 'Nagpur', lat: 21.15, lon: 79.09, area_km2: 800, priority: 5 },
]
