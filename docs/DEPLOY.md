# astro-sdk-services 部署文档

六个服务（astropy / astroquery / photutils / astroplan / sunpy / **euclid**），**一个镜像、一个容器、6 个 MCP 端点**。默认**不鉴权**；设置 `API_TOKEN` 后才要求 Bearer token。

## 一个镜像 = 一个容器 = 6 个 MCP 服务

镜像 `ghcr.io/aaronyang0628/astro-sdk-services` 默认 `SDK=all`：一个进程同时提供 6 个服务，按路径区分（前 5 个各 20 个工具；euclid 为 FITS URL/本地 MER 裁剪，13 个细粒度工具）：

| SDK | MCP 地址 | HTTP 调用 | 工具列表 | 工具数 | 对应简介文件 |
|---|---|---|---|---|---|
| astropy | `http(s)://<你的域名>/astropy/mcp` | `POST /astropy/invoke` | `GET /astropy/tools` | 20 | `astropy.json` |
| astroquery | `http(s)://<你的域名>/astroquery/mcp` | `POST /astroquery/invoke` | `GET /astroquery/tools` | 20 | `astroquery.json` |
| photutils | `http(s)://<你的域名>/photutils/mcp` | `POST /photutils/invoke` | `GET /photutils/tools` | 20 | `photutils.json` |
| astroplan | `http(s)://<你的域名>/astroplan/mcp` | `POST /astroplan/invoke` | `GET /astroplan/tools` | 20 | `astroplan.json` |
| sunpy | `http(s)://<你的域名>/sunpy/mcp` | `POST /sunpy/invoke` | `GET /sunpy/tools` | 20 | `sunpy.json` |
| euclid | `http(s)://<你的域名>/euclid/mcp` | `POST /euclid/invoke` | `GET /euclid/tools` | 13 | （URL/本地 FITS 细粒度 cutout，见下文） |

其他路径：`GET /` 和 `GET /health` 返回 6 个服务的列表；`GET /<sdk>/health` 为单个 SDK 健康检查（始终免鉴权）。

- `/invoke` 请求体：`{"function_name": "...", "arguments": {...}}`
- `/mcp`：MCP Streamable HTTP（无状态，JSON 响应）
- **上架到 MCP 平台**：登记 **6 个独立的 MCP 条目**（euclid 需另挂 MER 数据卷），各填对应的 MCP 地址并使用对应的 `<sdk>.json` 简介；若启用了 `API_TOKEN`，再加请求头 `Authorization: Bearer <你的token>`（5 个服务共用同一个 token）。
- 兼容模式：`SDK=astropy` 等单个名字时，容器只提供该 SDK（路径 `/<sdk>/...` 或不带前缀均可）。


## Euclid FITS 裁剪（`/euclid`）

纯 MCP/HTTP **细粒度**工具链（无 Flask）。主路径支持 **HTTPS FITS URL**（如下载到 `EUCLID_CACHE_DIR` 再裁剪），并输出 **cutout FITS + quicklook PNG/JPG**。本地 MER（TILE→产品路径）仍保留。

| 环境变量 | 含义 |
|---|---|
| `EUCLID_CACHE_DIR` | HTTPS FITS 下载缓存（默认 `./euclid_cache`；支持 Range 续传） |
| `EUCLID_OUTPUT_DIR` | cutout / preview 输出目录（默认 `./euclid_cutouts`） |
| `EUCLID_MER_ROOT` | （可选）本地 MER 根目录 |
| `EUCLID_TILE_INDEX` | （可选）TILE 索引 FITS |

**URL→图像推荐链：** `euclid_fetch_fits` → `euclid_list_hdus` → `euclid_read_wcs_header` → `euclid_sky_to_pixel` → `euclid_cutout2d` → `euclid_write_preview`。  
多 GB 文件请给 `fetch_fits` 传 `max_bytes`（例如 `25000000`）只拉前缀，避免整包下载。

