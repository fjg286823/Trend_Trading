# 趋势交易系统

这是一个面向 A 股和 ETF 的趋势交易研究系统，第一版支持：

- 内置示例数据，无网络也能先试用
- AKShare 日线数据与 SQLite 缓存
- 本地 CSV 数据导入
- 基线趋势策略回测
- 虚拟资金模拟撮合
- K 线图、均线、买入/加仓/卖出点展示
- 交易日志与资金曲线

## 快速启动

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

也可以使用脚本：

```bash
# Ubuntu
bash scripts/run_dev.sh

# Windows PowerShell
.\scripts\run_dev.ps1
```

## 构建一键执行文件

PyInstaller 不能稳定跨平台交叉编译，所以 Ubuntu 可执行文件需要在 Ubuntu 构建，Windows `.exe` 需要在 Windows 构建，或通过 GitHub Actions 同时构建两个平台的 artifact。

```bash
# Ubuntu
bash scripts/build_linux.sh
./dist/trend-trade
```

```powershell
# Windows PowerShell
.\scripts\build_windows.ps1
.\dist\trend-trade.exe
```

仓库已包含 `.github/workflows/build.yml`，推送到 GitHub 后可在 Actions 中自动构建 Ubuntu 和 Windows 可执行文件。

## 数据说明

如果 AKShare 因网络或代理不可用，界面左侧选择 `示例数据` 可以离线体验完整回测和图表流程。也可以上传本地 CSV，字段要求：

```text
date, open, high, low, close, volume
```

## 第一版基线策略

- A 股 + ETF
- 日线
- 只做多
- 55 日突破入场
- 20 日低点退出
- 2 ATR 初始止损
- 单笔 1% 账户风险
- 最多 3 次浮盈加仓

## 后续扩展方向

- 增量模拟账户
- 小时线/日线多周期确认
- 股票池批量扫描
- 真实券商接口适配层
- 更严格的 A 股交易规则处理
