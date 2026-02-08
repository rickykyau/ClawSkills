# region imports
from AlgorithmImports import *
# endregion

class SMA50CrossoverStrategy(QCAlgorithm):
    """
    SMA(50) Crossover Strategy
    Signal: QQQ crosses above/below 50-day SMA
    Trade: TQQQ (3x leveraged QQQ)
    
    Rules:
    - Entry: QQQ crosses ABOVE 50-day SMA
    - Exit: QQQ crosses BELOW 50-day SMA OR stop hit
    - Fixed Stop: 7.5% below entry price
    - Trailing Stop: 15% below highest price since entry
    - Stop Logic: Use whichever stop is HIGHER (loses less)
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2021, 1, 5)
        self.set_end_date(2026, 2, 6)
        self.set_cash(10000)
        
        # Assets
        self.signal_symbol = self.add_equity("QQQ", Resolution.MINUTE).symbol
        self.trade_symbol = self.add_equity("TQQQ", Resolution.MINUTE).symbol
        
        # Strategy parameters
        self.sma_period = 50
        self.fixed_stop_pct = 0.075  # 7.5%
        self.trailing_stop_pct = 0.15  # 15%
        
        # SMA indicator on QQQ daily
        self.sma = self.SMA(self.signal_symbol, self.sma_period, Resolution.DAILY)
        
        # Track position state
        self.entry_price = 0
        self.highest_since_entry = 0
        self.prev_above_sma = None
        
        # Schedule checks every 15 minutes during market hours
        self.schedule.on(
            self.date_rules.every_day(self.signal_symbol),
            self.time_rules.every(timedelta(minutes=15)),
            self.check_strategy
        )
        
        # Warm up SMA
        self.set_warm_up(self.sma_period, Resolution.DAILY)
        
        # Track trades for logging
        self.trade_count = 0

    def check_strategy(self):
        """Main strategy logic - called every 15 minutes"""
        
        if self.is_warming_up:
            return
        
        if not self.sma.is_ready:
            return
        
        # Get current prices
        qqq_price = self.securities[self.signal_symbol].price
        tqqq_price = self.securities[self.trade_symbol].price
        sma_value = self.sma.current.value
        
        if qqq_price == 0 or tqqq_price == 0:
            return
        
        # Check if QQQ is above SMA
        above_sma = qqq_price > sma_value
        
        # Check exits first
        if self.portfolio[self.trade_symbol].invested:
            self.check_exits(tqqq_price, above_sma)
        
        # Check entries
        elif not self.portfolio[self.trade_symbol].invested:
            self.check_entries(tqqq_price, above_sma)
        
        # Update state
        self.prev_above_sma = above_sma

    def check_exits(self, tqqq_price, above_sma):
        """Check exit conditions"""
        
        # Update highest price
        if tqqq_price > self.highest_since_entry:
            self.highest_since_entry = tqqq_price
        
        # Calculate stops
        fixed_stop = self.entry_price * (1 - self.fixed_stop_pct)
        trailing_stop = self.highest_since_entry * (1 - self.trailing_stop_pct)
        stop_price = max(fixed_stop, trailing_stop)
        
        exit_reason = None
        
        # Check stop loss (use current price as proxy for low)
        if tqqq_price <= stop_price:
            exit_reason = "TRAIL" if trailing_stop >= fixed_stop else "FIXED"
        
        # Check SMA cross down
        elif self.prev_above_sma == True and above_sma == False:
            exit_reason = "SMA"
        
        if exit_reason:
            pnl_pct = (tqqq_price - self.entry_price) / self.entry_price * 100
            self.liquidate(self.trade_symbol)
            self.trade_count += 1
            self.log(f"EXIT #{self.trade_count} | {exit_reason} | Entry: ${self.entry_price:.2f} Exit: ${tqqq_price:.2f} | P&L: {pnl_pct:+.1f}%")
            
            # Reset state
            self.entry_price = 0
            self.highest_since_entry = 0

    def check_entries(self, tqqq_price, above_sma):
        """Check entry conditions"""
        
        # Cross above SMA
        if self.prev_above_sma == False and above_sma == True:
            self.set_holdings(self.trade_symbol, 1.0)
            self.entry_price = tqqq_price
            self.highest_since_entry = tqqq_price
            self.log(f"ENTRY | QQQ crossed above SMA(50) | TQQQ: ${tqqq_price:.2f}")

    def on_end_of_algorithm(self):
        """Log final results"""
        self.log("="*60)
        self.log("FINAL RESULTS")
        self.log("="*60)
        self.log(f"Total Trades: {self.trade_count}")
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Total Return: {(self.portfolio.total_portfolio_value / 10000 - 1) * 100:+.1f}%")
