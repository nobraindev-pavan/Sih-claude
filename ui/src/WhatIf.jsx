import { useState } from 'react'
import { api } from './api'

// Change an assumption, re-optimise, and show what moved. The previous plan
// anchors the objective, so the answer is the smallest change that absorbs the
// disruption rather than a different optimum - which is what a planner who has
// already circulated a block plan actually wants.

const SCENARIOS = [
  { kind: 'freight', label: '+10 freight paths', body: { kind: 'freight', n: 10 },
    blurb: 'Extra rakes routed through the corridor window.' },
  { kind: 'crew', label: 'S&T gang unavailable', body: { kind: 'crew', n: 1, crewType: 'signal_team' },
    blurb: 'One signal team off - sick, or pulled to a failure.' },
  { kind: 'urgent', label: 'New critical defect', body: { kind: 'urgent', section: 'MAIN05' },
    blurb: 'A rail defect reported today, due in two days.' },
  { kind: 'durations', label: 'Monsoon: work +25% longer', body: { kind: 'durations', factor: 1.25 },
    blurb: 'Everything runs long.' },
]

export default function WhatIf({ params, onResult }) {
  const [active, setActive] = useState(null)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const run = async (s) => {
    setActive(s.kind); setBusy(true); setErr(null); setRes(null)
    try {
      // no `seconds`: the backend reuses the base plan's budget, so the
      // diff reports the perturbation rather than extra search time
      const r = await api.whatIf(params, s.body)
      setRes(r)
      onResult?.(r)
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const reset = () => { setActive(null); setRes(null); onResult?.(null) }

  return (
    <>
      <div className="wi">
        {SCENARIOS.map((s) => (
          <button key={s.kind} className={active === s.kind ? 'on' : ''}
            disabled={busy} onClick={() => run(s)} title={s.blurb}>
            {s.label}
          </button>
        ))}
        {res && <button className="ghost" onClick={reset}>back to base plan</button>}
      </div>

      {busy && <p className="muted" style={{ marginTop: 10 }}>
        <span className="spin" />re-optimising the whole plan…</p>}
      {err && <p className="err">{err}</p>}

      {res && (
        <>
          <p className="muted" style={{ marginTop: 11 }}>{res.detail}</p>
          <div className="diffgrid">
            <div>
              <div className="k">blocks</div>
              <div className="v">{res.blocksBefore} → {res.blocksAfter}</div>
            </div>
            <div>
              <div className="k">deferred</div>
              <div className="v">{res.deferredBefore} → {res.deferredAfter}</div>
            </div>
            <div>
              <div className="k">train cost</div>
              <div className="v">{res.trainCostBefore.toFixed(0)} → {res.trainCostAfter.toFixed(0)}</div>
            </div>
          </div>
          <p className="muted" style={{ marginTop: 10 }}>
            {res.tasksMoved.length} task(s) moved to a different window.
            {res.newlyDeferred.length > 0 && ' The plan can no longer fit:'}
          </p>
          {res.newlyDeferred.length > 0 && (
            <ul className="tasklist">
              {res.newlyDeferred.slice(0, 6).map((t) => (
                <li key={t.id}>
                  <div className="row">
                    <span><code>{t.id}</code> {t.name}</span>
                    <span className={`pill ${t.severity}`}>{t.severity}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted" style={{ marginTop: 8, fontSize: 11.5 }}>
            The chart above now shows the re-optimised plan.
          </p>
        </>
      )}
    </>
  )
}
