# astro-sdk-services 部署文档（给 zero2xLab / 021 运维）

**一个镜像 = 一个容器 = 6 个 MCP 服务**：astropy / astroquery / photutils / astroplan / sunpy / **euclid**。

- 镜像：`ghcr.io/aaronyang0628/astro-sdk-services:a5ff7cf7b2769308fe1676e0f4a17f8ecee251c1`（公开，免登录拉取；GitHub Actions 按提交 SHA 打 tag，同时更新 `:latest`）
- 容器端口 `8000`，默认 `SDK=all`：一个进程按路径同时提供 6 个服务 `/<sdk>/{health,tools,invoke,mcp}`
- **默认不鉴权**（只有设置了非空 `API_TOKEN` 才要求 `Authorization: Bearer <token>`）
- 部署完成后，在 021 平台登记 **6 个连接器**（每个 SDK 一个 MCP 地址 `https://<你的域名>/<sdk>/mcp`，传输方式 Streamable），见第 7 节

| SDK | MCP 地址（Streamable HTTP） | 工具数 | 简介文件 |
|---|---|---|---|
| astropy | `https://<你的域名>/astropy/mcp` | 20 | `astropy.json` |
| astroquery | `https://<你的域名>/astroquery/mcp` | 20 | `astroquery.json` |
| photutils | `https://<你的域名>/photutils/mcp` | 20 | `photutils.json` |
| astroplan | `https://<你的域名>/astroplan/mcp` | 20 | `astroplan.json` |
| sunpy | `https://<你的域名>/sunpy/mcp` | 20 | `sunpy.json` |
| euclid | `https://<你的域名>/euclid/mcp` | 14 | `euclid.json` |

其他路径：`GET /`、`GET /health` 返回 6 个服务列表；`GET /<sdk>/health` 单个服务健康检查（始终免鉴权）；`GET /<sdk>/tools` 工具清单；`POST /<sdk>/invoke` 直接 HTTP 调用（请求体 `{"function_name": "...", "arguments": {...}}`）。`/mcp` 为 MCP Streamable HTTP（无状态、JSON 响应）。

> 文档里的 `astro.example.com`、`<你的域名>` 都是占位符，请换成你们自己的域名。

---

## 1. 镜像与环境变量

