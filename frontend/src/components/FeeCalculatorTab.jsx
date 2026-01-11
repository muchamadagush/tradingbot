import { useState } from 'react'
import axios from 'axios'

const VITE_API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export function FeeCalculatorTab() {
  // Buy Cost
  const [buyAmount, setBuyAmount] = useState(100)
  const [buyPrice, setBuyPrice] = useState(50000)
  const [buyOrderType, setBuyOrderType] = useState('market')
  const [buyResult, setBuyResult] = useState(null)

  // Sell Proceeds
  const [sellAmount, setSellAmount] = useState(0.002)
  const [sellPrice, setSellPrice] = useState(50000)
  const [sellOrderType, setSellOrderType] = useState('market')
  const [sellResult, setSellResult] = useState(null)

  // Round Trip
  const [rtAmount, setRtAmount] = useState(100)
  const [rtPrice, setRtPrice] = useState(50000)
  const [rtResult, setRtResult] = useState(null)

  // Profit Target
  const [ptBuyPrice, setPtBuyPrice] = useState(50000)
  const [ptAmount, setPtAmount] = useState(0.002)
  const [ptTarget, setPtTarget] = useState(5)
  const [ptResult, setPtResult] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const calculateBuyCost = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post(`${VITE_API_URL}/api/fee/calculate-buy`, {
        amount_usdt: buyAmount,
        price: buyPrice,
        order_type: buyOrderType
      })
      setBuyResult(res.data)
    } catch (err) {
      setError('Failed to calculate')
    } finally {
      setLoading(false)
    }
  }

  const calculateSellProceeds = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post(`${VITE_API_URL}/api/fee/calculate-sell`, {
        asset_amount: sellAmount,
        price: sellPrice,
        order_type: sellOrderType
      })
      setSellResult(res.data)
    } catch (err) {
      setError('Failed to calculate')
    } finally {
      setLoading(false)
    }
  }

  const calculateRoundTrip = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post(`${VITE_API_URL}/api/fee/round-trip`, {
        amount_usdt: rtAmount,
        price: rtPrice
      })
      setRtResult(res.data)
    } catch (err) {
      setError('Failed to calculate')
    } finally {
      setLoading(false)
    }
  }

  const calculateProfitTarget = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await axios.post(`${VITE_API_URL}/api/fee/profit-target`, {
        buy_price: ptBuyPrice,
        amount: ptAmount,
        target_profit_pct: ptTarget
      })
      setPtResult(res.data)
    } catch (err) {
      setError('Failed to calculate')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tab-content">
      <h2>💰 Fee Calculator</h2>

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

      {/* Buy Cost Calculator */}
      <div className="card">
        <h3>🛒 Buy Cost Calculator</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate total cost including fees and slippage when buying
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Amount to Buy (USDT)</label>
            <input
              type="number"
              min="10"
              step="10"
              value={buyAmount}
              onChange={(e) => setBuyAmount(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Current Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={buyPrice}
              onChange={(e) => setBuyPrice(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Order Type</label>
            <select value={buyOrderType} onChange={(e) => setBuyOrderType(e.target.value)}>
              <option>market</option>
              <option>limit</option>
            </select>
          </div>
        </div>

        <button onClick={calculateBuyCost} disabled={loading} className="btn-primary">
          🧮 Calculate
        </button>

        {buyResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            <h4>Buy Cost Breakdown</h4>
            <div className="grid-3">
              <div className="stat">
                <label>Total Cost</label>
                <value>${buyResult.total_cost_usdt.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Asset Received</label>
                <value>{buyResult.asset_amount.toFixed(8)}</value>
              </div>
              <div className="stat">
                <label>Execution Price</label>
                <value>${buyResult.execution_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Effective Price</label>
                <value>${buyResult.effective_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Fee Paid</label>
                <value style={{color: 'red'}}>${buyResult.fee_usdt.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Fee %</label>
                <value style={{color: 'red'}}>{buyResult.fee_pct.toFixed(3)}%</value>
              </div>
              <div className="stat">
                <label>Slippage Cost</label>
                <value style={{color: 'red'}}>${buyResult.slippage_cost.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Slippage %</label>
                <value style={{color: 'red'}}>{buyResult.slippage_pct.toFixed(3)}%</value>
              </div>
              <div className="stat">
                <label>Total Overhead</label>
                <value style={{color: 'red', fontSize: '16px'}}>${buyResult.total_overhead.toFixed(4)}</value>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Round Trip Calculator */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>🔄 Round Trip Cost (Buy + Sell)</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate break-even point: how much price must rise to profit
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Investment (USDT)</label>
            <input
              type="number"
              min="10"
              step="10"
              value={rtAmount}
              onChange={(e) => setRtAmount(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Entry Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={rtPrice}
              onChange={(e) => setRtPrice(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button onClick={calculateRoundTrip} disabled={loading} className="btn-primary">
          🧮 Calculate
        </button>

        {rtResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            <h4>Round Trip Analysis</h4>
            <div className="stat" style={{marginBottom: '12px', padding: '12px', backgroundColor: '#ffe6e6', borderRadius: '4px'}}>
              <label style={{fontSize: '16px'}}>{rtResult.message}</label>
              <value style={{fontSize: '18px', color: 'red'}}>{rtResult.breakeven_rise_pct.toFixed(2)}% rise needed</value>
            </div>
            <div className="grid-3">
              <div className="stat">
                <label>Initial Investment</label>
                <value>${rtResult.initial_capital.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>After Round Trip</label>
                <value style={{color: 'red'}}>${rtResult.final_capital.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Total Loss</label>
                <value style={{color: 'red'}}>${rtResult.total_loss.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Loss %</label>
                <value style={{color: 'red'}}>{rtResult.loss_pct.toFixed(3)}%</value>
              </div>
              <div className="stat">
                <label>Buy Overhead</label>
                <value style={{color: 'red'}}>${rtResult.buy_overhead.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Sell Overhead</label>
                <value style={{color: 'red'}}>${rtResult.sell_overhead.toFixed(4)}</value>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Profit Target Calculator */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>🎯 Profit Target Calculator</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate target sell price to achieve desired profit (AFTER fees)
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Buy Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={ptBuyPrice}
              onChange={(e) => setPtBuyPrice(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Amount (in asset)</label>
            <input
              type="number"
              min="0.00001"
              step="0.001"
              value={ptAmount}
              onChange={(e) => setPtAmount(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Target Profit (%)</label>
            <input
              type="number"
              min="0.1"
              step="0.5"
              value={ptTarget}
              onChange={(e) => setPtTarget(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button onClick={calculateProfitTarget} disabled={loading} className="btn-primary">
          🧮 Calculate Target
        </button>

        {ptResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            <h4>Target Price Analysis</h4>
            <div className="stat" style={{marginBottom: '12px', padding: '12px', backgroundColor: '#e6ffe6', borderRadius: '4px'}}>
              <label style={{fontSize: '16px'}}>{ptResult.message}</label>
              <value style={{fontSize: '18px', color: 'green'}}>${ptResult.target_sell_price.toFixed(6)}</value>
            </div>
            <div className="grid-3">
              <div className="stat">
                <label>Buy Price</label>
                <value>${ptResult.buy_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Target Sell Price</label>
                <value style={{color: 'green'}}>${ptResult.target_sell_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Price Rise Needed</label>
                <value style={{color: 'green'}}>{ptResult.price_rise_needed.toFixed(2)}%</value>
              </div>
              <div className="stat">
                <label>Cost Basis</label>
                <value>${ptResult.cost_basis.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Target Proceeds</label>
                <value style={{color: 'green'}}>${ptResult.target_proceeds.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Actual Profit</label>
                <value style={{color: 'green'}}>${ptResult.actual_profit.toFixed(2)}</value>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Sell Proceeds Calculator */}
      <div className="card" style={{marginTop: '16px'}}>
        <h3>💵 Sell Proceeds Calculator</h3>
        <p style={{color: '#666', fontSize: '13px'}}>
          Calculate net proceeds when selling (after fees and slippage)
        </p>

        <div className="form-grid">
          <div className="form-group">
            <label>Asset Amount</label>
            <input
              type="number"
              min="0.00001"
              step="0.001"
              value={sellAmount}
              onChange={(e) => setSellAmount(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Current Price ($)</label>
            <input
              type="number"
              min="0.01"
              step="1"
              value={sellPrice}
              onChange={(e) => setSellPrice(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label>Order Type</label>
            <select value={sellOrderType} onChange={(e) => setSellOrderType(e.target.value)}>
              <option>market</option>
              <option>limit</option>
            </select>
          </div>
        </div>

        <button onClick={calculateSellProceeds} disabled={loading} className="btn-primary">
          🧮 Calculate
        </button>

        {sellResult && (
          <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f9f9f9', borderRadius: '4px'}}>
            <h4>Sell Proceeds Breakdown</h4>
            <div className="grid-3">
              <div className="stat">
                <label>Gross Proceeds</label>
                <value>${sellResult.gross_proceeds.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Net Proceeds</label>
                <value style={{color: 'green', fontSize: '16px'}}>${sellResult.net_proceeds.toFixed(2)}</value>
              </div>
              <div className="stat">
                <label>Execution Price</label>
                <value>${sellResult.execution_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Effective Price</label>
                <value>${sellResult.effective_price.toFixed(6)}</value>
              </div>
              <div className="stat">
                <label>Fee Paid</label>
                <value style={{color: 'red'}}>${sellResult.fee_usdt.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Fee %</label>
                <value style={{color: 'red'}}>{sellResult.fee_pct.toFixed(3)}%</value>
              </div>
              <div className="stat">
                <label>Slippage Cost</label>
                <value style={{color: 'red'}}>${sellResult.slippage_cost.toFixed(4)}</value>
              </div>
              <div className="stat">
                <label>Slippage %</label>
                <value style={{color: 'red'}}>{sellResult.slippage_pct.toFixed(3)}%</value>
              </div>
              <div className="stat">
                <label>Total Overhead</label>
                <value style={{color: 'red', fontSize: '16px'}}>${sellResult.total_overhead.toFixed(4)}</value>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Fee Reference */}
      <div className="card" style={{marginTop: '16px', backgroundColor: '#e6f2ff', borderLeft: '4px solid #0066cc'}}>
        <h4>ℹ️ Fee Reference (Tokocrypto)</h4>
        <table style={{width: '100%', fontSize: '13px'}}>
          <tbody>
            <tr style={{borderBottom: '1px solid #ccc'}}>
              <td style={{padding: '8px'}}>Taker Fee (Market Orders)</td>
              <td style={{padding: '8px', textAlign: 'right'}}>0.1%</td>
            </tr>
            <tr style={{borderBottom: '1px solid #ccc'}}>
              <td style={{padding: '8px'}}>Maker Fee (Limit Orders)</td>
              <td style={{padding: '8px', textAlign: 'right'}}>0.1%</td>
            </tr>
            <tr style={{borderBottom: '1px solid #ccc'}}>
              <td style={{padding: '8px'}}>Estimated Slippage</td>
              <td style={{padding: '8px', textAlign: 'right'}}>0.05%</td>
            </tr>
            <tr>
              <td style={{padding: '8px'}}>Total per Round Trip</td>
              <td style={{padding: '8px', textAlign: 'right', fontWeight: 'bold'}}>~0.25%</td>
            </tr>
          </tbody>
        </table>
        <p style={{fontSize: '12px', marginTop: '8px', color: '#666'}}>
          💡 <strong>Pro Tip:</strong> Even small fees add up. A 1% profit becomes 0.75% net after round-trip fees.
          Always account for fees in your profit targets!
        </p>
      </div>
    </div>
  )
}
