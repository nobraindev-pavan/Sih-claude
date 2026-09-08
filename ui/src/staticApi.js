// Serving the console from a pre-solved bundle, with no backend at all.
//
// The solver needs fifteen-odd seconds of CPU per scenario. That is fine on a
// laptop and wrong behind an HTTP request on a free host, so the published demo
// ships the answers instead of the solver. Everything the page can compute
// itself — slicing the timetable by route and day, running the sanction state
// machine — it computes; everything that would need a re-solve was precomputed,
// and where an answer is missing the page says so rather than inventing one.

let cache = null

async function bundle() {
  if (!cache) {
    const res = await fetch(`${import.meta.env.BASE_URL}demo-bundle.json`)
    if (!res.ok) throw new Error('could not load the pre-solved demo bundle')
    cache = await res.json()
  }
  return cache
}

const nearestStop = (stops, v) =>
  stops.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a), stops[0])

function planFor(b, method, params) {
  if (method !== 'optimizer') return b.plans[method]
  const stop = nearestStop(b.setupStops, Number(params.setup))
  return b.setupPlans[String(stop)] ?? b.plans.optimizer
}

// --- sanction workflow, run entirely in the browser -----------------------
// The same state machine as the server's, driven from the table in the bundle
// so the two cannot drift apart.
let wf = null

function initWorkflow(b) {
  if (wf) return wf
  const plan = b.plans.optimizer
  wf = {
    planId: 'static-demo',
    blocks: Object.fromEntries(
      plan.blocks.map((x) => [x.id, { state: 'proposed', sanctionedBy: null }]),
    ),
    events: [{
      id: 'e0', at: Date.now() / 1000, actor: 'SYSTEM', blockId: null,
      from: null, to: null, reasonCode: null, note: '',
      line: `${new Date().toISOString().slice(0, 19).replace('T', ' ')}  SYSTEM   (plan)     proposed  ${plan.blocks.length} block(s) proposed by the optimizer, ${plan.deferred.length} task(s) deferred`,
    }],
  }
  return wf
}

function wfJson(b) {
  const w = initWorkflow(b)
  const counts = {}
  Object.values(w.blocks).forEach((r) => { counts[r.state] = (counts[r.state] ?? 0) + 1 })
  const overrides = {}
  w.events.forEach((e) => {
    if (e.to === 'rejected' && e.reasonCode) {
      overrides[e.reasonCode] = (overrides[e.reasonCode] ?? 0) + 1
    }
  })
  return {
    planId: w.planId, scenario: b.network.name,
    counts: Object.fromEntries(Object.entries(counts).sort()),
    blocks: w.blocks, overrideReasons: overrides,
    reasonCodes: b.workflow.reasonCodes, roles: b.workflow.roles,
    trail: [...w.events].reverse().slice(0, 40),
  }
}

function wfTransition(b, { blockId, toState, actor, note, reasonCode }) {
  const w = initWorkflow(b)
  const rec = w.blocks[blockId]
  if (!rec) throw new Error(`block ${blockId} is not in this plan`)
  const allowed = b.workflow.transitions[rec.state] ?? {}
  if (!(toState in allowed)) {
    throw new Error(
      `${blockId} is ${rec.state}; it cannot move to ${toState}` +
      (Object.keys(allowed).length
        ? ` (only ${Object.keys(allowed).join(', ')})`
        : ' because that is a final state'))
  }
  if (!allowed[toState].includes(actor)) {
    throw new Error(`${actor} cannot move a block from ${rec.state} to ` +
      `${toState} — that is for ${allowed[toState].join(' or ')}`)
  }
  if (toState === 'rejected' && !reasonCode) {
    throw new Error('rejecting a block needs a reason code; an override nobody ' +
      'recorded a reason for teaches us nothing')
  }
  const from = rec.state
  rec.state = toState
  if (toState === 'sanctioned') rec.sanctionedBy = actor
  const when = new Date().toISOString().slice(0, 19).replace('T', ' ')
  w.events.push({
    id: `e${w.events.length}`, at: Date.now() / 1000, actor, blockId,
    from, to: toState, reasonCode: reasonCode ?? null, note: note ?? '',
    line: `${when}  ${actor.padEnd(8)} ${blockId.padEnd(10)} ${from} -> ${toState}` +
      (reasonCode ? `  [${reasonCode}] ${note ?? ''}`.trimEnd() : (note ? `  ${note}` : '')),
  })
  return wfJson(b)
}