| 项 | 值 |
|---|---|
| 镜像 | `ghcr.io/aaronyang0628/astro-sdk-services` |
| 推荐 tag | `a5ff7cf7b2769308fe1676e0f4a17f8ecee251c1`（固定提交，生产请用这个）；`latest` 为 master 最新构建 |
| 自行构建 | 无法访问 GHCR 时：`git clone https://github.com/AaronYang0628/astro-sdk-services.git && cd astro-sdk-services && git checkout a5ff7cf && docker build -t astro-sdk-services:a5ff7cf .`，然后推到内部镜像仓库 |
| 端口 | `8000`（HTTP） |
| 启动时间 | 约 10–20 秒（加载 6 个库）；空闲 RSS 约 350 MB |

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SDK` | `all` | `all` = 6 个服务；也可设单个名字（astropy/…/euclid）只跑一个 |
| `API_TOKEN` | 空 | 空 = 不鉴权；非空则除 `/health` 外都要求 `Authorization: Bearer <token>` |
| `MEM_LIMIT_GB` | all 模式 8，单 SDK 4 | 进程地址空间上限（RLIMIT_AS），超出时该次调用报 MemoryError 而不是整个容器被杀 |
| `EUCLID_CACHE_DIR` | `<工作目录>/euclid_cache`（容器内 `/workspace/astro_services/euclid_cache`） | `euclid_fetch_fits` 下载缓存（文件名只由 URL 的主机+路径生成，不含签名） |
| `EUCLID_OUTPUT_DIR` | `<工作目录>/euclid_cutouts` | 裁剪 FITS（`cutouts/`）与预览图（`previews/`）输出目录 |
| `EUCLID_INPUT_ROOTS` | 空 | 允许作为输入的本地目录（绝对路径，`:` 或 `,` 分隔），例如 `/home/scientist`。空 = 不接受本地路径，只接受 http(s) URL。见 6.3 |
| `EUCLID_MER_ROOT` | 空（可选） | 本地 Euclid MER 数据根目录，只有用本地 MER 工具时才需要 |
| `EUCLID_TILE_INDEX` | 空（可选） | 本地 MER 的 TILE 索引 FITS |
| `EUCLID_INLINE_IMAGE` | `1` | `0` = `euclid_write_preview` 不在 MCP 结果里内嵌缩略图 |
| `MCP_MAX_INLINE_IMAGE_BYTES` | `2000000` | 内嵌图片大小上限，超过则不内嵌 |

Helm chart 会把 `EUCLID_CACHE_DIR=/data/euclid/cache`、`EUCLID_OUTPUT_DIR=/data/euclid/cutouts` 设好，并在 `/data/euclid` 挂一个卷（默认 emptyDir 20Gi）。

## 2. 资源、出网、存储（部署前请确认）

| 项 | 建议 | 依据 |
|---|---|---|
| CPU | requests 200m，limits 2 | 工具都是单线程计算 |
| 内存 | requests 1Gi，limits **8Gi** | all 模式 `MEM_LIMIT_GB=8`；Euclid 用 memmap 读 FITS，实测单次切图 RSS 不到 0.5 GB，8Gi 是给大图/多 HDU 的余量 |
| 磁盘 | `/data/euclid` 卷 **≥ 20Gi**（emptyDir 或 PVC） | 按推荐用法（`max_bytes=25000000`）每个远程 FITS 只缓存约 25 MB；若不传 `max_bytes` 会下载完整文件（CASDC VIS 样例为 2.44 GB）。缓存不会自动清理，长期运行建议用 PVC 并定期清理 |
| 项目文件 | 021 用户上传的 FITS 在项目 Pod 的 `/home/scientist/project<项目ID>/Data/` 下（下载需登录，没有可用的 URL）。要让 MCP 直接读这些文件，需把同一份存储**只读**挂到本服务 Pod 的 `/home/scientist`，见 **6.3** | 不挂载时只能用 http(s) URL 作为输入 |
| 出网 | 必须能访问 `casdc.china-vo.org:443`（Euclid 样例数据）以及用户给出的其它 FITS 链接所在域名；astroquery 需访问 SIMBAD/VizieR（`simbad.cds.unistra.fr`、`vizier.cds.unistra.fr`）、Gaia（`gea.esac.esa.int`）、NASA（`exoplanetarchive.ipac.caltech.edu`、`irsa.ipac.caltech.edu`、`heasarc.gsfc.nasa.gov`）、JPL（`ssd.jpl.nasa.gov`）、MPC（`minorplanetcenter.net`）等；astropy 按名称解析目标也要访问 CDS | 需要走代理时用 `extraEnv` 设 `HTTPS_PROXY` / `NO_PROXY` |
| 入站 | 021 服务端要能访问到 `https://<你的域名>/<sdk>/mcp` | 021 连接器是从 021 服务端发起调用 |
| Ingress 超时 | `proxy-read-timeout` / `proxy-send-timeout` 设 **600** 秒 | nginx 默认 60 秒；Euclid 下载 FITS 实测约 37 秒（25 MB），网络慢时会超过 60 秒 |
| 副本 | 1（可加） | 见第 8 节「并发」 |

## 3. Docker 一行启动

```bash
docker run -d --name astro-sdk -p 8000:8000 \
  -e EUCLID_CACHE_DIR=/data/euclid/cache -e EUCLID_OUTPUT_DIR=/data/euclid/cutouts \
  -v /srv/astro-euclid:/data/euclid --memory 8g \
  ghcr.io/aaronyang0628/astro-sdk-services:a5ff7cf7b2769308fe1676e0f4a17f8ecee251c1
```

需要鉴权时加 `-e API_TOKEN=$(openssl rand -hex 24)`（不要把 token 写进仓库或公开配置）。需要代理时加 `-e HTTPS_PROXY=... -e NO_PROXY=...`。

## 4. Kubernetes：Helm（推荐）

Chart 在仓库 `helm/astro-sdk-services`（0.2.3）。默认 `allInOne: true`：1 个 Deployment + 1 个 Service `astro-all`，1 个 Ingress 把 `/astropy`、`/astroquery`、`/photutils`、`/astroplan`、`/sunpy`、`/euclid` 都转发过去。

