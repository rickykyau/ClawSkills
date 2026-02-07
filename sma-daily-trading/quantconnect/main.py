# QuantConnect Algorithm
# SMA Daily Trading Strategy - QQQ Signal → TQQQ Trade
# 
# To run:
# 1. Go to quantconnect.com (free account)
# 2. Create new Algorithm (Python)
# 3. Paste this code
# 4. Backtest from 2021-07-01 to 2026-02-05

from AlgorithmImports import *

class SMADailyTradingStrategy(QCAlgorithm):
    
    def Initialize(self):
        # Backtest period
        self.SetStartDate(2021, 7, 1)
        self.SetEndDate(2026, 2, 5)
        
        # Starting capital
        self.SetCash(10000)
        
        # Add securities
        self.qqq = self.AddEquity("QQQ", Resolution.Daily).Symbol
        self.tqqq = self.AddEquity("TQQQ", Resolution.Daily).Symbol
        
        # Parameters
        self.sma_period = 100
        self.fixed_stop_pct = 0.10  # 10%
        self.trailing_stop_pct = 0.15  # 15%
        
        # Create SMA indicator on QQQ
        self.sma = self.SMA(self.qqq, self.sma_period, Resolution.Daily)
        
        # Track position state
        self.entry_price = None
        self.highest_since_entry = None
        self.signal_memory = False
        self.prev_above_sma = False
        self.t1_cooldown = None
        
        # Warm up SMA
        self.SetWarmUp(self.sma_period, Resolution.Daily)
        
        # Schedule daily check at market close
        self.Schedule.On(
            self.DateRules.EveryDay(self.qqq),
            self.TimeRules.BeforeMarketClose(self.qqq, 1),
            self.CheckSignals
        )
    
    def CheckSignals(self):
        if self.IsWarmingUp:
            return
        
        # Check T+1 cooldown
        if self.t1_cooldown and self.Time.date() <= self.t1_cooldown:
            return
        
        # Get current values
        qqq_price = self.Securities[self.qqq].Close
        tqqq_price = self.Securities[self.tqqq].Close
        sma_value = self.sma.Current.Value
        
        above_sma = qqq_price > sma_value
        cross_above = above_sma and not self.prev_above_sma
        cross_below = not above_sma and self.prev_above_sma
        
        # If in position
        if self.Portfolio[self.tqqq].Invested:
            # Update highest
            if self.highest_since_entry:
                self.highest_since_entry = max(self.highest_since_entry, tqqq_price)
            
            # Calculate stops
            fixed_stop = self.entry_price * (1 - self.fixed_stop_pct)
            trailing_stop = self.highest_since_entry * (1 - self.trailing_stop_pct) if self.highest_since_entry else 0
            effective_stop = max(fixed_stop, trailing_stop)
            
            # Check stop hit
            if tqqq_price <= effective_stop:
                stop_type = "TRAIL" if trailing_stop >= fixed_stop else "FIXED"
                self.Liquidate(self.tqqq, f"{stop_type} STOP")
                self.signal_memory = above_sma  # Set memory if still above SMA
                self.entry_price = None
                self.highest_since_entry = None
                self.t1_cooldown = self.Time.date()
                self.prev_above_sma = above_sma
                return
            
            # Check SMA exit
            if cross_below:
                self.Liquidate(self.tqqq, "SMA EXIT")
                self.signal_memory = False
                self.entry_price = None
                self.highest_since_entry = None
                self.t1_cooldown = self.Time.date()
                self.prev_above_sma = above_sma
                return
        
        # Not in position - check for entry
        else:
            # Signal Memory re-entry
            if self.signal_memory and above_sma:
                self.SetHoldings(self.tqqq, 1.0, False, "REENTRY")
                self.entry_price = tqqq_price
                self.highest_since_entry = tqqq_price
                self.signal_memory = False
            elif self.signal_memory:
                self.signal_memory = False
            
            # Normal crossover entry
            elif cross_above:
                self.SetHoldings(self.tqqq, 1.0, False, "CROSS")
                self.entry_price = tqqq_price
                self.highest_since_entry = tqqq_price
        
        self.prev_above_sma = above_sma
    
    def OnData(self, data):
        # Update highest price intraday if in position
        if self.Portfolio[self.tqqq].Invested and self.tqqq in data.Bars:
            bar = data.Bars[self.tqqq]
            if self.highest_since_entry:
                self.highest_since_entry = max(self.highest_since_entry, bar.High)
