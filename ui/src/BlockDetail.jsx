import { useEffect, useState } from 'react'
import { api } from './api'

// "Why this block?" answered from the solver's own cost decomposition, and
// "why not that window?" answered by forcing the alternative and re-solving.
// Neither is generated prose, which matters in a safety-critical domain: an
// explanation that sounds plausible but is not derived from the actual decision
// is worse than none.

export default function BlockDetail({ params, block }) {
  const [ex, setEx] = useState(null)
  const [err, setErr] = useState(null)
  const [taskId, setTaskId] = useState(null)
  const [alts, setAlts] = useState([])
  const [cf, setCf] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!block) return
    setEx(null); setErr(null); setTaskId(null); setAlts([]); setCf(null)
    api.explain(params, block.id).then(setEx).catch((e) => setErr(String(e)))
  }, [block?.id, JSON.stringify(params)])

  if (!block) {
    return <p className="muted">Click a block on the chart to see why the
      optimizer chose that window, and what any alternative would have cost.</p>
  }
  if (err) return <p className="err">{err}</p>
  if (!ex) return <p className="muted"><span className="spin" />reading the plan…</p>

  const max = Math.max(...Object.values(ex.costs), 1)

  const askWhyNot = async (t) => {
    setTaskId(t); setCf(null); setAlts([]); setBusy(true)
    try {
      const r = await api.alternatives(params, t)
      setAlts(r.alternatives)
      if (!r.alternatives.length) {
        // Not an error: a task with a single feasible window genuinely has no
        // alternative to compare against. Saying nothing would look broken.
        setCf({
          possible: false, reasons: [],
          sentence: `${t}: there is no other window on its section that is long ` +
            'enough and still inside its deadline, so this placement is forced.',
        })
      }
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const runCounterfactual = async (blockId) => {
    setBusy(true); setCf(null)
    try {
      setCf(await api.counterfactual(params, taskId, blockId))
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <>
      <p style={{ margin: '0 0 4px', fontWeight: 600 }}>{ex.headline}</p>
      <p style={{ margin: '0 0 12px' }}>
        <span className={`pill ${block.windowSource}`}>{block.windowSource}</span>
        {block.departments.map((d) => <span key={d} className="pill dept">{d}</span>)}
        {block.permits.length > 0 && (
          <span className="muted mono" style={{ fontSize: 11 }}>
            {block.permits.join(' · ').replace(/_/g, ' ')}
          </span>
        )}
      </p>

      {Object.entries(ex.costs).map(([k, v]) => (
        <div className="costbar" key={k}>
          <span className="muted">{k}</span>
          <span className="track">
            <span className="fill" style={{ width: `${(v / max) * 100}%` }} />
          </span>
          <span className="n">{v.toFixed(0)}</span>
        </div>
      ))}
      <div className="costbar" style={{ fontWeight: 600, marginTop: 6 }}>
        <span>total</span><span /><span className="n">{ex.total.toFixed(0)}</span>
      </div>

      <ul className="reasons">
        {ex.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>

      <ul className="tasklist">
        {block.tasks.map((t) => (
          <li key={t.id}>
            <div className="row">
              <span><code>{t.id}</code> {t.name}</span>
              <span className={`pill ${t.severity}`}>{t.severity}</span>
            </div>
            <div className="row">
              <span className="meta">
                KM {t.km} · {t.durationMin} min · due {t.dueLabel}
                {t.overrunProbability > 0 &&
                  ` · ${(t.overrunProbability * 100).toFixed(0)}% overrun risk`}
              </span>
              <button className="linky" onClick={() => askWhyNot(t.id)}>
                why not elsewhere?
              </button>
            </div>
          </li>
        ))}
      </ul>

      {busy && <p className="muted"><span className="spin" />re-solving…</p>}

      {taskId && alts.length > 0 && (
        <>
          <p className="muted" style={{ marginTop: 12 }}>
            Alternative windows for <code>{taskId}</code>. Picking one forces it
            and re-solves the whole plan.
          </p>
          <div className="wi alts">
            {alts.map((a) => (
              <button key={a.id} className="ghost" disabled={busy}
                onClick={() => runCounterfactual(a.id)}>
                {a.startLabel}–{a.endLabel} · {a.windowSource}
              </button>
            ))}
          </div>
        </>
      )}

      {cf && (
        <div className={`cf${cf.possible === null ? ' better'
          : !cf.possible ? ' impossible'
          : (cf.deltaObjective ?? 0) < -1 ? ' better' : ''}`}>
          {cf.sentence}
        </div>
      )}
    </>
  )
}
