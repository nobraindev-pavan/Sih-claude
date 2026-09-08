import { useMemo } from 'react'

// The time-distance chart. Distance up one axis, time along the other, each
// train a diagonal. Every controller in India reads one daily, so a railway
// person understands the contribution here in three seconds with no
// explanation - which is why this is the hero visual and not a map.

const W = 1120
const H = 470
const PAD = { l: 78, r: 16, t: 26, b: 40 }
const DAY = 1440

const TRAIN_STYLE = {
  VB: ['var(--premium)', 1.9],
  RAJ: ['var(--premium)', 1.9],
  MEX: ['var(--express)', 1.4],
  PASS: ['var(--slow)', 1.1],
  MEMU: ['var(--slow)', 1.1],
  FRT: ['var(--freight)', 1.0],
}
const BLOCK_FILL = {
  corridor: 'var(--ok)',
  gap: 'var(--warn)',
  traffic: 'var(--bad)',
}

export default function TrainGraph({ graph, blocks, selectedId, onSelect }) {
  const { sections, trains, corridorWindows, day, dayStart } = graph

  const scale = useMemo(() => {
    const kmLo = Math.min(...sections.map((s) => Math.min(s.kmFrom, s.kmTo)))
    const kmHi = Math.max(...sections.map((s) => Math.max(s.kmFrom, s.kmTo)))
    const plotW = W - PAD.l - PAD.r
    const plotH = H - PAD.t - PAD.b
    return {
      kmLo,
      kmHi,
      x: (m) => PAD.l + (Math.min(Math.max(m, dayStart), dayStart + DAY) - dayStart) / DAY * plotW,
      y: (km) => PAD.t + ((km - kmLo) / Math.max(1e-6, kmHi - kmLo)) * plotH,
    }
  }, [sections, dayStart])

  const stations = useMemo(() => {
    const m = new Map()
    sections.forEach((s) => {
      m.set(s.kmFrom, s.from)
      m.set(s.kmTo, s.to)
    })
    return [...m.entries()].sort((a, b) => a[0] - b[0])
  }, [sections])

  const sectionById = useMemo(
    () => Object.fromEntries(sections.map((s) => [s.id, s])),
    [sections],
  )
  const onThisDay = blocks.filter(
    (b) => sectionById[b.sectionId] && b.end > dayStart && b.start < dayStart + DAY,
  )

  return (
    <div className="graph">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Time-distance chart for day ${day}: ${trains.length} train paths and ${onThisDay.length} maintenance blocks.`}>
        {/* mandated corridor windows - the timetable is built around these */}
        {corridorWindows.map((w, i) => {
          const s = sectionById[w.sectionId]
          if (!s) return null
          const y0 = scale.y(Math.min(s.kmFrom, s.kmTo))
          const y1 = scale.y(Math.max(s.kmFrom, s.kmTo))
          return (
            <rect key={`c${i}`} x={scale.x(w.start)} y={y0}
              width={Math.max(1, scale.x(w.end) - scale.x(w.start))}
              height={Math.max(2, y1 - y0)} fill="var(--accent-soft)" />
          )
        })}

        {/* station lines */}
        {stations.map(([km, code]) => (
          <g key={code + km}>
            <line x1={PAD.l} y1={scale.y(km)} x2={W - PAD.r} y2={scale.y(km)}
              stroke="var(--rule)" strokeWidth="1" />
            <text x={PAD.l - 8} y={scale.y(km) + 3.5} fontSize="10"
              fill="var(--dim)" textAnchor="end">
              {code} <tspan opacity="0.6">{km}</tspan>
            </text>
          </g>
        ))}

        {/* hour grid */}
        {Array.from({ length: 13 }, (_, i) => i * 2).map((h) => (
          <g key={h}>
            <line x1={scale.x(dayStart + h * 60)} y1={PAD.t}
              x2={scale.x(dayStart + h * 60)} y2={H - PAD.b}
              stroke="var(--rule)" strokeWidth="1" strokeDasharray="2 4" />
            <text x={scale.x(dayStart + h * 60)} y={H - PAD.b + 15} fontSize="10"
              fill="var(--dim)" textAnchor="middle">
              {String(h).padStart(2, '0')}
            </text>
          </g>
        ))}
        <text x={16} y={H / 2} fontSize="10" fill="var(--dim)" textAnchor="middle"
          transform={`rotate(-90 16 ${H / 2})`}>KM POST</text>

        {/* train paths */}
        {trains.map((t) => {
          const [colour, width] = TRAIN_STYLE[t.trainClass] ?? ['var(--slow)', 1]
          const pts = []
          t.segments.forEach((seg) => {
            const s = sectionById[seg.sectionId]
            if (!s) return
            const [a, b] = t.direction === 'DN' ? [s.kmFrom, s.kmTo] : [s.kmTo, s.kmFrom]
            pts.push(`${scale.x(seg.enter)},${scale.y(a)}`)
            pts.push(`${scale.x(seg.exit)},${scale.y(b)}`)
          })
          if (pts.length < 2) return null
          return (
            <polyline key={t.number} points={pts.join(' ')} fill="none"
              stroke={colour} strokeWidth={width} strokeLinejoin="round" opacity="0.72">
              <title>{`${t.number} · ${t.trainClass} · ${t.direction}`}</title>
            </polyline>
          )
        })}

        {/* blocks */}
        {onThisDay.map((b) => {
          const s = sectionById[b.sectionId]
          const y0 = Math.min(scale.y(s.kmFrom), scale.y(s.kmTo))
          const y1 = Math.max(scale.y(s.kmFrom), scale.y(s.kmTo))
          const x0 = scale.x(b.start)
          const w = Math.max(3, scale.x(b.end) - x0)
          const h = Math.max(7, y1 - y0)
          const label = b.departments.join('+')
          return (
            <g key={b.id}>
              <rect className={`blockrect${selectedId === b.id ? ' sel' : ''}`}
                x={x0} y={y0} width={w} height={h}
                fill={BLOCK_FILL[b.windowSource] ?? 'var(--warn)'} fillOpacity="0.9"
                stroke="var(--panel)" strokeWidth="0.8"
                onClick={() => onSelect(b.id)}>
                <title>
                  {`${b.sectionId} ${b.startLabel}-${b.endLabel} · ${label} · ${b.tasks.length} task(s) · train cost ${b.trainCost}`}
                </title>
              </rect>
              {w > 40 && h > 13 && (
                <text x={x0 + w / 2} y={y0 + h / 2 + 3.5} fontSize="9.5"
                  fill="var(--on-block)" fontWeight="600" textAnchor="middle"
                  pointerEvents="none">{label}</text>
              )}
            </g>
          )
        })}
      </svg>

      <div className="legend">
        <span><i style={{ background: 'var(--accent-soft)' }} />mandated corridor window</span>
        <span><i style={{ background: 'var(--ok)' }} />block in corridor</span>
        <span><i style={{ background: 'var(--warn)' }} />block in timetable gap</span>
        <span><i style={{ background: 'var(--bad)' }} />block displacing traffic</span>
        <span><i style={{ background: 'var(--premium)', height: 2 }} />premium</span>
        <span><i style={{ background: 'var(--express)', height: 2 }} />mail/express</span>
        <span><i style={{ background: 'var(--freight)', height: 2 }} />freight</span>
        <span>click a block to see why it was chosen</span>
      </div>
    </div>
  )
}
