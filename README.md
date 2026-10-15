# astro-sdk-services

One small FastAPI HTTP service per astronomy SDK (prototype). Each service exposes a whitelist of 20 tools
(100 in total), with JSON-serialisable inputs/outputs.

| SDK | port | tools |
|---|---|---|
| astropy | 9101 | 20 |
| astroquery | 9102 | 20 (network: SIMBAD/VizieR/Gaia/MPC/IRSA/HEASARC/JPL/NASA) |
| photutils | 9103 | 20 |
| astroplan | 9104 | 20 |
| sunpy | 9105 | 20 |
| euclid | (all-in-one `/euclid`) | 6 (local Euclid Q1 MER cutout; needs EUCLID_MER_ROOT + EUCLID_TILE_INDEX) |

Services bind to `127.0.0.1` only. Behind an Ingress (`https://astro.example.com/<sdk>/...`) the services accept the
path both with and without the `/<sdk>` prefix.

## Run
```bash
python -m venv venv && . venv/bin/activate && pip install -r requirements.txt
python tests/make_fixtures.py            # test fixture files
PY=$(which python) ./run_all.sh          # starts 9101..9105 ; ./run_all.sh stop to stop
```

## API
* `GET /health`, `GET /tools`
* `POST /invoke` body `{"function_name": "...", "arguments": {...}}` -> `{"ok":bool,"result":...,"error":...}`

```bash
curl -s localhost:9101/invoke -H 'content-type: application/json' -d '{"function_name":"astropy_sky_coord_transform_to","arguments":{"_self":{"ra":10.684,"dec":41.269},"frame":"galactic"}}'
curl -s localhost:9101/invoke -H 'content-type: application/json' -d '{"function_name":"astropy_flat_lambda_cdm_luminosity_distance","arguments":{"_self":{"__call__":"astropy.cosmology.FlatLambdaCDM","kwargs":{"H0":70,"Om0":0.3}},"_args":[0.5]}}'
curl -s localhost:9102/invoke -H 'content-type: application/json' -d '{"function_name":"astroquery_simbad_query_object","arguments":{"object_name":"M31"}}'
```

## Codec
* `{"value":1.5,"unit":"km"}` Quantity; `{"ra":..,"dec":..,"unit":"deg","frame":"icrs"}` SkyCoord;
  `{"__type__":"Time","value":..}`, `ndarray`, `Table` (rows), `tuple`, `slice`, `Unit`.
* `{"__call__":"pkg.path","args":[],"kwargs":{}}` builds an object by calling a callable under an allow-listed
  package prefix (astropy/numpy/scipy.ndimage + the service's own SDK); private names are refused.
* Instance methods take the instance in `_self`; positional-only parameters go in `_args`.
* Results: arrays -> lists, Table -> rows, Quantity/Time/SkyCoord -> dicts; other objects -> `{"__type__":"object","handle":"hN","repr":..}`
  (the handle can be passed back as `{"__handle__":"hN"}`).

## Limits
30 s timeout per call (SIGALRM, main thread), 4 GB address-space limit per process. `__call__` may read local files
via `numpy.load` / `astropy.io.fits`: do not expose publicly without sandboxing / auth.

## Verification
`cases/<sdk>.json` hold one reproducible input per tool; `python tests/run_cases.py <sdk>` calls the running service
and writes `results/<sdk>.json`. `tests/build_xlsx.py` renders the tool table. Statuses are recorded as observed.
Candidates in astroquery whose external service timed out (NED, SDSS) were left out of the 20 and are not claimed to work.

## Helm
`helm/astro-sdk-services`: by default (`allInOne: true`) one Deployment + Service `astro-all` (SDK=all) and an Ingress
routing `/astropy`, `/astroquery`, `/photutils`, `/astroplan`, `/sunpy` to it (host `astro.example.com`, placeholder).
`allInOne: false` deploys one Deployment + Service per SDK instead. See `docs/DEPLOY.md`.

## All-in-one (default)
The image defaults to `SDK=all`: one process serves all 6 services under `/<sdk>/{health,tools,invoke,mcp}`, plus `/` and
`/health` listing them. `docker run -p 8000:8000 ghcr.io/aaronyang0628/astro-sdk-services:latest`.
`SDK=<name>` still runs a single SDK.

## Authentication
Auth is **off by default**. Set a non-empty env `API_TOKEN` (Helm: `--set auth.secretName=<secret with key "token">`) to require `Authorization: Bearer <token>` on every endpoint except `/health`.
Regression against a deployed instance: `BASE_URL=https://astro.example.com API_TOKEN=... python tests/run_cases.py <sdk>`.

## MCP (Streamable HTTP)
Every SDK service also speaks MCP at `/mcp` (via Ingress: `/<sdk>/mcp`, e.g. `https://astro.example.com/astropy/mcp`).
Its 20 tools are registered as MCP tools with the same names; `description` is the tool description and `inputSchema`
is generated from the parameter list (`str/int/float/bool/dict/list` map to JSON Schema types, astro objects such as
`SkyCoord`/`Time`/`Quantity` accept the codec forms above, required params go into `required`, methods require `_self`).
Calls share the `/invoke` engine: same whitelist, timeout and encoding; the tool result is a JSON text
`{"ok", "result", "error", "elapsed_s"}` (`isError=true` on failure). The endpoint is stateless and returns JSON responses.
If `API_TOKEN` is set, the same `Authorization: Bearer <token>` is required (401 otherwise); without it, omit `headers`.

Cursor (`~/.cursor/mcp.json`) / Claude Code / other clients that support remote HTTP servers:
```json
{
  "mcpServers": {
    "astropy":    {"url": "https://astro.example.com/astropy/mcp",    "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
    "astroquery": {"url": "https://astro.example.com/astroquery/mcp", "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
    "photutils":  {"url": "https://astro.example.com/photutils/mcp",  "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
    "astroplan":  {"url": "https://astro.example.com/astroplan/mcp",  "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
    "sunpy":      {"url": "https://astro.example.com/sunpy/mcp",      "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}}
  }
}
```
Claude Code CLI: `claude mcp add --transport http astropy https://astro.example.com/astropy/mcp --header "Authorization: Bearer <YOUR_TOKEN>"`.
Clients that only speak stdio (e.g. Claude Desktop) can bridge with `npx mcp-remote https://astro.example.com/astropy/mcp --header "Authorization: Bearer <YOUR_TOKEN>"`.

Smoke test: `BASE=https://astro.example.com API_TOKEN=... [VERIFY_TLS=0] python tests/mcp_check.py` (initialize, list_tools = 20, two tool calls per SDK).