工具（13）：上述 6 步 + `euclid_pixel_to_sky` / `euclid_get_config`，以及本地 MER：`validate_catalog` / `query_tile_id` / `locate_products` / `cutout_single` / `cutout_batch`。

```bash
docker run -d --name astro-sdk -p 8000:8000 \
  -e EUCLID_CACHE_DIR=/data/cache \
  -e EUCLID_OUTPUT_DIR=/data/cutouts \
  -v /path/to/cache:/data/cache \
  -v /path/to/cutouts:/data/cutouts \
  ghcr.io/aaronyang0628/astro-sdk-services:latest
```

冒烟：`python tests/test_euclid_smoke.py`（含 mock + 可选真实 CASDC URL 前缀下载）。


## 1. 镜像

| 项 | 值 |
|---|---|
| 镜像仓库 | `ghcr.io/aaronyang0628/astro-sdk-services`（公开，无需登录即可拉取） |
| 浮动 tag | `latest`（master 最新构建） |
| 固定 tag | 提交 SHA，例如 `ghcr.io/aaronyang0628/astro-sdk-services:<commit-sha>` |
| 构建方式 | GitHub Actions `.github/workflows/image.yml`，push 到 `master` 自动构建，也可手动触发 |
| 容器端口 | `8000` |
| 环境变量 | `SDK`（默认 `all`；或 astropy/astroquery/photutils/astroplan/sunpy/euclid）；Euclid 另需 `EUCLID_CACHE_DIR` / `EUCLID_OUTPUT_DIR`（URL 裁剪）；本地 MER 另需 `EUCLID_MER_ROOT` / `EUCLID_TILE_INDEX`；`API_TOKEN`（可选，为空则不鉴权）；`MEM_LIMIT_GB`（可选，进程地址空间上限，all 模式默认 8，单 SDK 默认 4） |

生产环境建议使用固定 SHA tag。若无法访问 GHCR，可从源码自行构建：`docker build -t astro-sdk-services .`

## 2. Docker 运行

```bash
docker run -d --name astro-sdk -p 8000:8000 ghcr.io/aaronyang0628/astro-sdk-services:latest

curl http://127.0.0.1:8000/                       # 6 个服务列表
curl http://127.0.0.1:8000/astropy/tools          # astropy 的 20 个工具
curl -X POST http://127.0.0.1:8000/astropy/invoke -H "Content-Type: application/json" \
  -d '{"function_name":"astropy_quantity_to","arguments":{"unit":"m","_self":{"value":1.5,"unit":"km"}}}'
```

如需鉴权，加 `-e API_TOKEN=<你的token>`（例如 `openssl rand -hex 24` 生成），之后除 `/health` 外的请求需带 `-H "Authorization: Bearer <你的token>"`。

启动约 10 秒（加载 5 个库），空闲内存约 300–400 MB；建议给容器 2–4 GB 内存。

## 3. Kubernetes（Helm）部署

Chart 位于 `helm/astro-sdk-services`。默认 `allInOne: true`：一个 Deployment + Service `astro-all`，一个 Ingress 把 `/astropy`、`/astroquery`、`/photutils`、`/astroplan`、`/sunpy`、`/euclid` 都转发到它。设 `allInOne: false` 则每个 SDK 各一个 Deployment + Service（`astro-<sdk>`），适合需要隔离或分别扩容时。

### 3.1 （可选）token Secret
```bash
kubectl create namespace astro-tools
# 仅在需要鉴权时：
kubectl -n astro-tools create secret generic astro-api-token \
  --from-literal=token=$(openssl rand -hex 24)
```

### 3.2 values 文件
`my-values.yaml`：
```yaml
image:
  repository: ghcr.io/aaronyang0628/astro-sdk-services
  tag: "<commit-sha>"
  pullPolicy: IfNotPresent
allInOne: true
ingress:
  enabled: true
  className: nginx
  host: astro.example.com          # 换成你的域名
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "false"   # 仅 HTTP 访问时
    # cert-manager.io/cluster-issuer: <your-issuer>     # 需要 HTTPS 时
  tls: []
auth:
  secretName: ""                   # 空 = 不鉴权；需要时填 astro-api-token
resources:
  requests: {cpu: 200m, memory: 1Gi}
  limits: {cpu: "2", memory: 4Gi}
```

