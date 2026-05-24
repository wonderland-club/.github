# A股选股与仓位控制提醒小程序

已按你的要求默认采用：**平衡型 + 偏好 AI/芯片/半导体/电力 + 日内最大亏损 5%**。

## 策略预设
- `conservative`（稳健）：总仓 60%，单票 20%，止损 -6%，止盈 +12%
- `balanced`（平衡，默认）：总仓 70%，单票 25%，止损 -8%，止盈 +15%
- `aggressive`（进攻）：总仓 85%，单票 35%，止损 -10%，止盈 +20%

## 你的默认风险偏好
- `--profile balanced`
- `--themes AI,芯片,半导体,电力`
- `--max-daily-loss 0.05`

> 日内亏损上限会折算为可用总仓上限：`可用总仓 <= min(预设总仓, max_daily_loss / |stop_loss|)`。

## 快速运行
```bash
python trading_assistant.py \
  --cash 70000 \
  --holding 600587:500:23.80 \
  --holding 002241:300:17.20 \
  --price 600587:25.10 \
  --price 002241:19.30 \
  --candidate 300760 \
  --candidate 688981 \
  --candidate 600900 \
  --price 300760:146.00 \
  --price 688981:45.50 \
  --price 600900:28.00 \
  --session morning \
  --profile balanced \
  --themes AI,芯片,半导体,电力 \
  --max-daily-loss 0.05
```

## 定时提醒（交易日1~2次）
```cron
25 9 * * 1-5 cd /workspace/.github && /usr/bin/python3 trading_assistant.py ... --session morning --profile balanced --themes AI,芯片,半导体,电力 --max-daily-loss 0.05 >> trade.log 2>&1
20 14 * * 1-5 cd /workspace/.github && /usr/bin/python3 trading_assistant.py ... --session afternoon --profile balanced --themes AI,芯片,半导体,电力 --max-daily-loss 0.05 >> trade.log 2>&1
```
