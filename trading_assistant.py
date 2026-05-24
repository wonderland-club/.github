#!/usr/bin/env python3
"""
A股选股与仓位控制提醒小程序
支持稳健/平衡/进攻三种预设，默认平衡型。
可设置偏好赛道与日内最大亏损约束。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from dataclasses import dataclass
from typing import Dict, List
from urllib import request

LOT_SIZE = 100


@dataclass
class Holding:
    code: str
    shares: int
    cost: float


@dataclass
class StrategyConfig:
    max_total_position: float
    max_single_position: float
    stop_loss: float
    take_profit: float


PRESET_CONFIGS: Dict[str, StrategyConfig] = {
    "conservative": StrategyConfig(0.60, 0.20, -0.06, 0.12),
    "balanced": StrategyConfig(0.70, 0.25, -0.08, 0.15),
    "aggressive": StrategyConfig(0.85, 0.35, -0.10, 0.20),
}


class TradingAssistant:
    def __init__(self, cash: float, holdings: List[Holding], config: StrategyConfig, max_daily_loss: float):
        self.cash = cash
        self.holdings = {h.code: h for h in holdings}
        self.config = config
        self.max_daily_loss = max_daily_loss

    @staticmethod
    def is_trading_day(today: dt.date) -> bool:
        return today.weekday() < 5

    def market_value(self, prices: Dict[str, float]) -> float:
        return sum(h.shares * prices.get(h.code, 0.0) for h in self.holdings.values())

    def total_assets(self, prices: Dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def pnl_ratio(self, code: str, prices: Dict[str, float]) -> float:
        h = self.holdings.get(code)
        if not h or h.cost <= 0:
            return 0.0
        return prices.get(code, h.cost) / h.cost - 1.0

    def max_allowed_position_by_daily_risk(self, assets: float) -> float:
        """
        粗略风险预算：若触发策略止损，日内最大预估损失不超过 max_daily_loss。
        position * abs(stop_loss) <= max_daily_loss
        """
        if abs(self.config.stop_loss) <= 0:
            return self.config.max_total_position
        risk_bound = self.max_daily_loss / abs(self.config.stop_loss)
        return min(self.config.max_total_position, max(risk_bound, 0.0))

    def generate_actions(self, prices: Dict[str, float], candidates: List[str], session: str, themes: List[str]) -> List[str]:
        actions: List[str] = []
        assets = self.total_assets(prices)
        market_value = self.market_value(prices)
        current_pos = market_value / assets if assets else 0.0

        for code, h in self.holdings.items():
            p = prices.get(code)
            if p is None:
                actions.append(f"{code}: 缺少实时价格，暂不处理")
                continue
            r = self.pnl_ratio(code, prices)
            if r <= self.config.stop_loss:
                sell_qty = (h.shares // LOT_SIZE) * LOT_SIZE
                if sell_qty > 0:
                    actions.append(f"{code}: 触发止损({r:.1%})，建议卖出 {sell_qty} 股")
            elif r >= self.config.take_profit:
                sell_qty = (h.shares // LOT_SIZE // 2) * LOT_SIZE
                if sell_qty > 0:
                    actions.append(f"{code}: 达到止盈({r:.1%})，建议分批止盈卖出 {sell_qty} 股")

        pos_cap = self.max_allowed_position_by_daily_risk(assets)
        if current_pos > pos_cap:
            need_reduce = (current_pos - pos_cap) * assets
            actions.append(f"当前总仓位 {current_pos:.1%} 高于风控上限 {pos_cap:.1%}，需减仓约 ¥{need_reduce:.0f}")

        if candidates:
            remain_buying_power = max(pos_cap * assets - market_value, 0.0)
            per_stock_cap = self.config.max_single_position * assets
            eq_budget = remain_buying_power / max(len(candidates), 1)

            for code in candidates:
                p = prices.get(code)
                if p is None or p <= 0:
                    actions.append(f"{code}: 无可用价格，跳过")
                    continue

                current_value = self.holdings.get(code, Holding(code, 0, p)).shares * p
                max_add_value = max(per_stock_cap - current_value, 0.0)
                budget = min(eq_budget, max_add_value, self.cash)
                qty = math.floor(budget / p / LOT_SIZE) * LOT_SIZE
                if qty >= LOT_SIZE:
                    actions.append(f"{code}: 建议买入 {qty} 股，参考金额约 ¥{qty * p:.0f}")
                    self.cash -= qty * p
                else:
                    actions.append(f"{code}: 资金/仓位不足，不建议新增")

        if not actions:
            actions.append("今日策略：持仓观察，不做交易")

        prefix = "早盘提醒" if session == "morning" else "午盘提醒"
        strategy_line = (
            f"策略: 总仓≤{self.config.max_total_position:.0%}, 单票≤{self.config.max_single_position:.0%}, "
            f"止损{self.config.stop_loss:.0%}, 止盈+{self.config.take_profit:.0%}, 日内亏损上限{self.max_daily_loss:.1%}"
        )
        risk_line = f"风险折算后可用总仓上限: {pos_cap:.1%}"
        theme_line = f"偏好赛道: {', '.join(themes) if themes else '未设置'}"
        return [f"[{prefix}] 总资产估算 ¥{assets:.2f}，当前仓位 {current_pos:.1%}", strategy_line, risk_line, theme_line] + actions


def parse_holding(raw: str) -> Holding:
    code, shares, cost = raw.split(":")
    return Holding(code=code, shares=int(shares), cost=float(cost))


def parse_price(raw: str) -> tuple[str, float]:
    code, price = raw.split(":")
    return code, float(price)


def push_serverchan(key: str, title: str, content: str) -> None:
    url = f"https://sctapi.ftqq.com/{key}.send"
    payload = json.dumps({"title": title, "desp": content}).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=10) as resp:
        resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="A股交易日提醒小程序")
    parser.add_argument("--cash", type=float, required=True)
    parser.add_argument("--holding", action="append", default=[], help="格式: 代码:股数:成本")
    parser.add_argument("--price", action="append", default=[], help="格式: 代码:现价")
    parser.add_argument("--candidate", action="append", default=[], help="候选股票代码，可多个")
    parser.add_argument("--session", choices=["morning", "afternoon"], default="morning")
    parser.add_argument("--profile", choices=["conservative", "balanced", "aggressive"], default="balanced")
    parser.add_argument("--max-daily-loss", type=float, default=0.05, help="日内最大亏损比例，例如0.05")
    parser.add_argument("--themes", default="AI,芯片,半导体,电力", help="偏好赛道，逗号分隔")
    parser.add_argument("--serverchan-key", default="", help="可选，填写后自动推送")
    args = parser.parse_args()

    today = dt.date.today()
    if not TradingAssistant.is_trading_day(today):
        print(f"今天是 {today}，非交易日，不触发提醒")
        return

    holdings = [parse_holding(x) for x in args.holding]
    prices = dict(parse_price(x) for x in args.price)
    config = PRESET_CONFIGS[args.profile]
    themes = [x.strip() for x in args.themes.split(",") if x.strip()]

    ta = TradingAssistant(args.cash, holdings, config, args.max_daily_loss)
    lines = ta.generate_actions(prices, args.candidate, args.session, themes)
    message = "\n".join(lines)
    print(message)

    if args.serverchan_key:
        title = f"A股{('早盘' if args.session == 'morning' else '午盘')}策略提醒({args.profile})"
        push_serverchan(args.serverchan_key, title, message)
        print("\n已推送到 Server酱")


if __name__ == "__main__":
    main()
