import { useEffect, useState } from 'react'
import { api } from './api'

// The sanction workflow. The deliverable in this domain is not a chart — it is
// a sanctioned block plan with a record of who approved what and why. Nothing
// here decides anything; it records decisions people make.

const NEXT = {
  proposed: ['under_review', 'rejected'],
  under_review: ['sanctioned', 'rejected'],
  sanctioned: ['issued', 'rejected'],
  issued: ['executed'],
  executed: ['returned'],
}
const STATE_COLOUR = {
  proposed: 'routine', under_review: 'important', sanctioned: 'corridor',
  issued: 'corridor', executed: 'corridor', returned: 'routine',
  rejected: 'critical',
}

export default function Sanction({ params, block }) {
  const [wf, setWf] = useState(null)
  const [actor, setActor] = useState('DOM')
  const [reason, setReason] = useState('resources')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = () => api.workflow(params).then(setWf).catch((e) => setErr(String(e)))
  useEffect(() => { setErr(null); refresh() }, [JSON.stringify(params)])

  if (!wf) return <p className="muted">{err ? <span className="err">{err}</span> : 'loading…'}</p>

  const state = block ? wf.blocks[block.id]?.state : null
  const act = async (toState) => {
    setBusy(true); setErr(null)
    try {
      const body = { blockId: block.id, toState, actor, note }
      if (toState === 'rejected') body.reasonCode = reason
      setWf(await api.transition(params, body))
      setNote('')
    } catch (e) {
      // 409 means the plan is not in a state where this move is allowed —
      // a real answer, not a crash. Show it.
      setErr(String(e).replace(/^Error: /, '').slice(0, 200))
    } finally { setBusy(false) }
  }
  const bulk = async (action) => {
    setBusy(true); setErr(null)
    try { setWf(await api.workflowBulk(params, { action, actor, note })) }
    catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="controls" style={{ marginTop: 0, gap: 10 }}>
        <div className="field">
          <label htmlFor="actor">acting as</label>
          <select id="actor" value={actor} onChange={(e) => setActor(e.target.value)}>
            {Object.entries(wf.roles).filter(([k]) => k !== 'SYSTEM')
              .map(([k, v]) => <option key={k} value={k} title={v}>{k}</option>)}
          </select>
        </div>
        <button className="ghost" disabled={busy} onClick={() => bulk('review_all')}>
          Open all for review
        </button>
        <button disabled={busy} onClick={() => bulk('sanction_all')}>
          Sanction reviewed
        </button>
      </div>
      <p className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
        {wf.roles[actor]}
      </p>

      <div className="wi" style={{ marginTop: 10 }}>
        {Object.entries(wf.counts).map(([s, n]) => (
          <span key={s} className={`pill ${STATE_COLOUR[s] ?? 'dept'}`}>
            {s.replace('_', ' ')} {n}
          </span>
        ))}
      </div>

      {block ? (
        <>
          <p style={{ marginTop: 13, marginBottom: 6 }}>
            <code>{block.id}</code> · {block.sectionId} {block.startLabel}–{block.endLabel}
            {' '}<span className={`pill ${STATE_COLOUR[state] ?? 'dept'}`}>{state}</span>
          </p>
          {(NEXT[state] ?? []).includes('rejected') && (
            <div className="field" style={{ marginBottom: 8 }}>
              <label htmlFor="reason">reason, if rejecting</label>
              <select id="reason" value={reason} onChange={(e) => setReason(e.target.value)}>
                {Object.entries(wf.reasonCodes).map(([k, v]) =>
                  <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          )}
          <input type="text" placeholder="note (optional)" value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ width: '100%', marginBottom: 8, padding: '5px 8px',
                     border: '1px solid var(--rule-2)', borderRadius: 3,
                     background: 'var(--panel)', color: 'var(--ink)', font: 'inherit' }} />
          <div className="wi">
            {(NEXT[state] ?? []).map((t) => (
              <button key={t} disabled={busy} onClick={() => act(t)}
                className={t === 'rejected' ? 'ghost' : ''}>
                {t.replace('_', ' ')}
              </button>
            ))}
            {!NEXT[state]?.length && <span className="muted">final state</span>}
          </div>
        </>
      ) : (
        <p className="muted" style={{ marginTop: 12 }}>
          Select a block on the chart to move it through the sanction workflow.
        </p>
      )}

      {err && <p className="err" style={{ marginTop: 8 }}>{err}</p>}

      {Object.keys(wf.overrideReasons).length > 0 && (
        <>
          <p className="muted" style={{ marginTop: 14, marginBottom: 4 }}>
            Why our recommendations were overridden — the distribution that makes
            the trail worth keeping:
          </p>
          {Object.entries(wf.overrideReasons).map(([k, n]) => (
            <div className="costbar" key={k}>
              <span className="muted">{wf.reasonCodes[k]}</span>
              <span className="track"><span className="fill" style={{ width: '100%' }} /></span>
              <span className="n">{n}</span>
            </div>
          ))}
        </>
      )}

      <p className="muted" style={{ marginTop: 14, marginBottom: 4 }}>Audit trail</p>
      <ul className="tasklist">
        {wf.trail.slice(0, 8).map((e) => (
          <li key={e.id}><span className="meta mono" style={{ fontSize: 11 }}>{e.line}</span></li>
        ))}
      </ul>
    </>
  )
}
