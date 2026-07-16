# 舆情源接入说明（Reddit 403 / X 未接）

## 现状

| 源 | 你这边情况 | 怎么修 |
|----|------------|--------|
| 币安公告 + RSS | 已可用 | 不用管 |
| Reddit 公开 JSON | 常 **403**（墙/反爬） | 代理 或 官方 API |
| X | 默认无 Token | 申请 Bearer 写入 `.env` |
| CryptoPanic | 新加，聚合新闻 | 可选 Token，更稳 |

**不配也能跑**：靠币安公告 + 媒体 RSS 定方向。Reddit/X 是增强。

---

## 最快：开代理（国内首选）

1. 打开 Clash / V2Ray 等，记下本地端口（常见 `7890`）
2. 编辑 `binance-futures-bot\.env`，加一行：

```env
HTTPS_PROXY=http://127.0.0.1:7890
HTTP_PROXY=http://127.0.0.1:7890
```

3. 重启 `start.bat`，再点「立即刷新舆情摘要」

代理通了以后，Reddit 公开接口有时也能直接过。

---

## Reddit 官方 API（更稳）

1. 登录 Reddit → https://www.reddit.com/prefs/apps  
2. Create App → 类型选 **script**  
3. 拿到 `client_id`（名字下面那串）和 `secret`  
4. 写入 `.env`：

```env
REDDIT_CLIENT_ID=你的id
REDDIT_CLIENT_SECRET=你的secret
REDDIT_USER_AGENT=FluxBot/0.1 by 你的用户名
```

5. 若仍 403：继续加 `HTTPS_PROXY`（API 域名也被墙时必须代理）

---

## X（Twitter）接入

1. 打开 https://developer.x.com 申请开发者  
2. 创建 Project/App → 拿到 **Bearer Token**  
3. 写入 `.env`：

```env
X_BEARER_TOKEN=你的Bearer
```

4. `config.yaml` 里 `news.sources.x: true`（默认已 true）  
5. 重启软件  

说明：X 免费档额度很少；付费 Basic 才比较能用 recent search。没 Token 时日志只提示一次，不刷屏。

---

## CryptoPanic（推荐补强）

1. https://cryptopanic.com/developers/api/ 注册拿 token（可空跑 public）  
2. `.env`：

```env
CRYPTOPANIC_TOKEN=你的token
```

聚合站，有时比直连 Reddit 更容易访问。

---

## config.yaml 开关

```yaml
news:
  sources:
    binance_announcement: true
    rss: true
    cryptopanic: true
    reddit: true   # 一直 403 可改 false
    x: true        # 没 Token 会自动跳过
```

---

## 怎么确认修好

重启 → 连接 → 点 **立即刷新舆情摘要**  

日志里应出现类似：

- `舆情源状态: {..., 'reddit': 'oauth', 'x': 'bearer', ...}`  
- `Reddit OAuth 已就绪` / `X 拉取 N 条` / `CryptoPanic 拉取 N 条`  
- `sources={'binance':..,'x':..,'reddit':..}`  

仍只有 binance/rss：先查代理端口，再查 Token 是否写错、是否保存到**同一目录**的 `.env`。
