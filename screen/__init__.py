# Stock Screeners
# ================
#
# Three screeners:
# 1. stage2_screener.py      — Stage 2 trend template (Minervini 8 conditions)
# 2. momentum_screener.py    — Momentum stocks near 52-week high
# 3. week10_momentum.py      — Weekly 10% accumulation momentum
#
# Usage:
#   cd ~/Documents/Harbor_stock
#   python3 screen/stage2_screener.py --tickers AAPL NVDA TSLA
#   python3 screen/momentum_screener.py --tickers AAPL NVDA TSLA
#   python3 screen/week10_momentum.py --tickers AAPL NVDA TSLA
#
# Or scan the full default watchlist:
#   python3 screen/stage2_screener.py
#   python3 screen/momentum_screener.py
#   python3 screen/week10_momentum.py