`my-values.yaml`（只需改域名、证书、存储）：
```yaml
image:
  repository: ghcr.io/aaronyang0628/astro-sdk-services   # 用内部仓库时改这里
  tag: "a5ff7cf7b2769308fe1676e0f4a17f8ecee251c1"
  pullPolicy: IfNotPresent
allInOne: true
services:              # 6 个 SDK，对应 Ingress 路径 /<name>
  - name: astropy
  - name: astroquery
  - name: photutils
  - name: astroplan
  - name: sunpy
  - name: euclid
ingress:
  enabled: true
  className: nginx
  host: astro.example.com                  # 换成你们的域名
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
    # nginx.ingress.kubernetes.io/ssl-redirect: "false"   # 只走 HTTP 时打开
    # cert-manager.io/cluster-issuer: <your-issuer>       # 用 cert-manager 签证书时
  tls: []
  # tls: [{hosts: [astro.example.com], secretName: astro-example-tls}]
auth:
  secretName: ""                           # 空 = 不鉴权
resources:
  requests: {cpu: 200m, memory: 1Gi}
  limits: {cpu: "2", memory: 8Gi}
euclid:
  cacheDir: /data/euclid/cache
  outputDir: /data/euclid/cutouts
  storage:
    existingClaim: ""                      # 填 PVC 名可跨重启保留缓存/输出；空 = emptyDir
    sizeLimit: 20Gi
  inputRoots: ""                           # EUCLID_INPUT_ROOTS；空且配置了 projectStorage 时自动取 mountPath（/home/scientist）
  projectStorage:                          # 只读挂载 021 项目存储（见 6.3），三选一，不填则不挂载
    existingClaim: ""                      #   PVC 名（同命名空间，RWX/ROX）
    hostPath: ""                           #   节点目录
    nfs: {server: "", path: ""}            #   NFS 导出
    subPath: ""
    mountPath: /home/scientist             #   与项目 Pod 内路径保持一致
    readOnly: true
extraEnv: []
# extraEnv:
#   - {name: HTTPS_PROXY, value: "http://proxy.example.com:3128"}
#   - {name: NO_PROXY, value: "localhost,127.0.0.1,.svc,.cluster.local"}
```

安装 / 升级：
```bash
git clone https://github.com/AaronYang0628/astro-sdk-services.git && cd astro-sdk-services
helm upgrade --install astro-sdk helm/astro-sdk-services -n astro-tools --create-namespace -f my-values.yaml
kubectl -n astro-tools rollout status deploy/astro-all
kubectl -n astro-tools get pods,svc,ingress
```

回滚 / 卸载：
```bash
helm -n astro-tools history astro-sdk
helm -n astro-tools rollback astro-sdk <revision>
helm -n astro-tools uninstall astro-sdk
```

如果之前用旧版 chart 按「每个 SDK 一个 Deployment」部署过，`helm upgrade` 到 `allInOne: true` 后旧的 `astro-<sdk>` Deployment 会被 helm 自动删除。

可选：需要鉴权时先建 Secret，再设 `auth.secretName: astro-api-token`：
```bash
kubectl -n astro-tools create secret generic astro-api-token --from-literal=token=$(openssl rand -hex 24)
```

## 5. Kubernetes：原生 YAML（不用 Helm 时）

`deploy/astro-all.yaml` 是用上面默认 values 渲染出来的完整清单（Deployment + Service + Ingress，emptyDir 20Gi，Ingress 超时 600 秒）。把里面的 `astro.example.com` 换成你们的域名后：
```bash
kubectl create namespace astro-tools
kubectl -n astro-tools apply -f deploy/astro-all.yaml
```

## 6. 健康检查与自测

- 就绪探针：`GET /health`（chart 已配置 readinessProbe：initialDelay 15s、period 10s、failureThreshold 30）。注意：长时间工具调用（如下载 FITS）期间 `/health` 会暂时卡住，所以没有配 livenessProbe，请不要加过于激进的存活探针。

```bash
export BASE=https://astro.example.com     # 或集群内 http://astro-all.astro-tools.svc
H='-H Content-Type:application/json -H Accept:application/json,text/event-stream'

curl -s $BASE/health                      # {"ok":true,"mode":"all","auth":false,"services":{...6 个...}}
curl -s $BASE/euclid/health               # {"ok":true,"sdk":"euclid","tools":14}

# MCP tools/list（每个 SDK 都可以这样测，astropy 等应返回 20，euclid 返回 14）
for s in astropy astroquery photutils astroplan sunpy euclid; do
  printf "%-11s" $s; curl -s -X POST $BASE/$s/mcp $H \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -c "import json,sys;print(len(json.load(sys.stdin)['result']['tools']))"
done

# 普通 HTTP 调用示例
curl -s -X POST $BASE/astropy/invoke -H 'Content-Type: application/json' \
  -d '{"function_name":"astropy_quantity_to","arguments":{"unit":"m","_self":{"value":1.5,"unit":"km"}}}'
```

