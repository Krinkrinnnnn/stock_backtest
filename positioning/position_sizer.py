"""
Position Sizing Module
======================
Handles risk management and position sizing calculations based on Account Risk and Trade Risk.
"""

def calculate_position_size(total_equity, available_cash, entry_price, 
                            risk_per_trade_pct, max_drawdown_per_trade_pct, max_position_size_pct):
    """
    Calculate the number of shares to buy based on risk parameters.
    
    Formula:
    1. Risk Amount = Total Equity * Risk_Per_Trade_Pct (e.g. 2%)
    2. Risk Per Share = Entry Price * Max_Drawdown_Per_Trade (e.g. 8% stop loss)
    3. Target Shares = Risk Amount / Risk Per Share
    4. Apply Cap = Target Shares must not exceed Total Equity * Max_Position_Size (e.g. 40%)
    
    Args:
        total_equity (float): Total portfolio value (cash + positions)
        available_cash (float): Currently available cash to trade
        entry_price (float): Price of the asset to buy
        risk_per_trade_pct (float): % of total equity willing to risk per trade (e.g. 0.02)
        max_drawdown_per_trade_pct (float): % stop-loss distance per trade (e.g. 0.08)
        max_position_size_pct (float): absolute max % of total equity allowed for one position (e.g. 0.40)
        
    Returns:
        int: Number of shares to purchase safely.
    """
    if entry_price <= 0:
        return 0
        
    # 1. Calculate how much dollar amount we are allowed to lose
    risk_amount = total_equity * risk_per_trade_pct
    
    # 2. Calculate dollar risk per share based on our stop loss
    risk_per_share = entry_price * max_drawdown_per_trade_pct
    
    # 3. Target position size (shares)
    if risk_per_share > 0:
        target_size = int(risk_amount / risk_per_share)
    else:
        target_size = 0
        
    # 4. Safety check 1: Apply Maximum Position Size Cap (e.g. 40%)
    max_capital_for_trade = total_equity * max_position_size_pct
    max_shares_by_cap = int(max_capital_for_trade / entry_price)
    
    # 5. Safety check 2: Ensure we don't exceed available cash
    max_shares_by_cash = int(available_cash / entry_price)
    
    # 6. Final Size Determination (take the smallest of the three constraints)
    final_size = min(target_size, max_shares_by_cap, max_shares_by_cash)
    
    # Prevent negative sizes
    return max(0, final_size)
