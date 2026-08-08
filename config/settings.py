"""
T3 Trading Account Configuration
Hard constraints for the $10k prop account.
All systems must respect these values.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    multiplier: float          # $ per full point
    tick_size: float
    tick_value: float
    max_contracts: int         # firm position limit
    point_value_note: str


# Exact specs for the products we are allowed to trade
CONTRACTS: Dict[str, ContractSpec] = {
    "MES": ContractSpec(
        symbol="MES",
        multiplier=5.0,            # $5 per point
        tick_size=0.25,
        tick_value=1.25,
        max_contracts=10,          # 10 MES = 1 ES equivalent
        point_value_note="$5/pt → 10 contracts = $50/pt"
    ),
    "ES": ContractSpec(
        symbol="ES",
        multiplier=50.0,
        tick_size=0.25,
        tick_value=12.50,
        max_contracts=1,
        point_value_note="$50/pt"
    ),
    "MGC": ContractSpec(
        symbol="MGC",
        multiplier=10.0,           # $10 per $1 move in gold
        tick_size=0.10,
        tick_value=1.0,
        max_contracts=5,
        point_value_note="$10 per $1 → 5 contracts = $50 per $1"
    ),
    "SIL": ContractSpec(
        symbol="SIL",
        multiplier=1000.0,         # $1000 per $1 move in silver
        tick_size=0.005,
        tick_value=5.0,
        max_contracts=5,           # full size is extremely aggressive
        point_value_note="$1000 per $1 → 5 contracts = $5000 per $1"
    ),
}


@dataclass(frozen=True)
class AccountLimits:
    account_size: float = 10_000.0
    max_daily_loss: float = 750.0          # hard auto-liq
    soft_daily_loss: float = 500.0         # our internal circuit breaker
    max_planned_risk_per_day: float = 350.0  # target risk budget
    commission_per_contract: float = 0.50  # + exchange pass-throughs
    platform_monthly_fee: float = 574.0    # reduced by 150 if >3500 contracts/month
    profit_split_trader: float = 0.90


ACCOUNT = AccountLimits()


# Risk sizing defaults (can be overridden per strategy)
DEFAULT_RISK_PER_TRADE_PCT = 0.005   # 0.5% of account = $50
MAX_OPEN_RISK_PCT = 0.04             # 4% of account across all positions
