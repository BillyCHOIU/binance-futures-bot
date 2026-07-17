# FluxBot 模块架构（重构后）

```
GUI (main)
   │
   ▼
Engine  ── 组装与主循环
   ├── RiskManager     风控（日亏/回撤/仓位）
   ├── BracketBook     本地止损止盈
   ├── BinanceFutures  交易所适配
   ├── Strategy        信号（内置 + 多格式插件）
   ├── SentimentEngine 舆情门控
   └── Store           SQLite 日志
```

## 分层

| 层 | 模块 | 职责 |
|----|------|------|
| 基础 | `paths` | 可写目录、打包资源、首次落盘 |
| 配置 | `config_loader` | yaml + .env 注入、logging |
| 存储 | `storage` | events / trades / equity |
| 风控 | `risk` | 熔断、仓位上限、下单量 |
| 交易所 | `exchange` | ccxt 封装、Position |
| 策略 | `strategy/*` | base / 内置 / 声明式 / 注册表 |
| 舆情 | `news/*` | scoring + SentimentEngine 采集 |
| 引擎 | `engine` | tick 循环、开平仓 |
| UI | `main` | 控件与配置读写 |

## 兼容

- 入口仍是 `python -m app.main` / `run_fluxbot.py` / 安装包
- 配置字段与 GUI 行为保持不变
