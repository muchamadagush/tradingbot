import { useEffect, useState } from 'react'
import axios from 'axios'

const VITE_API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export function PaperTradingTab() {
  const [account, setAccount] = useState(null)
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [amount, setAmount] = useState(100)
  const [currentPrice, setCurrentPrice] = useState(0)
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetchAccountData()
    const interval = setInterval(fetchAccountData, 5000)
    return () => clearInterval(interval)
  }, [])

  const fetchAccountData = async () => {
    try {
      const accountRes = await axios.get(`${VITE_API_URL}/api/paper/account`)
      setAccount(accountRes.data)
      setPositions(accountRes.data.positions_detail || [])

      const tradesRes = await axios.get('${VITE_API_URL}/api/paper/trades')
      setTrades(tradesRes.data || [])
    } catch (err) {
      console.error('Error fetching account:', err)
    }
  }

  const fetchPrice = async (sym) => {
    try {
      const cleanSym = sym.replace('/', '')
      const res = await axios.get(`${VITE_API_URL}/api/toko/price/${cleanSym}`)
      setCurrentPrice(res.data.current_price)
      setError('')
    } catch (err) {
      setError('Failed to fetch price')
    }
  }

  const handleBuy = async () => {
    try {
      setLoading(true)
      setMessage('')
      setError('')

      await fetchPrice(symbol)

      const res = await axios.post(`${VITE_API_URL}/api/paper/buy`, {
        symbol,
        amount_usdt: amount
      })

      if (res.data.status === 'success') {
        setMessage(`✅ Bought! Asset: ${res.data.position.amount.toFixed(8)}`)
        await fetchAccountData()
        setAmount(100)
      } else if (res.data.status === 'rejected') {
        setError(`Risk check failed: ${res.data.reasons.join(', ')}`)
      } else {
        setError(res.data.reason || 'Buy failed')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSell = async (sym) => {
    try {
      setLoading(true)
      setMessage('')
      setError('')

      const res = await axios.post(`${VITE_API_URL}/api/paper/sell`, {
        symbol: sym,
        percentage: 100
      })

      if (res.data.status === 'success') {
        const profit = res.data.trade.profit
        const color = profit >= 0 ? 'green' : 'red'
        setMessage(`✅ Sold ${sym}! Profit: $${profit.toFixed(2)} (${res.data.trade.profit_pct.toFixed(2)}%)`)
        await fetchAccountData()
      } else {
        setError(res.data.reason || 'Sell failed')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (window.confirm('Reset paper account to $1000?')) {
      try {
        await axios.post(`${VITE_API_URL}/api/paper/reset`, {
          balance: 1000
        })
        setMessage('✅ Account reset to $1000')
        await fetchAccountData()
      } catch (err) {
        setError('Reset failed')
      }
    }
  }

  return (
    <div className="tab-content">
      <h2>📈 Paper Trading</h2>

      {/* Account Summary */}
      {account && (
        <div className="card">
          <h3>💰 Account Status</h3>
          <div className="grid-4">
            <div className="stat">
              <label>Balance</label>
              <value>${account.balance.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Total Equity</label>
              <value>${account.total_equity.toFixed(2)}</value>
            </div>
            <div className="stat">
              <label>Total P&L</label>
              <value style={{color: account.total_pnl >= 0 ? 'green' : 'red'}}>
                ${account.total_pnl.toFixed(2)}
              </value>
            </div>
            <div className="stat">
              <label>Return %</label>
              <value style={{color: account.pnl_pct >= 0 ? 'green' : 'red'}}>
                {account.pnl_pct.toFixed(2)}%
              </value>
            </div>
            <div className="stat">
              <label>Open Positions</label>
              <value>{account.open_positions}</value>
            </div>
            <div className="stat">
              <label>Total Trades</label>
              <value>{account.total_trades}</value>
            </div>
            <div className="stat">
              <label>Win Rate</label>
              <value>{account.win_rate_pct.toFixed(1)}%</value>
            </div>
            <div className="stat">
              <label>Total Fees</label>
              <value>${account.total_fees_paid.toFixed(2)}</value>
            </div>
          </div>

          <button onClick={handleReset} className="btn-secondary" style={{marginTop: '12px'}}>
            🔄 Reset Account
          </button>
        </div>
      )}

      {/* Messages */}
      {message && (
        <div style={{
          padding: '12px',
          backgroundColor: '#ccffcc',
          border: '1px solid #00aa00',
          borderRadius: '4px',
          color: '#006600',
          marginTop: '12px'
        }}>
          {message}
        </div>
      )}
      {error && (
        <div style={{
          padding: '12px',
          backgroundColor: '#ffcccc',
          border: '1px solid #ff0000',
          borderRadius: '4px',
          color: '#cc0000',
          marginTop: '12px'
        }}>
          ❌ {error}
        </div>
      )}

      {/* Buy Form */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>🛒 Buy Order</h3>
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
            <label>Amount (USDT)</label>
            <input
              type="number"
              min="10"
              step="10"
              value={amount}
              onChange={(e) => setAmount(parseFloat(e.target.value))}
            />
          </div>
        </div>
        <button
          onClick={handleBuy}
          disabled={loading}
          className="btn-primary"
          style={{marginTop: '12px'}}
        >
          {loading ? '⏳ Processing...' : '💚 Buy'}
        </button>
      </div>

      {/* Open Positions */}
      {positions.length > 0 && (
        <div className="card" style={{marginTop: '16px'}}>
          <h3>📊 Open Positions ({positions.length})</h3>
          <div style={{overflowX: 'auto'}}>
            <table style={{width: '100%', fontSize: '13px'}}>
              <thead>
                <tr style={{backgroundColor: '#f0f0f0'}}>
                  <th style={{padding: '8px', textAlign: 'left'}}>Symbol</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Amount</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Entry Price</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Current Price</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Value</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>P&L</th>
                  <th style={{padding: '8px', textAlign: 'center'}}>Action</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} style={{borderBottom: '1px solid #eee'}}>
                    <td style={{padding: '8px'}}>{pos.symbol}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>{pos.amount.toFixed(8)}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>${pos.entry_price.toFixed(2)}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>${pos.current_price.toFixed(2)}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>${pos.current_value.toFixed(2)}</td>
                    <td style={{
                      padding: '8px',
                      textAlign: 'right',
                      color: pos.pnl >= 0 ? 'green' : 'red'
                    }}>
                      ${pos.pnl.toFixed(2)} ({pos.pnl_pct.toFixed(2)}%)
                    </td>
                    <td style={{padding: '8px', textAlign: 'center'}}>
                      <button
                        onClick={() => handleSell(pos.symbol)}
                        disabled={loading}
                        className="btn-secondary"
                        style={{fontSize: '12px', padding: '4px 8px'}}
                      >
                        Sell
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trade History */}
      {trades.length > 0 && (
        <div className="card" style={{marginTop: '16px'}}>
          <h3>📋 Trade History ({trades.length})</h3>
          <div style={{
            maxHeight: '300px',
            overflowY: 'auto'
          }}>
            <table style={{width: '100%', fontSize: '12px'}}>
              <thead>
                <tr style={{backgroundColor: '#f0f0f0', position: 'sticky', top: 0}}>
                  <th style={{padding: '8px', textAlign: 'left'}}>Symbol</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Entry</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Exit</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>Profit</th>
                  <th style={{padding: '8px', textAlign: 'right'}}>%</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade, idx) => (
                  <tr key={idx} style={{borderBottom: '1px solid #eee'}}>
                    <td style={{padding: '8px'}}>{trade.symbol}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>${trade.entry_price.toFixed(2)}</td>
                    <td style={{padding: '8px', textAlign: 'right'}}>${trade.exit_price.toFixed(2)}</td>
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

      {!account || positions.length === 0 && (
        <div className="card" style={{marginTop: '16px', textAlign: 'center', color: '#999'}}>
          <p>No open positions yet. Start trading with the buy form above!</p>
        </div>
      )}
    </div>
  )
}
