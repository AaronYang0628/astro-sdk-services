# astro-sdk-services 部署文档

五个天文 SDK（astropy / astroquery / photutils / astroplan / sunpy）各跑一个独立服务，共用**同一个镜像**，通过环境变量 `SDK` 选择加载哪个 SDK。每个服务提供：

| 路径 | 说明 | 鉴权 |
|---|---|---|
| `GET /<sdk>/health` | 健康检查 | 不需要 |
| `GET /<sdk>/tools` | 该 SDK 的 20 个工具及参数 | Bearer token |
| `POST /<sdk>/invoke` | REST 调用：`{"function_name": "...", "arguments": {...}}` | Bearer token |
| `POST /<sdk>/mcp` | MCP Streamable HTTP 端点 | Bearer token |

## 一个镜像 = 5 个 MCP 服务

只有**一个镜像** `ghcr.io/aaronyang0628/astro-sdk-services`。容器启动时用环境变量 `SDK=astropy|astroquery|photutils|astroplan|sunpy` 指定加载哪个 SDK，每个容器就是一个**独立的 MCP 服务**（各自 20 个工具）。

| `SDK` 取值 | 服务（Deployment）名 | MCP 地址 | HTTP 地址 | 工具数 | 对应简介文件 |
|---|---|---|---|---|---|
| `astropy` | `astro-astropy` | `https://<你的域名>/astropy/mcp` | `https://<你的域名>/astropy/invoke` | 20 | `astropy.json` |
| `astroquery` | `astro-astroquery` | `https://<你的域名>/astroquery/mcp` | `https://<你的域名>/astroquery/invoke` | 20 | `astroquery.json` |
| `photutils` | `astro-photutils` | `https://<你的域名>/photutils/mcp` | `https://<你的域名>/photutils/invoke` | 20 | `photutils.json` |
| `astroplan` | `astro-astroplan` | `https://<你的域名>/astroplan/mcp` | `https://<你的域名>/astroplan/invoke` | 20 | `astroplan.json` |
| `sunpy` | `astro-sunpy` | `https://<你的域名>/sunpy/mcp` | `https://<你的域名>/sunpy/invoke` | 20 | `sunpy.json` |

- **Helm**：chart 按 `values.yaml` 的 `services[]` 一次部署全部 5 个（每个一个 Deployment + Service `astro-<sdk>`），由同一个 Ingress 按 `/<sdk>` 路径分流，见第 3 节。
- **Docker**：起 5 个容器即可，例如：

  ```bash
  TOKEN=$(openssl rand -hex 24)
  port=8001
  for sdk in astropy astroquery photutils astroplan sunpy; do
    docker run -d --name astro-$sdk -p $port:8000 \
      -e SDK=$sdk -e API_TOKEN=$TOKEN \
      ghcr.io/aaronyang0628/astro-sdk-services:latest
    port=$((port+1))
  done
  ```

  直连容器时，服务同时接受带前缀和不带前缀的路径，例如 astropy 为 `http://<主机>:8001/astropy/mcp`（或 `/mcp`）、`http://<主机>:8001/astropy/invoke`（或 `/invoke`）；对外提供时可用反向代理把 `/<sdk>` 前缀分流到对应端口，无需改写路径。
- **Token**：5 个服务可以共用同一个 `API_TOKEN`（Helm 中即同一个 Secret）。
- **上架到 MCP 平台**：请登记 **5 个独立的 MCP 条目**，每个条目填写各自的 MCP 地址、请求头 `Authorization: Bearer <你的token>`，并使用对应的 `<sdk>.json` 简介文件。

## 1. 镜像

| 项 | 值 |
|---|---|
| 镜像仓库 | `ghcr.io/aaronyang0628/astro-sdk-services`（公开，无需登录即可拉取） |
| 浮动 tag | `latest`（master 最新构建） |
| 固定 tag | 提交 SHA，例如 `ghcr.io/aaronyang0628/astro-sdk-services:09069ddb37ba60c2755c0bc19c6f70e3ae95e8b1` |
| 构建方式 | GitHub Actions `.github/workflows/image.yml`，push 到 `master` 且改动了代码/依赖时自动构建，也可手动 `workflow_dispatch` |
| 容器端口 | `8000` |
| 关键环境变量 | `SDK`（astropy/astroquery/photutils/astroplan/sunpy），`API_TOKEN`（为空则不鉴权，**生产务必设置**） |

生产环境建议使用固定 SHA tag，不要用 `latest`。

拉取验证：
```bash
docker pull ghcr.io/aaronyang0628/astro-sdk-services:latest
```

## 2. 单机 Docker 运行（快速试用）

```bash
TOKEN=$(openssl rand -hex 24)
docker run -d --name astro-astropy -p 9101:8000 \
  -e SDK=astropy -e API_TOKEN=$TOKEN \
  ghcr.io/aaronyang0628/astro-sdk-services:latest

curl http://127.0.0.1:9101/health
curl http://127.0.0.1:9101/tools -H "Authorization: Bearer $TOKEN"
```
其他 SDK 换 `SDK=` 和端口即可。