function wfBulk(b, { action, actor, note }) {
  const w = initWorkflow(b)
  const from = action === 'review_all' ? 'proposed' : 'under_review'
  const to = action === 'review_all' ? 'under_review' : 'sanctioned'
  Object.entries(w.blocks).forEach(([id, rec]) => {
    if (rec.state === from) {
      try { wfTransition(b, { blockId: id, toState: to, actor, note }) } catch { /* skip */ }
    }
  })
  return wfJson(b)
}

// --- the API surface, matching api.js -------------------------------------

export const staticApi = {
  isStatic: true,

  async scenario(params) {
    const b = await bundle()
    return { network: b.network, methods: b.methods, weights: b.weights,
             precomputed: true, builtAt: b.builtAt, params: b.params }
  },

  async plan(params, method) {
    const b = await bundle()
    return planFor(b, method, params)
  },

  async compare(params) {
    const b = await bundle()
    const labels = Object.fromEntries(b.methods.map((m) => [m.id, m.label]))
    const rows = b.methods.map((m) => planFor(b, m.id, params).metrics)
    return { rows, labels }
  },

  async trainGraph(params, route, day) {
    const b = await bundle()
    const prefix = { MAIN: 'MAIN', BRANCH: 'BRCH', DIV: 'DIV' }[route]
    const sections = b.network.sections.filter((s) => s.id.startsWith(prefix))
    const ids = new Set(sections.map((s) => s.id))
    const lo = day * 1440
    const hi = lo + 1440
    const trains = b.trainPaths
      .map((t) => ({
        ...t,
        segments: t.segments.filter(
          (s) => ids.has(s.sectionId) && s.exit > lo && s.enter < hi),
      }))
      .filter((t) => t.segments.length > 0)
    return {
      route, day, dayStart: lo, sections, trains,
      corridorWindows: b.network.corridorWindows.filter(
        (w) => ids.has(w.sectionId) && w.start < hi && w.end > lo),
    }
  },

  async explain(params, blockId) {
    const b = await bundle()
    const ex = b.explanations[blockId]
    if (!ex) {
      throw new Error('This block is not in the pre-solved plan, so its ' +
        'explanation was not baked in. Run the app locally to explain any block.')
    }
    return ex
  },

  async alternatives(params, taskId) {
    const b = await bundle()
    return { taskId, alternatives: b.alternatives[taskId] ?? [] }
  },

  async counterfactual(params, taskId, blockId) {
    const b = await bundle()
    const cf = b.counterfactuals[`${taskId}|${blockId}`]
    if (cf) return cf
    // Each counterfactual is a full re-solve, so only a curated set could be
    // precomputed. Say that plainly instead of returning a plausible number.
    return {
      taskId, alternative: blockId, possible: null,
      deltaObjective: null, deltaBlocks: null, reasons: [],
      sentence: 'Costing this window means re-solving the whole plan, which ' +
        'this published demo cannot do. Run it locally for any window.',
    }
  },

  async whatIf(params, body) {
    const b = await bundle()
    const r = b.whatIf[body.kind]
    if (!r) throw new Error(`the ${body.kind} scenario was not precomputed`)
    return r
  },

  async rulebook() {
    return (await bundle()).rulebook
  },

  async workflow(params) { return wfJson(await bundle()) },
  async transition(params, body) { return wfTransition(await bundle(), body) },
  async workflowBulk(params, body) { return wfBulk(await bundle(), body) },
}
