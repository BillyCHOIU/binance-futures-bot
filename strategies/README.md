# FluxBot 自定义策略说明

## 支持的文件格式（扔进 strategies 文件夹即可）

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Python | `.py` | 完全自定义代码 |
| YAML | `.yaml` `.yml` | 推荐，配置型 |
| JSON | `.json` | 同 YAML |
| TOML | `.toml` | 同 YAML |
| 文本 | `.txt` `.ini` `.conf` `.cfg` | `key=value` |
| Markdown | `.md` | 可写 `key: value` 行 |

**不支持真正的「任意二进制」**（如图片/PDF），但常见配置/脚本格式都能加。  
未知扩展名若内容是 YAML/JSON，也可能被识别。

操作：复制文件到策略文件夹 → 界面 **重载** → 下拉选择 → **应用策略**

---

## 不会写代码：配置型（推荐）

```yaml
id: my_yaml_trend
name: 我的均线
type: trend_ema          # trend_ema | rsi_reversion | breakout | rules
params:
  ema_fast: 12
  ema_slow: 48
```

或纯文本：

```text
id=my_s
name=我的策略
type=rsi_reversion
oversold=25
overbought=75
```

---

## 规则组合 type: rules

见 `example_rules.yaml`。条件包括：

- `ema_fast_above_slow` / `ema_fast_below_slow`
- `rsi_below` / `rsi_above`
- `price_above_sma` / `price_below_sma`
- `breakout_high` / `breakout_low`

---

## Python 插件

见 `example_dual_ma.py`，需 `class Strategy` 与 `evaluate(...)`。

---

## 注意

- 文件名不要用奇怪符号；建议英文
- 来源不明的 `.py` 不要运行
- 安装版目录：`%LOCALAPPDATA%\FluxBot\strategies\`