### 6.1 Euclid 快速验证（远程 FITS URL → 1024 像素切图 + 预览图）

样例：CASDC 镜像的 Euclid Q1 VIS 文件（2.44 GB，多扩展 FITS，科学图像在 `hdu_index=1`）。工具链：
`euclid_fetch_fits` → `euclid_list_hdus` → `euclid_find_peak_sky` → `euclid_cutout2d(hdu_index=1, size=1024)` → `euclid_write_preview`

```bash
call(){ curl -s -X POST $BASE/euclid/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['content'][0]['text'])"; }
URL=https://casdc.china-vo.org/mirror/Euclid-Q1/VIS/2686/EUC_VIS_SWL-BKG-002686-01-1-0000000__20241017T042432.874944Z.fits

# 1) 只下载前 25 MB（足够包含 HDU 1），返回服务端缓存 path
call euclid_fetch_fits "{\"url\":\"$URL\",\"max_bytes\":25000000}"
P=<上一步 result.path>
# 2) 列 HDU：0=PRIMARY(空)，1=1-1.E 2048x2066，2=1-1.F
call euclid_list_hdus "{\"path\":\"$P\"}"
# 3) 没有星表时取最亮像素的 RA/DEC（有星表就用星表坐标）
call euclid_find_peak_sky "{\"path\":\"$P\",\"hdu_index\":1}"
# 4) 按 RA/DEC 切 1024x1024
call euclid_cutout2d "{\"path\":\"$P\",\"ra\":<ra>,\"dec\":<dec>,\"hdu_index\":1,\"size\":1024,\"obj_id\":\"vis2686_peak\"}"
# 5) 写预览 PNG
call euclid_write_preview "{\"fits_path\":\"<上一步 result.fits_path>\"}"   # call() 只打印 text；完整响应里还有 content[1] 图片块

# 或用仓库自带的 MCP 自测（6 个 SDK 全测；euclid 断言返回可解码的 PNG 图片块，SAVE_IMAGE 把图片存下来）
pip install mcp httpx
BASE=$BASE EUCLID_URL=$URL SAVE_IMAGE=./mcp_image_block.png python3 tests/mcp_check.py
```

参考结果（a5ff7cf 同版本代码实测，MCP tools/call）：

| 步骤 | 关键返回 | 耗时 |
|---|---|---|
| fetch_fits | `size_bytes=25000000`，`remote_size_bytes=2438570880`，`prefix_ok=true` | ≈37 s（取决于到 CASDC 的带宽） |
| list_hdus | 3 个 HDU，HDU 1 `shape=[2066,2048]` 带 WCS | <0.1 s |
| find_peak_sky | `ra≈267.47864, dec≈66.72683`（x=431, y=343） | <0.1 s |
| cutout2d | `shape=[1024,1024]`，`inside=true`，`fits_path=/data/euclid/cutouts/cutouts/vis2686_peak.fits` | <0.1 s |
| write_preview | MCP 返回 `content=[text, image]`：text 为 JSON（`preview_path`、`stretch` 等），image 为 `image/png` 缩略图（约 13 KB，最长边 ≤ 1024） | ≈0.2 s |

> 峰值点靠近图像边缘，1024 切图是 `mode=partial`，图像外部分用 0 填充（预览中为黑边），这是正常现象。

**切图结果如何展示**：`euclid_write_preview` 通过 MCP 调用时，返回内容里除了 JSON 文本外还带一个 **MCP 图片内容块**（`{"type":"image","mimeType":"image/png","data":"<base64>"}`），021 对话里直接显示为**内嵌缩略图**。缩略图最长边默认 ≤ 1024 像素（参数 `max_side` 可调小），通常几十 KB 以内；超过 2 MB 的图片不会内嵌（`MCP_MAX_INLINE_IMAGE_BYTES` 可调）。不想内嵌时调用参数传 `inline_image=false`，或全局设环境变量 `EUCLID_INLINE_IMAGE=0`。**完整的裁剪 FITS（以及 PNG 原文件）只保存在服务端** `/data/euclid/cutouts/` 下，不提供下载链接；运维需要时可 `kubectl -n astro-tools cp <pod>:/data/euclid/cutouts/cutouts/<名字>.fits ./` 取回。HTTP `POST /euclid/invoke` 只返回 JSON（不含图片）。

