# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion

class SMA50CrossoverStrategyFull(QCAlgorithm):
    """
    SMA(50) Crossover Strategy - Full Implementation
    
    Signal: QQQ crosses above/below 50-day SMA
    Trade: TQQQ (3x leveraged QQQ)
    
    Strategy Rules:
    ════════════════════════════════════════════════════════════════
    | Rule           | Value                                        |
    |----------------|----------------------------------------------|
    | Signal Source  | QQQ daily close                              |
    | Indicator      | 50-day SMA                                   |
    | Trade Asset    | TQQQ (3x leveraged)                          |
    | Check Freq     | Every 15 minutes                             |
    | Fixed Stop     | 7.5% from entry price                        |
    | Trailing Stop  | 15% from highest price                       |
    | STOP LOGIC     | Use whichever stop is HIGHER (loses less)    |
    | BUY            | QQQ crosses above 50 SMA                     |
    | SELL           | QQQ crosses below 50 SMA OR stop hit         |
    ════════════════════════════════════════════════════════════════
    """

    def initialize(self):
        # ══════════════════════════════════════════════════════════
        # BACKTEST CONFIGURATION
        # ══════════════════════════════════════════════════════════
        self.set_start_date(2021, 1, 5)
        self.set_end_date(2026, 2, 6)
        self.set_cash(10000)
        
        # Benchmark
        self.set_benchmark("QQQ")
        
        # ══════════════════════════════════════════════════════════
        # ASSETS
        # ══════════════════════════════════════════════════════════
        self.signal_symbol = self.add_equity("QQQ", Resolution.MINUTE).symbol
        self.trade_symbol = self.add_equity("TQQQ", Resolution.MINUTE).symbol
        
        # ══════════════════════════════════════════════════════════
        # STRATEGY PARAMETERS
        # ══════════════════════════════════════════════════════════
        self.sma_period = 50
        self.fixed_stop_pct = 0.075   # 7.5%
        self.trailing_stop_pct = 0.15  # 15%
        
        # ══════════════════════════════════════════════════════════
        # INDICATORS
        # ══════════════════════════════════════════════════════════
        # SMA on QQQ daily closes
        self.sma = self.SMA(self.signal_symbol, self.sma_period, Resolution.DAILY)
        
        # ══════════════════════════════════════════════════════════
        # STATE TRACKING
        # ══════════════════════════════════════════════════════════
        self.entry_price = 0
        self.highest_since_entry = 0
        self.prev_above_sma = None
        self.last_exit_date = None
        
        # Trade logging
        self.trades = []
        self.current_trade = None
        
        # ══════════════════════════════════════════════════════════
        # SCHEDULING
        # ══════════════════════════════════════════════════════════
        # Check every 15 minutes during market hours
        self.schedule.on(
            self.date_rules.every_day(self.signal_symbol),
            self.time_rules.every(timedelta(minutes=15)),
            self.check_strategy
        )
        
        # Warm up period for SMA
        self.set_warm_up(self.sma_period + 10, Resolution.DAILY)

    def check_strategy(self):
        """Main strategy logic - runs every 15 minutes"""
        
        if self.is_warming_up:
            return
        
        if not self.sma.is_ready:
            return
        
        # Get current data
        qqq = self.securities[self.signal_symbol]
        tqqq = self.securities[self.trade_symbol]
        
        if qqq.price == 0 or tqqq.price == 0:
            return
        
        qqq_price = qqq.price
        tqqq_price = tqqq.price
        tqqq_high = tqqq.high if tqqq.high > 0 else tqqq_price
        tqqq_low = tqqq.low if tqqq.low > 0 else tqqq_price
        sma_value = self.sma.current.value
        
        above_sma = qqq_price > sma_value
        
        # ══════════════════════════════════════════════════════════
        # CHECK EXITS (if in position)
        # ══════════════════════════════════════════════════════════
        if self.portfolio[self.trade_symbol].invested:
            # Update highest using the bar's high
            if tqqq_high > self.highest_since_entry:
                self.highest_since_entry = tqqq_high
            
            # Calculate stop levels
            fixed_stop = self.entry_price * (1 - self.fixed_stop_pct)
            trailing_stop = self.highest_since_entry * (1 - self.trailing_stop_pct)
            active_stop = max(fixed_stop, trailing_stop)
            
            exit_reason = None
            exit_price = None
            
            # Check if stop hit (use LOW for realistic execution)
            if tqqq_low <= active_stop:
                exit_reason = "TRAIL" if trailing_stop >= fixed_stop else "FIXED"
                exit_price = active_stop  # Assume filled at stop price
            
            # Check SMA cross down
            elif self.prev_above_sma == True and above_sma == False:
                exit_reason = "SMA"
                exit_price = tqqq_price
            
            # Execute exit
            if exit_reason:
                self.execute_exit(exit_reason, exit_price)
        
        # ══════════════════════════════════════════════════════════
        # CHECK ENTRIES (if not in position)
        # ══════════════════════════════════════════════════════════
        else:
            # T+1 cooldown: no same-day re-entry
            if self.last_exit_date == self.time.date():
                pass  # Skip entry today
            
            # Cross above SMA
            elif self.prev_above_sma == False and above_sma == True:
                self.execute_entry(tqqq_price, tqqq_high, "CROSS")
        
        # Update state
        self.prev_above_sma = above_sma

    def execute_entry(self, price, high, entry_type):
        """Execute entry and log"""
        self.set_holdings(self.trade_symbol, 1.0)
        self.entry_price = price
        self.highest_since_entry = high
        
        self.current_trade = {
            'entry_date': self.time.strftime('%Y-%m-%d'),
            'entry_time': self.time.strftime('%H:%M'),
            'entry_price': price,
            'entry_type': entry_type
        }
        
        self.log(f"ENTRY | {entry_type} | TQQQ @ ${price:.2f} | QQQ {'>' if self.prev_above_sma else '<'} SMA({self.sma_period})")

    def execute_exit(self, reason, price):
        """Execute exit and log"""
        pnl_pct = (price - self.entry_price) / self.entry_price * 100
        pnl_dollar = self.portfolio[self.trade_symbol].quantity * (price - self.entry_price)
        
        self.liquidate(self.trade_symbol)
        self.last_exit_date = self.time.date()
        
        # Complete trade record
        if self.current_trade:
            self.current_trade.update({
                'exit_date': self.time.strftime('%Y-%m-%d'),
                'exit_time': self.time.strftime('%H:%M'),
                'exit_price': price,
                'exit_reason': reason,
                'pnl_pct': pnl_pct,
                'pnl_dollar': pnl_dollar
            })
            self.trades.append(self.current_trade)
            self.current_trade = None
        
        self.log(f"EXIT  | {reason} | TQQQ @ ${price:.2f} | P&L: {pnl_pct:+.1f}% (${pnl_dollar:+,.0f})")
        
        # Reset state
        self.entry_price = 0
        self.highest_since_entry = 0

    def on_end_of_algorithm(self):
        """Generate final report"""
        self.log("")
        self.log("=" * 80)
        self.log(" FINAL RESULTS - SMA(50) STRATEGY")
        self.log("=" * 80)
        self.log("")
        self.log(f"Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        self.log(f"Starting Capital: $10,000")
        self.log("")
        
        final_value = self.portfolio.total_portfolio_value
        total_return = (final_value / 10000 - 1) * 100
        
        self.log(f"Strategy Final:     ${final_value:,.0f} ({total_return:+.1f}%)")
        self.log("")
        self.log(f"Total Trades:       {len(self.trades)}")
        
        if self.trades:
            # Exit breakdown
            fixed_exits = len([t for t in self.trades if t.get('exit_reason') == 'FIXED'])
            trail_exits = len([t for t in self.trades if t.get('exit_reason') == 'TRAIL'])
            sma_exits = len([t for t in self.trades if t.get('exit_reason') == 'SMA'])
            
            self.log("")
            self.log("Exit Breakdown:")
            self.log(f"  - Fixed Stop:     {fixed_exits}")
            self.log(f"  - Trailing Stop:  {trail_exits}")
            self.log(f"  - SMA Exit:       {sma_exits}")
            
            # Win rate
            wins = [t for t in self.trades if t.get('pnl_pct', 0) > 0]
            losses = [t for t in self.trades if t.get('pnl_pct', 0) <= 0]
            win_rate = len(wins) / len(self.trades) * 100
            
            avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
            
            self.log("")
            self.log(f"Win Rate:           {win_rate:.0f}% ({len(wins)}/{len(self.trades)})")
            self.log(f"Avg Win:            {avg_win:+.1f}%")
            self.log(f"Avg Loss:           {avg_loss:+.1f}%")
        
        self.log("")
        self.log("=" * 80)
