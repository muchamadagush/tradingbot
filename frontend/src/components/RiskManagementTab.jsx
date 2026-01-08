import { useState } from 'react'
import axios from 'axios'

export function RiskManagementTab() {
  // Position Sizing
  const [psCapital, setPsCapital] = useState(1000)
  const [psEntryPrice, setPsEntryPrice] = useState(50000)
  const [psStopLoss, setPsStopLoss] = useState(48500)
  const [psResult, setPsResult] = useState(null)

  // Kelly Criterion
  const [kellyWinRate, setKellyWinRate] = useState(55)
  const [kellyAvgWin, setKellyAvgWin] = useState(50)
  const [kellyAvgLoss, setKellyAvgLoss] = useState(30)
  const [kellyResult, setKellyResult] = useState(null)

  // Risk Summary
  const [riskSummary, setRiskSummary] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const calculatePositionSize = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post('http://127.0.0.1:8000/api/risk/position-size', {
        capital: psCapital,
        entry_price: psEntryPrice,
        stop_loss_price: psStopLoss
      })
      setPsResult(res.data)
    } catch (err) {
      setError('Failed to calculate position size')
    } finally {
      setLoading(false)
    }
  }

  const calculateKelly = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post('http://127.0.0.1:8000/api/risk/kelly', {
        win_rate: kellyWinRate,
        avg_win: kellyAvgWin,
        avg_loss: kellyAvgLoss
      })
      setKellyResult(res.data)
    } catch (err) {
      setError('Failed to calculate Kelly')
    } finally {
      setLoading(false)
    }
  }

  const fetchRiskSummary = async () => {
    try {
      setLoading(true)
      const res = await axios.get('http://127.0.0.1:8000/api/risk/summary')
      setRiskSummary(res.data)
    } catch (err) {
      setError('Failed to fetch risk summary')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tab-content">
      <h2>🛡️ Risk Management Tools</h2>

      {error && (
        <div style={{
          padding: '12px',
          backgroundColor: '#ffcccc',
          border: '1px solid #ff0000',
          borderRadius: '4px',
          color: '#cc0000',
          marginBottom: '12px'
        }}>
          ❌ {error}
        </div>
      )}

      {/* Position Sizing */}
      <div className="card">
        <h3>📊 Position Sizing Calculator</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate optimal position size based on risk management (Fixed Fractional method)
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Capital ($)</label>
            <input
              type="number"
              min="100"
              step="100"
              value={psCapital}
              onChange={(e) => setPsCapital(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Entry Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={psEntryPrice}
              onChange={(e) => setPsEntryPrice(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Stop-Loss Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={psStopLoss}
              onChange={(e) => setPsStopLoss(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button onClick={calculatePositionSize} disabled={loading} className="btn-primary">
          💡 Calculate Position Size
        </button>

        {psResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            {psResult.status === 'success' ? (
              <>
                <h4>{psResult.message}</h4>
                <div className="grid-3" style={{marginTop: '12px'}}>
                  <div className="stat">
                    <label>Position Size</label>
                    <value>{psResult.position_size.toFixed(8)}</value>
                  </div>
                  <div className="stat">
                    <label>Position Value</label>
                    <value>${psResult.position_value_usdt.toFixed(2)}</value>
                  </div>
                  <div className="stat">
                    <label>% of Capital</label>
                    <value>{psResult.position_pct.toFixed(2)}%</value>
                  </div>
                  <div className="stat">
                    <label>Risk Amount</label>
                    <value>${psResult.risk_amount.toFixed(2)}</value>
                  </div>
                  <div className="stat">
                    <label>Risk %</label>
                    <value>{psResult.risk_pct.toFixed(2)}%</value>
                  </div>
                  <div className="stat">
                    <label>Price Risk/Unit</label>
                    <value>${psResult.price_risk_per_unit.toFixed(6)}</value>
                  </div>
                </div>
                {psResult.capped && (
                  <div style={{marginTop: '12px', padding: '8px', backgroundColor: '#ffffcc', borderRadius: '4px', color: '#666'}}>
                    ℹ️ Position size capped to max allowed (20% of capital)
                  </div>
                )}
              </>
            ) : (
              <p style={{color: 'red'}}>Error: {psResult.message}</p>
            )}
          </div>
        )}
      </div>

      {/* Kelly Criterion */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>🎰 Kelly Criterion Calculator</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate optimal position size based on your trading statistics
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Win Rate (%)</label>
            <input
              type="number"
              min="1"
              max="100"
              step="1"
              value={kellyWinRate}
              onChange={(e) => setKellyWinRate(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Average Win ($)</label>
            <input
              type="number"
              min="1"
              step="10"
              value={kellyAvgWin}
              onChange={(e) => setKellyAvgWin(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Average Loss ($)</label>
            <input
              type="number"
              min="1"
              step="10"
              value={kellyAvgLoss}
              onChange={(e) => setKellyAvgLoss(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button onClick={calculateKelly} disabled={loading} className="btn-primary">
          🎯 Calculate Kelly %
        </button>

        {kellyResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            {kellyResult.status === 'success' ? (
              <>
                <h4>{kellyResult.message}</h4>
                <div className="grid-3" style={{marginTop: '12px'}}>
                  <div className="stat">
                    <label>Full Kelly %</label>
                    <value style={{fontSize: '18px', color: kellyResult.kelly_pct >= 0 ? '#0066cc' : 'red'}}>
                      {kellyResult.kelly_pct.toFixed(2)}%
                    </value>
                  </div>
                  <div className="stat">
                    <label>Half Kelly %</label>
                    <value style={{fontSize: '18px', color: '#ff9900'}}>
                      {kellyResult.half_kelly_pct.toFixed(2)}%
                    </value>
                  </div>
                  <div className="stat">
                    <label>Quarter Kelly %</label>
                    <value style={{fontSize: '18px', color: '#66cc00'}}>
                      {kellyResult.quarter_kelly_pct.toFixed(2)}%
                    </value>
                  </div>
                </div>
                <div style={{marginTop: '12px', padding: '8px', backgroundColor: '#e6f2ff', borderRadius: '4px', borderLeft: '4px solid #0066cc'}}>
                  <strong>Recommendation:</strong> {kellyResult.recommendation}
                </div>
                <div style={{marginTop: '12px', fontSize: '13px', color: '#666'}}>
                  <p><strong>Full Kelly:</strong> Most aggressive. Use only if very confident.</p>
                  <p><strong>Half Kelly:</strong> Moderate risk. Good balance for most traders.</p>
                  <p><strong>Quarter Kelly:</strong> Conservative. Best for learning & testing.</p>
                </div>
              </>
            ) : (
              <p style={{color: 'red'}}>Error: {kellyResult.message}</p>
            )}
          </div>
        )}
      </div>

      {/* Risk Summary */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>📈 Current Risk Status</h3>
        <button onClick={fetchRiskSummary} disabled={loading} className="btn-primary">
          🔄 Refresh Risk Summary
        </button>

        {riskSummary && (
          <div style={{marginTop: '16px'}}>
            {/* Risk Level */}
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
              <p style={{margin: '4px 0', fontSize: '12px'}}>
                Current drawdown: {riskSummary.current_drawdown_pct.toFixed(2)}% (limit: {riskSummary.limits.max_drawdown_pct}%)
              </p>
            </div>

            {/* Risk Metrics */}
            <div className="grid-3" style={{marginBottom: '16px'}}>
              <div className="stat">
                <label>Current Capital</label>
                <value>${riskSummary.current_capital.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Peak Capital</label>
                <value>${riskSummary.peak_capital.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Drawdown</label>
                <value style={{color: '#ff9900'}}>{riskSummary.current_drawdown_pct.toFixed(2)}%</value>
              </div>
              <div className="stat">
                <label>Daily P&L</label>
                <value style={{color: riskSummary.daily_pnl >= 0 ? 'green' : 'red'}}>
                  ${riskSummary.daily_pnl.toFixed(2)}
                </value>
              </div>
              <div className="stat">
                <label>Daily Loss %</label>
                <value>{riskSummary.daily_loss_pct.toFixed(2)}%</value>
              </div>
              <div className="stat">
                <label>Remaining Daily Loss</label>
                <value>{riskSummary.remaining_daily_loss_pct.toFixed(2)}%</value>
              </div>
              <div className="stat">
                <label>Open Positions</label>
                <value>{riskSummary.open_positions}/{riskSummary.limits.max_positions}</value>
              </div>
              <div className="stat">
                <label>Trades Today</label>
                <value>{riskSummary.trades_today}</value>
              </div>
              <div className="stat">
                <label>Remaining Positions</label>
                <value>{riskSummary.remaining_positions}</value>
              </div>
            </div>

            {/* Limits Table */}
            <table style={{width: '100%', fontSize: '13px'}}>
              <thead>
                <tr style={{backgroundColor: '#f0f0f0'}}>
                  <th style={{padding: '8px', textAlign: 'left'}}>Limit</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Current</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Maximum</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Remaining</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{borderBottom: '1px solid #eee'}}>
                  <td style={{padding: '8px'}}>Portfolio Drawdown</td>
                  <td style={{padding: '8px', textAlign: 'right', color: '#ff9900'}}>
                    {riskSummary.current_drawdown_pct.toFixed(2)}%
                  </td>
                  <td style={{padding: '8px', textAlign: 'right'}}>
                    {riskSummary.limits.max_drawdown_pct}%
                  </td>
                  <td style={{padding: '8px', textAlign: 'right', color: 'green'}}>
                    {riskSummary.remaining_drawdown_pct.toFixed(2)}%
                  </td>
                </tr>
                <tr style={{borderBottom: '1px solid #eee'}}>
                  <td style={{padding: '8px'}}>Daily Loss</td>
                  <td style={{padding: '8px', textAlign: 'right', color: riskSummary.daily_pnl < 0 ? 'red' : 'green'}}>
                    {riskSummary.daily_loss_pct.toFixed(2)}%
                  </td>
                  <td style={{padding: '8px', textAlign: 'right'}}>
                    {riskSummary.limits.max_daily_loss_pct}%
                  </td>
                  <td style={{padding: '8px', textAlign: 'right', color: 'green'}}>
                    {riskSummary.remaining_daily_loss_pct.toFixed(2)}%
                  </td>
                </tr>
                <tr>
                  <td style={{padding: '8px'}}>Open Positions</td>
                  <td style={{padding: '8px', textAlign: 'right'}}>
                    {riskSummary.open_positions}
                  </td>
                  <td style={{padding: '8px', textAlign: 'right'}}>
                    {riskSummary.limits.max_positions}
                  </td>
                  <td style={{padding: '8px', textAlign: 'right', color: 'green'}}>
                    {riskSummary.remaining_positions}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="card" style={{marginTop: '16px', backgroundColor: '#e6f2ff', borderLeft: '4px solid #0066cc'}}>
        <h4>ℹ️ Risk Management Tips</h4>
        <ul style={{listStyle: 'none', padding: 0, fontSize: '13px'}}>
          <li>✅ Use Position Sizing Calculator to determine trade size</li>
          <li>✅ Kelly Criterion helps optimize position sizing based on statistics</li>
          <li>✅ Monitor Risk Summary to stay within limits</li>
          <li>✅ Start with Quarter Kelly (most conservative)</li>
          <li>✅ Only increase position size after consistent profits</li>
          <li>✅ Max 20% of capital per position (built-in limit)</li>
        </ul>
      </div>
    </div>
  )
}
