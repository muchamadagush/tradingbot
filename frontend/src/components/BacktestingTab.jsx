import { useEffect, useState } from 'react'
import axios from 'axios'

export function BacktestingTab() {
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [daysBack, setDaysBack] = useState(30)
  const [initialCapital, setInitialCapital] = useState(1000)
  const [takeProfit, setTakeProfit] = useState(1.5)
  const [stopLoss, setStopLoss] = useState(3.0)
  
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])

  useEffect(() => {
    fetchBacktestHistory()
  }, [])

  const fetchBacktestHistory = async () => {
    try {
      const res = await axios.get('http://127.0.0.1:8000/api/backtest/history?limit=20')
      setHistory(res.data)
    } catch (err) {
      console.error('Error fetching history:', err)
    }
  }

  const handleRunBacktest = async () => {
    try {
      setRunning(true)
      setError(null)
      setResult(null)

      const res = await axios.post('http://127.0.0.1:8000/api/backtest/run', {
        symbol,
        timeframe,
        days_back: daysBack,
        initial_capital: initialCapital,
        take_profit_pct: takeProfit,
        stop_loss_pct: stopLoss
      })

      if (res.data.error) {
        setError(res.data.error)
      } else {
        setResult(res.data)
        fetchBacktestHistory()
      }
    } catch (err) {
      setError(err.message || 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="tab-content">
      <h2>🔬 Backtesting Engine</h2>

      {/* Input Form */}
      <div className="card">
        <h3>Configure Backtest</h3>
        
        <div className="form-grid">
          <div className="form-group">
            <label>Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="e.g., BTC/USDT"
            />
          </div>

          <div className="form-group">
            <label>Timeframe</label>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              <option>1m</option>
              <option>5m</option>
              <option>15m</option>
              <option>1h</option>
              <option>4h</option>
              <option>1d</option>
            </select>
          </div>

          <div className="form-group">
            <label>Days Back</label>
            <input
              type="number"
              min="1"
              max="365"
              value={daysBack}
              onChange={(e) => setDaysBack(parseInt(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label>Initial Capital ($)</label>
            <input
              type="number"
              min="100"
              step="100"
              value={initialCapital}
              onChange={(e) => setInitialCapital(parseFloat(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label>Take Profit (%)</label>
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={takeProfit}
              onChange={(e) => setTakeProfit(parseFloat(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label>Stop Loss (%)</label>
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={stopLoss}
              onChange={(e) => setStopLoss(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button
          onClick={handleRunBacktest}
          disabled={running}
          className="btn-primary"
          style={{marginTop: '16px'}}
        >
          {running ? '⏳ Running Backtest...' : '▶️ Run Backtest'}
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div style={{
          padding: '12px',
          backgroundColor: '#ffcccc',
          border: '1px solid #ff0000',
          borderRadius: '4px',
          color: '#cc0000',
          marginTop: '12px'
        }}>
          ❌ Error: {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="card" style={{marginTop: '16px', borderLeft: '4px solid #44aa44'}}>
          <h3>✅ Backtest Results</h3>
          
          <div className="grid-3">
            <div className="stat">
              <label>Initial Capital</label>
              <value>${result.initial_capital.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Final Capital</label>
              <value style={{color: result.roi_pct >= 0 ? 'green' : 'red'}}>
                ${result.final_capital.toFixed(2)}
              </value>
            </div>
            <div className="stat">
              <label>ROI</label>
              <value style={{color: result.roi_pct >= 0 ? 'green' : 'red', fontSize: '18px'}}>
                {result.roi_pct.toFixed(2)}%
              </value>
            </div>
            <div className="stat">
              <label>Total Trades</label>
              <value>{result.total_trades}</value>
            </div>
            <div className="stat">
              <label>Winning Trades</label>
              <value style={{color: 'green'}}>{result.winning_trades}</value>
            </div>
            <div className="stat">
              <label>Win Rate</label>
              <value>{result.win_rate_pct.toFixed(2)}%</value>
            </div>
            <div className="stat">
              <label>Max Drawdown</label>
              <value style={{color: '#ff9900'}}>{result.max_drawdown_pct.toFixed(2)}%</value>
            </div>
            <div className="stat">
              <label>Profit Factor</label>
              <value>{result.profit_factor.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Total Fees</label>
              <value>${result.total_fees_paid.toFixed(2)}</value>
            </div>
          </div>

          {/* Trade List */}
          {result.trades && result.trades.length > 0 && (
            <div style={{marginTop: '20px'}}>
              <h4>Trades ({result.trades.length})</h4>
              <div style={{
                maxHeight: '300px',
                overflowY: 'auto',
                border: '1px solid #ddd',
                borderRadius: '4px'
              }}>
                <table style={{width: '100%', fontSize: '12px'}}>
                  <thead>
                    <tr style={{backgroundColor: '#f0f0f0', position: 'sticky', top: 0}}>
                      <th style={{padding: '8px', textAlign: 'left'}}>Entry</th>
                      <th style={{padding: '8px', textAlign: 'left'}}>Exit</th>
                      <th style={{padding: '8px', textAlign: 'right'}}>Profit</th>
                      <th style={{padding: '8px', textAlign: 'right'}}>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade, idx) => (
                      <tr key={idx} style={{borderBottom: '1px solid #eee'}}>
                        <td style={{padding: '8px'}}>${trade.entry_price.toFixed(2)}</td>
                        <td style={{padding: '8px'}}>${trade.exit_price.toFixed(2)}</td>
                        <td style={{
                          padding: '8px',
                          textAlign: 'right',
                          color: trade.profit >= 0 ? 'green' : 'red'
                        }}>
                          ${trade.profit.toFixed(2)}
                        </td>
                        <td style={{
                          padding: '8px',
                          textAlign: 'right',
                          color: trade.profit_pct >= 0 ? 'green' : 'red'
                        }}>
                          {trade.profit_pct.toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Assessment */}
          <div style={{marginTop: '20px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            <h4>📊 Assessment</h4>
            {result.roi_pct > 5 && result.win_rate_pct > 50 ? (
              <p style={{color: 'green'}}>
                ✅ <strong>Good strategy!</strong> Positive ROI and good win rate. Consider paper trading.
              </p>
            ) : result.roi_pct > 0 ? (
              <p style={{color: '#ff9900'}}>
                ⚠️ <strong>Marginal results.</strong> Needs more testing or strategy refinement.
              </p>
            ) : (
              <p style={{color: 'red'}}>
                ❌ <strong>Strategy not profitable.</strong> Review your strategy before paper trading.
              </p>
            )}
          </div>
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="card" style={{marginTop: '16px'}}>
          <h3>📋 Recent Backtests</h3>
          <div style={{
            maxHeight: '400px',
            overflowY: 'auto'
          }}>
            <table style={{width: '100%', fontSize: '13px'}}>
              <thead>
                <tr style={{backgroundColor: '#f0f0f0'}}>
                  <th style={{padding: '8px', textAlign: 'left'}}>Symbol</th>
                  <th style={{padding: '8px', textAlign: 'left'}}>Period</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>ROI</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Trades</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Win Rate</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Drawdown</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item, idx) => (
                  <tr key={idx} style={{borderBottom: '1px solid #eee'}}>
                    <td style={{padding: '8px'}}>{item.symbol}</td>
                    <td style={{padding: '8px'}}>{item.period_days}d {item.timeframe}</td>
                    <td style={{
                      padding: '8px',
                      textAlign: 'right',
                      color: item.roi_pct >= 0 ? 'green' : 'red'
                    }}>
                      {item.roi_pct.toFixed(2)}%
                    </td>
                    <td style={{padding: '8px', textAlign: 'right'}}>{item.total_trades}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>{item.win_rate_pct.toFixed(1)}%</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>{item.max_drawdown_pct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