### 6.2 Euclid 的输入形式与安全限制

`euclid_fetch_fits` 的入参是 **`url`**（旧名 `url_or_path` 仍可用），二选一：

| 输入 | 说明 |
|---|---|
| **021 项目文件的绝对路径**（主要用法） | 用户把 FITS 上传到项目的 `Data/` 目录后，文件在 `/home/scientist/project<项目ID>/Data/<文件名>`，例如 `/home/scientist/project2114525713776963586/Data/x.fits`。021 智能体直接把这个路径传给 `euclid_fetch_fits`（也接受 `file:///home/scientist/...`）。**前提**：本服务 Pod 以只读方式在同一路径挂载了这份存储，并设置 `EUCLID_INPUT_ROOTS=/home/scientist`（见 6.3）。文件**原地只读打开（memmap），不复制**，返回的 `path` 就是这个路径。 |
| **http(s) FITS URL** | 公开链接（如 6.1 的 CASDC 镜像），或带签名参数的临时 OSS/S3 地址（查询串原样发送、在结果与错误里显示为 `?<redacted>`）。多 GB 文件传 `max_bytes`（如 `25000000`）只取前缀（HTTP Range；服务器不支持 Range 时边下边截断）；签名过期会返回 `temporary (presigned) URL has expired` 错误。 |

- **本地路径的限制**：路径先做 realpath（解析 `..` 和符号链接）再检查，必须落在 `EUCLID_INPUT_ROOTS` 某个目录内；目录外、`..` 越界、指向外部的符号链接都会被拒绝。错误信息会列出允许的目录并提示可改用 http(s) URL，例如：`PermissionError: path not allowed (outside the input roots): /etc/passwd; allowed input roots (EUCLID_INPUT_ROOTS): /home/scientist; e.g. /home/scientist/project<id>/Data/<file>.fits. Alternatively pass an http(s) URL`。`EUCLID_INPUT_ROOTS` 为空时一律拒绝本地路径。输入目录只读：输出只会写到 `EUCLID_OUTPUT_DIR`。
- **文件类型**：按内容识别 FITS（开头 `SIMPLE  =`，也支持 gzip），不看扩展名：`.fits/.fit/.fts/.fz`、无扩展名都可以；非 FITS 文件会被拒绝。
- **必须含 2D 图像**：切图需要图像 HDU。**示例上传文件 `euclid-…moc.fits` 是 MOC（HEALPix 覆盖范围）表格，没有图像 HDU**：`euclid_list_hdus` 会返回 `image_hdus: []` 和说明，`find_peak_sky` / `cutout2d` / `write_preview` 等返回 `no image HDU (this looks like a MOC (HEALPix coverage) table; HDUs: …)`。请上传 VIS/NISP 图像或 MER 拼接图来验证切图。
- **其余工具**：`path` / `fits_path` / `catalog_path` 只能是 `EUCLID_INPUT_ROOTS`、`EUCLID_CACHE_DIR`、`EUCLID_OUTPUT_DIR`（以及配置了的 `EUCLID_MER_ROOT` / `EUCLID_TILE_INDEX`、镜像内置测试样例）里的文件；`output_path` / `output_dir` 只能在 `EUCLID_OUTPUT_DIR` 内；`mer_root` 覆盖值只能是 `EUCLID_MER_ROOT` 的子目录。Euclid 工具参数按原样 JSON 传入，不支持 `/invoke` 的 `__call__` 对象构造。

### 6.3 让 MCP 直接读 021 项目文件（只读挂载 `/home/scientist`）

021 智能体看到的项目文件路径是项目 Pod 内的 `/home/scientist/project<项目ID>/Data/...`，这些文件不能匿名下载（需要登录，返回 401），所以 MCP 服务要**自己能在同一路径读到它们**：

