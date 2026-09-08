# Deploying SANCHAY

Two different things can be deployed, and they have different homes. Choosing
wrongly here is the commonest way this kind of project ends up broken in front
of an audience.

| | what it is | where it goes |
|---|---|---|
| **The demo** | the console with every plan pre-solved and shipped as data — no server, no solve | GitHub Pages, Vercel, Netlify, any static host |
| **The app** | FastAPI + the solver, re-planning on demand | a container host: Render, Fly.io, Railway, Cloud Run |

## Why the app cannot go on Vercel or Netlify

Not a preference — two hard limits:

- **Execution time.** A solve takes 15–20 seconds. Vercel's Hobby functions cap
  at 10 s and Netlify's at 10 s (26 s background). The request dies before the
  plan exists.
- **Bundle size.** OR-Tools alone is over 100 MB; with LightGBM, NumPy and
  SciPy the dependency set is comfortably past Vercel's ~250 MB unzipped limit.

Serverless is the wrong shape for a CPU-bound optimiser that holds solved state
in memory. Put the *demo* there — that is exactly what those platforms are good
at — and the app on something that runs a container.

## The demo → GitHub Pages

Already wired. `.github/workflows/pages.yml` builds `ui/` in static mode and
publishes it on every push that touches the frontend.

One-time setup, in the repository: **Settings → Pages → Source: GitHub
Actions**. Then push, or run the workflow by hand from the Actions tab. The URL
is `https://<user>.github.io/<repo>/`.

The pre-solved bundle is **committed**, not built in CI, because building it
runs the solver for several minutes. Regenerate it deliberately:

```bash
python -m sanchay export --time-limit 20     # ~8 minutes; writes ui/public/demo-bundle.json
cd ui && VITE_STATIC=1 npm run build         # check it locally first
git add ui/public/demo-bundle.json && git commit -m "chore: refresh the demo bundle"
```

## The demo → Vercel

`vercel.json` is in place; the build is `VITE_STATIC=1 npm run build` out of
`ui/`. Import the repository at [vercel.com/new](https://vercel.com/new) and
accept the detected settings — no environment variables, no tokens. It is a
static site, so the Hobby tier is genuinely enough.

From a terminal instead: `npx vercel --prod` (it will ask you to log in once).

## The app → Render

`render.yaml` is a blueprint: **New → Blueprint** at
[render.com](https://dashboard.render.com/), point it at the repository.

Free instances have 512 MB and shared CPU, and sleep when idle — so the first
request after a sleep pays a cold start *and* a solve, which is a bad way to
begin a demo. Use `starter`, and keep a tab open beforehand.

## The app → Fly.io

```bash
fly launch --no-deploy      # reads fly.toml, keeps its settings
fly deploy
```

`fly.toml` asks for `shared-cpu-2x` and 1 GB, in `bom` (Mumbai). 256 MB will not
hold OR-Tools plus a cached scenario. `min_machines_running = 1` costs a little
and avoids a cold start in front of judges.

## The app → any container host

```bash
docker build -t sanchay .
docker run -p 8000:8000 sanchay      # http://localhost:8000/
```

The image is roughly 700 MB, most of it the scientific stack. It serves the API
and the built console from one origin, so there is no CORS to configure.

## Things that will bite you

**One worker, not four.** A solve pins a core and caches its result in process
memory. Several workers means several copies of the same solve competing for the
same CPU, and a worse plan winning — the cache stampede in
[`docs/build-notes.md`](docs/build-notes.md) §11. `WEB_CONCURRENCY=1` is set
everywhere for this reason.

**Raise the proxy timeout.** The first request for a scenario blocks for the
solver's time limit plus model training. Anything with a 30-second gateway
timeout needs raising, or lower `timeLimit` in the UI.

**Memory grows with scenarios.** `PlanningService` keeps the last eight solved
worlds. Each is a few tens of MB. On a 512 MB instance, lower `max_sessions`.

**Nothing here is authenticated.** There is no login, and the role dropdown is a
dropdown, not an identity. Fine for a demo on an unlisted URL; not fine for
anything real. Deploy it somewhere you are content for anyone to open.

## What is *not* deployed

The benchmark, the ablations and the model training are offline work. They run
on a laptop or in CI and write to `results/`. They are not endpoints and should
not become endpoints — a judge asking "can I see the benchmark?" should be shown
[`results/`](results/), which is reproducible, not a live button that spends two
minutes of someone's CPU.