### 3.3 安装 / 升级
```bash
git clone https://github.com/AaronYang0628/astro-sdk-services.git
cd astro-sdk-services
helm upgrade --install astro-sdk helm/astro-sdk-services -n astro-tools --create-namespace \
  -f my-values.yaml --set image.tag=<commit-sha>
kubectl -n astro-tools rollout status deploy/astro-all
kubectl -n astro-tools get pods,svc,ingress
```

### 3.4 验证
```bash
export BASE=http://astro.example.com          # 或 http://<域名>:<ingress NodePort>
# 终端设置了 http(s)_proxy 时，内网地址需绕过代理：
export NO_PROXY=astro.example.com,$NO_PROXY no_proxy=$NO_PROXY

curl $BASE/health
curl $BASE/astropy/tools
curl -X POST $BASE/astroquery/invoke -H "Content-Type: application/json" \
  -d '{"function_name":"astroquery_simbad_query_object","arguments":{"object_name":"M31"}}'

# 全量回归 / MCP 冒烟测试（启用鉴权时再加 API_TOKEN=<你的token>）
pip install -r requirements.txt requests httpx
for s in astropy astroquery photutils astroplan sunpy; do BASE_URL=$BASE python3 tests/run_cases.py $s; done
BASE=$BASE python3 tests/mcp_check.py
```

### 3.5 回滚 / 卸载
```bash
helm -n astro-tools history astro-sdk
helm -n astro-tools rollback astro-sdk <revision>
helm -n astro-tools uninstall astro-sdk
```

## 4. MCP 客户端接入

每个 SDK 一个端点 `<BASE>/<sdk>/mcp`（Streamable HTTP）。未启用鉴权时不需要 `headers`；启用后加 `"headers": {"Authorization": "Bearer <你的token>"}`。

Cursor / 通用 `mcpServers`：
```json
{
  "mcpServers": {
    "astropy":    {"url": "http://astro.example.com/astropy/mcp"},
    "astroquery": {"url": "http://astro.example.com/astroquery/mcp"},
    "photutils":  {"url": "http://astro.example.com/photutils/mcp"},
    "astroplan":  {"url": "http://astro.example.com/astroplan/mcp"},
    "sunpy":      {"url": "http://astro.example.com/sunpy/mcp"}
  }
}
```
opencode（`opencode.json`）：
```json
{
  "mcp": {
    "astro-astropy": {"type": "remote", "url": "http://astro.example.com/astropy/mcp", "enabled": true, "oauth": false}
  }
}
```
Claude Code：
```bash
claude mcp add --transport http astropy http://astro.example.com/astropy/mcp
```

## 5. 注意事项

- **安全**：默认不鉴权，仅适合内网或可信环境。部分工具可读取容器内文件（如 FITS、numpy 文件），对公网开放时务必设置 `API_TOKEN`，且不要把 token 写进仓库或公开配置。
- **外网依赖**：astroquery 各工具需要能访问 SIMBAD、VizieR、Gaia、NASA 等外部服务，外部服务不稳定时会超时或报 503；astropy 的 IERS 数据在镜像构建时预取。
- **并发**：all 模式下 5 个 SDK 共用一个进程，单个工具调用执行时会阻塞其它请求，慢查询（如 Gaia）会让所有请求排队。并发较高时可增加副本，或改用 `allInOne: false` 分开部署。
- **超时与资源**：单次调用 30 秒超时；进程地址空间上限由 `MEM_LIMIT_GB` 控制（all 模式默认 8）。
- **HTTPS**：MCP 客户端（Cursor、Claude）通常要求有效证书。若集群外 80/443 未转发到 Ingress，cert-manager HTTP-01 无法签发，可改用 DNS-01 或内网 HTTP 访问。