1. 找到 021 项目 Pod 中 `/home/scientist` 背后的存储（PVC / NFS / 节点目录）。
2. 把它**只读**挂到本服务 Pod 的**同一路径** `/home/scientist`（路径一致，智能体给的路径才能原样使用）。PVC 需要与本服务在同一命名空间且支持多 Pod 挂载（RWX/ROX）；不在同一命名空间时可用同一 NFS 导出再建一个只读 PV/PVC，或直接用 `nfs`。
3. 设置 `EUCLID_INPUT_ROOTS=/home/scientist`（Helm 配了 `projectStorage` 时自动设置）。

Helm 示例（三选一）：
```yaml
euclid:
  projectStorage:
    existingClaim: scientist-home          # 或：nfs: {server: nfs.example.com, path: /export/scientist}；或：hostPath: /data/scientist
    mountPath: /home/scientist
    readOnly: true
  # inputRoots: /home/scientist            # 不写则自动等于 mountPath
```
原生 YAML 见 `deploy/astro-all.yaml` 中被注释的 `project-storage` 示例（env、volumeMounts、volumes 三处取消注释）。

验证：
```bash
kubectl -n astro-tools exec deploy/astro-all -- ls /home/scientist/project<项目ID>/Data/
# euclid_get_config 返回的 input_roots 应为 ["/home/scientist"]
BASE=$BASE SDKS=euclid EUCLID_URL=/home/scientist/project<项目ID>/Data/<图像>.fits python3 tests/mcp_check.py
```

**无法挂载时的替代方案**：不配置 `EUCLID_INPUT_ROOTS`，让智能体传 http(s) URL（公开 FITS 链接，或能直接读取的临时签名地址）。

## 7. 在 021 登记连接器（创建者：02xlab，平台托管）

入口：「连接器 → 创建连接器 → 自部署 MCP（SSE）」，每个 SDK 建一条，共 6 条：

- **传输方式**：选 **Streamable**（不要选 SSE）
- **EndPoint**：`https://<你的域名>/<sdk>/mcp`
- **请求头**：未启用鉴权时**删掉 Authorization 那一行，留空**；启用了 `API_TOKEN` 时填 `Authorization: Bearer <token>`（6 个共用同一个 token）
- **超时**：见下表（各工具服务端都有自己的超时上限：常规工具 30 秒；`euclid_fetch_fits` 600 秒，`euclid_cutout2d` 120 秒）
- **简介**：用对应的 `<sdk>.json`（name/description/overview 中英文，随本文档一起提供的 6 个 JSON 文件）

| 名称 | 描述 | EndPoint | 超时（秒） |
|---|---|---|---|
| Astropy 天文基础工具 | 让AI直接调用 astropy：坐标转换、单位换算、时间系统、宇宙学距离、FITS头读取与周期分析，无需自己写代码。 | `https://<你的域名>/astropy/mcp` | 60 |
| Astroquery 天文数据库查询 | 让AI直接调用 astroquery：一句话查询 SIMBAD、VizieR、Gaia、NASA 系外行星等权威天文数据库。 | `https://<你的域名>/astroquery/mcp` | 120 |
| Photutils 天文测光 | 让AI直接调用 photutils：源检测、孔径测光、质心定位、背景估计与 PSF 宽度拟合，无需自己写代码。 | `https://<你的域名>/photutils/mcp` | 60 |
| Astroplan 观测规划 | 让AI直接调用 astroplan：目标升落、可观测性、晨昏蒙影与月相，几句话排好观测计划。 | `https://<你的域名>/astroplan/mcp` | 60 |
| SunPy 太阳物理工具 | 让AI直接调用 sunpy：日面坐标参数、卡林顿自转、较差自转与太阳图像处理，无需自己写代码。 | `https://<你的域名>/sunpy/mcp` | 60 |
| Euclid 图像裁剪 | 让AI直接处理 Euclid 等天文 FITS：给一个 FITS 文件（021 项目 Data/ 下文件的路径或公开 http(s) 链接），自动读取、找 HDU、按 RA/DEC 切出 1024 像素小图，并在对话中直接显示缩略图。 | `https://<你的域名>/euclid/mcp` | 300 |

超时说明：Euclid 的耗时主要在 `euclid_fetch_fits` 下载（带 `max_bytes=25000000` 实测约 37 秒），切图和预览都在 1 秒内；300 秒给慢网络留余量。若不传 `max_bytes` 会尝试下载完整的 2.4 GB 文件，必然超时，工具描述里已经提示模型对大文件传 `max_bytes`。astroquery 依赖外部数据库，给 120 秒。因为 6 个服务在同一进程内串行执行（第 8 节），并发时排队也会占用超时时间。

