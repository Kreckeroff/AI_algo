# Indicator families (wave 2)

Vectorized BT families in this session (Desktop `.italgo` ports can follow ranking):

1. supertrend_rsi — SuperTrend + RSI50 cross
2. ema_cross — EMA9/21 cross
3. macd_cross — MACD/signal cross
4. bb_mean_rev — Bollinger mean reversion
5. rsi_ob_os — RSI 30/70 exits from extremes
6. stochastic — Stoch K/D in OS/OB
7. adx_di — ADX>25 + DI cross
8. donchian — 20-bar Donchian breakout
9. keltner — Keltner channel breakout
10. cci — CCI ±100 reclaim
11. dual_sma_rsi — SMA20/50 + RSI filter
12. roc_momentum — ROC(10) zero-cross

Each: v0 → v1 (+EMA50 trend filter) → v2 (+ATR 1.5/3.0 SL/TP).
