import { useEffect, useState } from 'react'
import axios from 'axios'

export function DashboardTab() {
  const [botMode, setBotMode] = useState(null)
  const [riskSummary, setRiskSummary] = useState(null)
  const [paperAccount, setPaperAccount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true)
        // Get bot mode
        const modeRes = await axios.get('http://127.0.0.1:8000/api/bot/mode')
        setBotMode(modeRes.data)

        // Get risk summary
        const riskRes = await axios.get('http://127.0.0.1:8000/api/risk/summary')
        setRiskSummary(riskRes.data)

        // Get paper account (if in PAPER mode)
        if (modeRes.data.mode === 'PAPER') {
          const accountRes = await axios.get('http://127.0.0.1:8000/api/paper/account')
          setPaperAccount(accountRes.data)
        }

        setError(null)
      } catch (err) {
        setError(err.message)
        console.error('Error fetching dashboard:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchDashboard()
    const interval = setInterval(fetchDashboard, 5000) // Refresh every 5s
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="tab-content"><p>Loading...</p></div>
  if (error) return <div className="tab-content"><p style={{color: 'red'}}>Error: {error}</p></div>

  const modeColors = {
    'LIVE': '#ff4444',
    'PAPER': '#44aa44',
    'BACKTEST': '#4444ff'
  }

  const modeDescriptions = {
    'LIVE': 'Real Money - DANGEROUS! Trade with actual capital',
    'PAPER': 'Virtual Money - SAFE! Perfect for testing',
    'BACKTEST': 'Historical Data - Testing strategies'
  }

  return (
    <div className="tab-content">
      <h2>📊 Dashboard Overview</h2>
      
      {/* Mode Badge */}
      {botMode && (
        <div className="mode-badge" style={{borderColor: modeColors[botMode.mode]}}>
          <h3 style={{color: modeColors[botMode.mode]}}>
            🎯 Current Mode: {botMode.mode}
          </h3>
          <p>{modeDescriptions[botMode.mode]}</p>
        </div>
      )}

      {/* Paper Account Status */}
      {paperAccount && (
        <div className="card">
          <h3>💰 Paper Trading Account</h3>
          <div className="grid-2">
            <div className="stat">
              <label>Balance</label>
              <value>${paperAccount.balance.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Total Equity</label>
              <value>${paperAccount.total_equity.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Total P&L</label>
              <value style={{color: paperAccount.total_pnl >= 0 ? 'green' : 'red'}}>
                ${paperAccount.total_pnl.toFixed(2)} ({paperAccount.pnl_pct.toFixed(2)}%)
              </value>
            </div>
            <div className="stat">
              <label>Open Positions</label>
              <value>{paperAccount.open_positions}</value>
            </div>
          </div>
        </div>
      )}

      {/* Risk Management Status */}
      {riskSummary && (
        <div className="card">
          <h3>🛡️ Risk Management Status</h3>
          
          <div style={{
            padding: '12px',
            marginBottom: '12px',
            borderRadius: '4px',
            backgroundColor: riskSummary.risk_level === 'HIGH' ? '#ffcccc' : 
                            riskSummary.risk_level === 'MEDIUM' ? '#ffeecc' : '#ccffcc',
            borderLeft: `4px solid ${riskSummary.risk_level === 'HIGH' ? '#ff0000' : 
                                   riskSummary.risk_level === 'MEDIUM' ? '#ffaa00' : '#00aa00'}`
          }}>
            <strong>Risk Level: {riskSummary.risk_level}</strong>
          </div>

          <div className="grid-3">
            <div className="stat">
              <label>Current Drawdown</label>
              <value>{riskSummary.current_drawdown_pct.toFixed(2)}%</value>
              <small>Limit: {riskSummary.limits.max_drawdown_pct}%</small>
            </div>
            <div className="stat">
              <label>Daily P&L</label>
              <value style={{color: riskSummary.daily_pnl >= 0 ? 'green' : 'red'}}>
                ${riskSummary.daily_pnl.toFixed(2)}
              </value>
              <small>Limit: {riskSummary.limits.max_daily_loss_pct}%</small>
            </div>
            <div className="stat">
              <label>Open Positions</label>
              <value>{riskSummary.open_positions}/{riskSummary.limits.max_positions}</value>
            </div>
            <div className="stat">
              <label>Max Position Size</label>
              <value>{riskSummary.limits.max_position_size_pct}%</value>
            </div>
            <div className="stat">
              <label>Risk per Trade</label>
              <value>{riskSummary.limits.risk_per_trade_pct}%</value>
            </div>
            <div className="stat">
              <label>Trades Today</label>
              <value>{riskSummary.trades_today}</value>
            </div>
          </div>

          {/* Risk Progress Bars */}
          <div style={{marginTop: '16px'}}>
            <div className="progress-bar">
              <label>Drawdown Usage</label>
              <div style={{
                width: '100%',
                height: '20px',
                backgroundColor: '#eee',
                borderRadius: '4px',
                overflow: 'hidden'
              }}>
                <div style={{
                  width: `${Math.min((riskSummary.current_drawdown_pct / riskSummary.limits.max_drawdown_pct) * 100, 100)}%`,
                  height: '100%',
                  backgroundColor: '#ff6b6b',
                  transition: 'width 0.3s'
                }}></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Safety Checklist */}
      <div className="card">
        <h3>✅ Safety Checklist</h3>
        <ul style={{listStyle: 'none', padding: 0}}>
          <li>✅ Backtesting available</li>
          <li>✅ Paper trading enabled</li>
          <li>✅ Fee calculation active</li>
          <li>✅ Risk management engaged</li>
          <li>✅ Default mode is PAPER (safe)</li>
        </ul>
        {botMode?.mode === 'LIVE' && (
          <div style={{
            padding: '12px',
            marginTop: '12px',
            backgroundColor: '#ffcccc',
            border: '2px solid #ff0000',
            borderRadius: '4px',
            color: '#cc0000'
          }}>
            <strong>⚠️ WARNING: LIVE TRADING MODE ACTIVE</strong>
            <p>You are trading with REAL MONEY. Be careful!</p>
          </div>
        )}
      </div>
    </div>
  )
}
