#!/usr/bin/env bash
# Start the 5 SDK services on 127.0.0.1:9101-9105. Usage: PY=/path/to/python ./run_all.sh [stop]
cd "$(dirname "$0")"
PY=${PY:-/workspace/astro-venv/bin/python}
export MPLBACKEND=Agg PYTHONPATH=$PWD PYTHONWARNINGS=ignore
mkdir -p logs /tmp/astro_out
if [ "$1" = "stop" ]; then pkill -f "uvicorn sdks\." ; exit 0; fi
i=9101
for sdk in astropy astroquery photutils astroplan sunpy; do
  nohup $PY -m uvicorn sdks.$sdk:app --host 127.0.0.1 --port $i --log-level warning > logs/$sdk.log 2>&1 &
  i=$((i+1))
done
for p in 9101 9102 9103 9104 9105; do for t in $(seq 60); do curl -sf http://127.0.0.1:$p/health >/dev/null && break; sleep 1; done; curl -s http://127.0.0.1:$p/health; echo; done