## 3. Kubernetes（Helm）部署

Chart 位于 `helm/astro-sdk-services`。每个 SDK 生成一个 Deployment + Service（`astro-<sdk>`），一个 Ingress 按路径前缀 `/<sdk>` 分流。

### 3.1 准备命名空间和 token Secret
```bash
kubectl create namespace astro-tools
kubectl -n astro-tools create secret generic astro-api-token \
  --from-literal=token=$(openssl rand -hex 24)
```

### 3.2 私有 values 文件（不要提交到仓库）
`astro-private-values.yaml`：
```yaml
image:
  repository: ghcr.io/aaronyang0628/astro-sdk-services
  tag: "<commit-sha>"
  pullPolicy: IfNotPresent
ingress:
  enabled: true
  className: nginx
  host: astro.example.com          # 换成你的域名
  annotations:
    # 仅内网 HTTP 访问时关闭强制跳转 HTTPS
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
    # 需要 HTTPS 时启用 cert-manager：
    # cert-manager.io/cluster-issuer: <your-issuer>
  tls: []
  # tls:
  #   - hosts: [astro.example.com]
  #     secretName: astro-sdk-tls
auth:
  secretName: astro-api-token
resources:
  requests: {cpu: 100m, memory: 512Mi}
  limits: {cpu: "1", memory: 4Gi}
```

### 3.3 安装 / 升级
```bash
git clone https://github.com/AaronYang0628/astro-sdk-services.git
cd astro-sdk-services
helm upgrade --install astro-sdk helm/astro-sdk-services \
  -n astro-tools -f /path/to/astro-private-values.yaml \
  --set image.tag=<commit-sha>
kubectl -n astro-tools rollout status deploy/astro-astropy
kubectl -n astro-tools get pods,svc,ingress
```

### 3.4 验证
```bash
export TOKEN=$(kubectl -n astro-tools get secret astro-api-token -o jsonpath='{.data.token}' | base64 -d)
export BASE=http://astro.example.com          # 或 http://<域名>:<ingress NodePort>
# 若终端设置了 http(s)_proxy，内网地址需要绕过代理：
export NO_PROXY=astro.example.com,$NO_PROXY no_proxy=$NO_PROXY

curl $BASE/astropy/health
curl $BASE/astropy/tools -H "Authorization: Bearer $TOKEN"
curl -X POST $BASE/astroquery/invoke -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"function_name":"astroquery_simbad_query_object","arguments":{"object_name":"M31"}}'

# 全量回归 / MCP 冒烟测试
BASE_URL=$BASE API_TOKEN=$TOKEN python3 tests/run_cases.py astropy
BASE_URL=$BASE API_TOKEN=$TOKEN python3 tests/mcp_check.py
```

### 3.5 回滚 / 卸载
```bash
helm -n astro-tools history astro-sdk
helm -n astro-tools rollback astro-sdk <revision>
helm -n astro-tools uninstall astro-sdk        # 卸载
```

## 4. MCP 客户端接入

每个 SDK 一个 MCP 端点：`<BASE>/<sdk>/mcp`，传输方式 Streamable HTTP，请求头 `Authorization: Bearer <TOKEN>`。

Cursor / 通用 `mcpServers` 配置：
```json
{
  "mcpServers": {
    "astropy": {"url": "http://astro.example.com/astropy/mcp", "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}}
  }
}
```
opencode（`opencode.json`）：
```json
{
  "mcp": {
    "astro-astropy": {
      "type": "remote",
      "url": "http://astro.example.com/astropy/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {"Authorization": "Bearer {env:ASTRO_SDK_TOKEN}"}
    }
  }
}
```
Claude Code：
```bash
claude mcp add --transport http astropy http://astro.example.com/astropy/mcp \
  --header "Authorization: Bearer <YOUR_TOKEN>"
```

## 5. 注意事项

- **安全**：部分工具可读取容器内文件（如 FITS、numpy 文件），务必设置 `API_TOKEN`，不要把 token 写进仓库或公开配置。
- **外网依赖**：astroquery 各工具需要集群能访问 SIMBAD、VizieR、Gaia、MAST 等外部服务；astropy 的 IERS 数据在镜像构建时预取。
- **并发**：单个工具调用执行期间会占用该 SDK 的服务进程，慢查询（如 Gaia）会让同 SDK 的其它请求排队；有需要可增加副本数。
- **超时与资源**：单次调用默认 30 秒超时；每个 Pod 默认内存上限 4Gi。
- **HTTPS**：MCP 客户端（Cursor、Claude）通常要求有效证书。若集群外 80/443 未转发到 Ingress，cert-manager HTTP-01 无法签发，可改用 DNS-01 或内网 HTTP 访问。
