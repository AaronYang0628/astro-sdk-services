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
`helm/astro-sdk-services`: one Deployment + Service per SDK and a path-routed Ingress (host `astro.example.com`,
placeholder). Not deployed or linted against a cluster; the image must be built from `Dockerfile` (`SDK` env selects the service).