登记后在 021 项目对话里勾选 Euclid 连接器，给模型一句话即可验证（对话里应直接出现切图的缩略图）。配置了 6.3 的挂载后，也可以把 FITS 图像上传到项目 `Data/` 目录，然后说「对 /home/scientist/project<项目ID>/Data/<文件名> 在最亮的源处切一张 1024 像素的图」。远程 URL 示例：
> 这是一个 Euclid VIS 的 FITS 文件：https://casdc.china-vo.org/mirror/Euclid-Q1/VIS/2686/EUC_VIS_SWL-BKG-002686-01-1-0000000__20241017T042432.874944Z.fits ，请下载前 25MB，找到科学图像 HDU，在最亮的源处切一张 1024 像素的图并生成预览。

## 8. 注意事项

- **安全**：默认不鉴权，只适合内网 / 可信网络。Euclid 工具只能读 `EUCLID_INPUT_ROOTS`（只读）与自己的缓存/输出目录、只能写输出目录（6.2），但其他 5 个 SDK 的部分工具仍可读取容器内文件（FITS、numpy 文件）；`euclid_fetch_fits` 会按调用方给的 URL 发起出站下载（任意 http(s) 地址，含内网地址）。对公网开放时请设 `API_TOKEN`，或在网关层限制来源（只允许 021 服务端访问）。
- **并发**：all 模式下 6 个服务在一个进程里，工具调用在主线程同步执行，一次慢调用（Euclid 下载、Gaia 查询）会让其它请求排队，期间 `/health` 也会等待。并发高时可加副本（注意 emptyDir 缓存每个 Pod 各自一份；不同副本之间 `path` 不通用，见下条），或设 `allInOne: false` 每个 SDK 单独一个 Deployment。
- **多副本与 Euclid**：工具链前后步骤之间传的是服务端路径（缓存/输出目录），所以 **Euclid 必须保证同一条链路落在同一个 Pod 上**：保持 1 个副本，或用 RWX 的 PVC 共享 `/data/euclid`。
- **切图结果的返回方式**：`euclid_write_preview` 在 MCP 结果里内嵌 PNG/JPG 缩略图（图片内容块），021 对话里直接可见；`euclid_cutout2d` 只返回服务端 `fits_path` 和统计信息。完整 FITS 留在服务端，不对外提供下载。
- **缓存清理**：`/data/euclid/cache` 与 `/data/euclid/cutouts` 不会自动清理；emptyDir 在 Pod 重建时清空，PVC 需要定期清理。
- **样例数据说明**：`EUC_VIS_SWL-BKG-*` 是 VIS 背景（BKG）产品，切出来是平滑背景图，主要用于验证链路；真实科学用途请换成 VIS/NIR 科学图像或 MER 拼接图，并用星表 RA/DEC 而不是最亮像素。
- **HTTPS**：021 等 MCP 客户端通常要求有效证书。若集群外 80/443 未转发到 Ingress，cert-manager HTTP-01 无法签发，可改用 DNS-01 或内部 CA。
- **本地 MER 工具**（`euclid_query_tile_id` / `euclid_locate_products` / `euclid_cutout_single` / `euclid_cutout_batch`）只在挂载了 MER 数据（`EUCLID_MER_ROOT` + `EUCLID_TILE_INDEX`，通过 `extraVolumes` / `extraVolumeMounts` 挂入）时可用；只做 URL 裁剪不需要。

## 9. 其他 MCP 客户端（可选）

```json
{"mcpServers": {
  "astropy":    {"url": "https://astro.example.com/astropy/mcp"},
  "astroquery": {"url": "https://astro.example.com/astroquery/mcp"},
  "photutils":  {"url": "https://astro.example.com/photutils/mcp"},
  "astroplan":  {"url": "https://astro.example.com/astroplan/mcp"},
  "sunpy":      {"url": "https://astro.example.com/sunpy/mcp"},
  "euclid":     {"url": "https://astro.example.com/euclid/mcp"}
}}
```
Claude Code：`claude mcp add --transport http euclid https://astro.example.com/euclid/mcp`
