import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import BlockDetail from './BlockDetail'
import Sanction from './Sanction'
import TrainGraph from './TrainGraph'
import WhatIf from './WhatIf'

const DEFAULTS = {
  seed: 1, demand: 'normal', days: 7, ml: false, timeLimit: 20,
  train: 1, setup: 500, downtime: 2, overdue: 50, risk: 200, night: 20,
}
const METHODS = [
  ['optimizer', 'SANCHAY optimizer'],
  ['baseline_corridor', 'B2 · corridor policy'],
  ['baseline_fcfs', 'B1 · uncoordinated'],
  ['greedy_coordinated', 'greedy coordination'],
]
const KPI = [
  ['n_blocks', 'separate blocks', 'down'],
  ['n_coordinated_blocks', 'coordinated', 'up'],
  ['train_cost', 'train disruption', 'down'],
  ['completion_pct', 'work done %', 'up'],
  ['critical_completion_pct', 'critical done %', 'up'],
  ['total_block_minutes', 'block minutes', 'down'],
]

export default function App() {
  const [draft, setDraft] = useState(DEFAULTS)
  const [params, setParams] = useState(DEFAULTS)
  const [meta, setMeta] = useState(null)
  const [method, setMethod] = useState('optimizer')
  const [plan, setPlan] = useState(null)
  const [compare, setCompare] = useState(null)
  const [graph, setGraph] = useState(null)
  const [route, setRoute] = useState('MAIN')
  const [day, setDay] = useState(1)
  const [selected, setSelected] = useState(null)
  const [whatIfPlan, setWhatIfPlan] = useState(null)
  const [busy, setBusy] = useState(true)
  const [err, setErr] = useState(null)

  const dirty = JSON.stringify(draft) !== JSON.stringify(params)

  const load = useCallback(async () => {
    setBusy(true); setErr(null); setSelected(null); setWhatIfPlan(null)
    try {
      const [m, p, c] = await Promise.all([
        api.scenario(params), api.plan(params, method), api.compare(params),
      ])
      setMeta(m); setPlan(p); setCompare(c)
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }, [params, method])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    api.trainGraph(params, route, day).then(setGraph).catch((e) => setErr(String(e)))
  }, [params, route, day])

  const rows = compare?.rows ?? []
  const mine = rows.find((r) => r.method === 'optimizer')
  const corridorRow = rows.find((r) => r.method === 'baseline_corridor')

  // The what-if result replaces the drawn plan, so the chart shows what changed.
  const shownBlocks = whatIfPlan?.blocks ?? plan?.blocks ?? []
  const selectedBlock = useMemo(
    () => shownBlocks.find((b) => b.id === selected) ?? null,
    [shownBlocks, selected],
  )

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked
      : e.target.type === 'number' || e.target.type === 'range' ? Number(e.target.value)
        : e.target.value
    setDraft((d) => ({ ...d, [k]: v }))
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>SANCHAY</h1>
          <span className="sub">
            Coordinated railway maintenance block planning · SIH26027 ·
            {meta ? ` ${meta.network.name}` : ' loading'}
          </span>
        </div>
        <p className="disclaimer">
          Simulated data throughout. Schema-compatible with TMS, SMMS, TDMS and
          COA; it does not come from them, and nothing here is a measured
          railway result. Decision support — a planner sanctions every block.
        </p>

        <div className="controls">
          <div className="field">
            <label htmlFor="seed">scenario seed</label>
            <input id="seed" type="number" min="1" max="200" value={draft.seed} onChange={set('seed')} />
          </div>
          <div className="field">
            <label htmlFor="demand">maintenance demand</label>
            <select id="demand" value={draft.demand} onChange={set('demand')}>
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="surge">surge</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="tl">solver limit (s)</label>
            <input id="tl" type="number" min="1" max="60" value={draft.timeLimit} onChange={set('timeLimit')} />
          </div>
          <div className="field">
            <label htmlFor="setup">block setup cost {draft.setup}</label>
            <input id="setup" type="range" min="0" max="2000" step="50"
              value={draft.setup} onChange={set('setup')} />
          </div>
          <div className="field">
            <label htmlFor="traincost">train disruption weight {draft.train}</label>
            <input id="traincost" type="range" min="0" max="10" step="1"
              value={draft.train} onChange={set('train')} />
          </div>
          <div className="field">
            <label>&nbsp;</label>
            <label className="toggle">
              <input type="checkbox" checked={draft.ml} onChange={set('ml')} />
              plan to ML P80 durations
            </label>
          </div>
          <button onClick={() => setParams(draft)} disabled={busy || !dirty}>
            {busy ? 'solving…' : dirty ? 'Re-solve' : 'Up to date'}
          </button>
        </div>
        {meta?.network.mlNote && <p className="muted" style={{ marginTop: 8 }}>{meta.network.mlNote}</p>}
        {err && <p className="err">{err}</p>}
      </header>

      {mine && (
        <div className="kpis panel" style={{ padding: 0, border: 0 }}>
          {KPI.map(([k, label, dir]) => {
            const v = mine[k]
            const base = corridorRow?.[k]
            const delta = base == null ? null : v - base
            const good = delta == null ? null
              : dir === 'down' ? delta < 0 : delta > 0
            return (
              <div className="kpi" key={k}>
                <div className="k">{label}</div>
                <div className="v tnum">{Number(v).toFixed(k.endsWith('pct') ? 1 : 0)}</div>
                {delta != null && (
                  <div className={`d ${good ? 'good' : delta === 0 ? '' : 'bad'}`}>
                    {delta > 0 ? '+' : ''}{delta.toFixed(k.endsWith('pct') ? 1 : 0)} vs corridor policy
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="grid">
        <div>
          <div className="panel">
            <h2>
              <span>Time–distance chart{whatIfPlan ? ' · what-if plan' : ''}</span>
              <span className="note">
                <select value={method} onChange={(e) => setMethod(e.target.value)}
                  disabled={!!whatIfPlan} style={{ marginRight: 8 }}>
                  {METHODS.map(([id, l]) => <option key={id} value={id}>{l}</option>)}
                </select>
                <select value={route} onChange={(e) => setRoute(e.target.value)}
                  style={{ marginRight: 8 }}>
                  <option value="MAIN">main corridor</option>
                  <option value="BRANCH">branch (single line)</option>
                  <option value="DIV">diversion</option>
                </select>
                <select value={day} onChange={(e) => setDay(Number(e.target.value))}>
                  {Array.from({ length: params.days }, (_, i) => (
                    <option key={i} value={i}>day {i}</option>
                  ))}
                </select>
              </span>
            </h2>
            {graph
              ? <TrainGraph graph={graph} blocks={shownBlocks} selectedId={selected}
                  onSelect={setSelected} />
              : <p className="muted"><span className="spin" />drawing…</p>}
          </div>

          <div className="panel">
            <h2>
              <span>Method comparison</span>
              <span className="note">
                {plan && `solver ${plan.solverStatus.toLowerCase()} · ${plan.solveSeconds}s · gap ${plan.gapPct}%`}
              </span>
            </h2>
            <div className="tw">
              <table>
                <thead>
                  <tr>
                    <th>method</th><th>blocks</th><th>coordinated</th>
                    <th>block min</th><th>train cost</th><th>work done</th>
                    <th>critical</th><th>utilisation</th><th>objective</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.method} className={r.method === 'optimizer' ? 'me' : ''}>
                      <td>{compare.labels[r.method]}</td>
                      <td>{r.n_blocks}</td>
                      <td>{r.n_coordinated_blocks}</td>
                      <td>{r.total_block_minutes.toLocaleString()}</td>
                      <td>{r.train_cost.toFixed(0)}</td>
                      <td>{r.completion_pct.toFixed(1)}%</td>
                      <td>{r.critical_completion_pct.toFixed(1)}%</td>
                      <td>{r.utilisation_pct.toFixed(0)}%</td>
                      <td>{r.objective.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ marginTop: 10 }}>
              Every method draws from the same candidate blocks and obeys the same
              safety rulebook — a baseline that cheats would invalidate the whole
              comparison. Utilisation can exceed 100% because worksites far enough
              apart in kilometres run in parallel inside one block.
              {plan?.valid?.length ? ` ⚠ ${plan.valid.length} constraint violation(s).` : ' All plans pass the hard-constraint audit.'}
            </p>
          </div>
        </div>

        <div>
          <div className="panel">
            <h2><span>Why this block?</span></h2>
            <BlockDetail params={params} block={selectedBlock} />
          </div>

          <div className="panel">
            <h2>
              <span>Sanction</span>
              <span className="note">a human approves every block</span>
            </h2>
            <Sanction params={params} block={selectedBlock} />
          </div>

          <div className="panel">
            <h2><span>What if…</span></h2>
            <WhatIf params={params} onResult={(r) => { setWhatIfPlan(r); setSelected(null) }} />
          </div>

          {plan && plan.deferred.length > 0 && (
            <div className="panel">
              <h2>
                <span>Deferred to next period</span>
                <span className="note">{plan.deferred.length} task(s)</span>
              </h2>
              <p className="muted">
                Not everything fits. Rather than fail, the plan says explicitly what
                it could not accommodate — highest priority first.
              </p>
              <ul className="tasklist">
                {[...plan.deferred].sort((a, b) => b.priority - a.priority)
                  .slice(0, 8).map((t) => (
                    <li key={t.id}>
                      <div className="row">
                        <span><code>{t.id}</code> {t.name}</span>
                        <span className={`pill ${t.severity}`}>{t.severity}</span>
                      </div>
                      <div className="meta">{t.dept} · due {t.dueLabel} · priority {t.priority.toFixed(1)}</div>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
