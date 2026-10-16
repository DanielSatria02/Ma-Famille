const pad = (value) => String(value).padStart(2, '0')

// Local-time ISO date ("YYYY-MM-DD"), avoiding the UTC shift of toISOString().
export function toIsoDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function parseIsoDate(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function addDays(date, days) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

export function formatLongDate(isoDate) {
  return parseIsoDate(isoDate).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export function formatHour(hour) {
  return `${pad(hour)}:00`
}
