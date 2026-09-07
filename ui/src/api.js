// Every request carries the scenario parameters, because the backend caches a
// solved world per parameter set. Changing a weight or the seed is therefore a
// different world, and the first request for it pays the solve time.

const qs = (p) =>
  new URLSearchParams(
    Object.fromEntries(Object.entries(p).map(([k, v]) => [k, String(v)])),
  ).toString()

async function get(path, params) {
  const res = await fetch(`/api${path}?${qs(params)}`)
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  return res.json()
}

async function post(path, params, body) {
  const res = await fetch(`/api${path}?${qs(params)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  return res.json()
}

export const api = {
  scenario: (p) => get('/scenario', p),
  plan: (p, method) => get('/plan', { ...p, method }),
  compare: (p) => get('/compare', p),
  trainGraph: (p, route, day) => get('/traingraph', { ...p, route, day }),
  explain: (p, blockId) => get('/explain', { ...p, blockId }),
  alternatives: (p, taskId) => get('/alternatives', { ...p, taskId }),
  counterfactual: (p, taskId, blockId) =>
    post('/counterfactual', p, { taskId, blockId }),
  whatIf: (p, body) => post('/whatif', p, body),
  rulebook: () => get('/rulebook', {}),
  workflow: (p) => get('/workflow', p),
  transition: (p, body) => post('/workflow/transition', p, body),
  workflowBulk: (p, body) => post('/workflow/bulk', p, body),
}
