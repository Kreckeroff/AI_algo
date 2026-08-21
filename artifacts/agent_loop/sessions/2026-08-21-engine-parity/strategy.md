# Parity strategy: SMA Cross 20/50

- Long-only: SMA(20) cross up SMA(50) → open; cross down → close
- Signal on bar close; fill at **next open**
- Slippage 0.01%, commission 0.04% (cash only; trade PnL = exit−entry points)
- No force-close at end of data
- Desktop: `09-sma-cross-20-50.italgo`
- AI_algo: GraphDTO + mirror BT in `run_parity.py`
