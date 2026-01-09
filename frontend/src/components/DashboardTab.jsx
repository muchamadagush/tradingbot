import { useEffect, useState } from 'react'
import axios from 'axios'

export function DashboardTab() {
  const [botMode, setBotMode] = useState(null)
  const [riskSummary, setRiskSummary] = useState(null)
  const [paperAccount, setPaperAccount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // STATE BARU
  const [tokoStatus, setTokoStatus] = useState({ is_running: false, current_activity: 'Idle' })
  // Update state default untuk Solana agar mendukung array positions
  const [solanaStatus, setSolanaStatus] = useState({ 
    is_running: false, 
    mode: 'MANUAL_TARGET', 
    target: '', 
    positions: [], 
    count: 0 
  })
  const [solanaMode, setSolanaMode] = useState('AUTO_DISCOVERY') 

  const fetchDashboard = async () => {
    try {
      const modeRes = await axios.get('http://127.0.0.1:8000/api/bot/mode')
      setBotMode(modeRes.data)

      const tokoRes = await axios.get('http://127.0.0.1:8000/api/bot/status')
      setTokoStatus(tokoRes.data)

      const solanaRes = await axios.get('http://127.0.0.1:8000/api/solana/auto/status')
      setSolanaStatus(solanaRes.data)

      const riskRes = await axios.get('http://127.0.0.1:8000/api/risk/summary')
      setRiskSummary(riskRes.data)

      if (modeRes.data.mode === 'PAPER') {
        const accountRes = await axios.get('http://127.0.0.1:8000/api/paper/account')
        setPaperAccount(accountRes.data)
      }
      setError(null)
    } catch (err) {
      console.error('Error fetching dashboard:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDashboard()
    const interval = setInterval(fetchDashboard, 2000)
    return () => clearInterval(interval)
  }, [])

  const toggleTokoBot = async () => {
    try {
      await axios.post('http://127.0.0.1:8000/api/bot/toggle')
      fetchDashboard()
    } catch (err) {
      alert("Gagal toggle Toko Bot: " + err.message)
    }
  }

  const toggleSolanaBot = async () => {
    try {
      await axios.post('http://127.0.0.1:8000/api/solana/auto/toggle', {
        mode: solanaMode,
        token: "USDC" 
      })
      fetchDashboard()
    } catch (err) {
      alert("Gagal toggle Solana Bot: " + err.message)
    }
  }

  if (loading) return <div className="tab-content"><p>Loading Dashboard...</p></div>

  const modeColors = { 'LIVE': '#ff4444', 'PAPER': '#44aa44', 'BACKTEST': '#4444ff' }

  return (
    <div className="tab-content">
      <h2>📊 Dashboard & Control Panel</h2>
      {error && <p style={{color: 'red'}}>⚠️ Connection Error: {error}</p>}

      <div className="grid-2" style={{marginBottom: '20px'}}>
        
        {/* KONTROL TOKOCRYPTO */}
        <div className="card" style={{borderLeft: tokoStatus.is_running ? '5px solid #44aa44' : '5px solid #888'}}>
          <h3>🤖 Tokocrypto Hunter</h3>
          <p>Status: <strong style={{color: tokoStatus.is_running ? '#44aa44' : '#888'}}>
            {tokoStatus.is_running ? 'RUNNING 🚀' : 'STOPPED 🛑'}
          </strong></p>
          <p><small>Activity: {tokoStatus.current_activity}</small></p>
          <button 
            onClick={toggleTokoBot}
            className={tokoStatus.is_running ? 'btn-danger' : 'btn-primary'}
            style={{width: '100%', marginTop: '10px'}}
          >
            {tokoStatus.is_running ? '🛑 STOP HUNTER' : '🚀 START HUNTER'}
          </button>
        </div>

        {/* KONTROL SOLANA (UPDATED) */}
        <div className="card" style={{borderLeft: solanaStatus.is_running ? '5px solid #aa44ff' : '5px solid #888'}}>
          <h3>☀️ Solana Sniper (Multi-Slot)</h3>
          <p>Status: <strong style={{color: solanaStatus.is_running ? '#aa44ff' : '#888'}}>
            {solanaStatus.is_running ? 'RUNNING ⚡' : 'STOPPED 💤'}
          </strong></p>
          
          {/* TAMPILKAN STATUS HOLDING */}
          <div style={{background: '#f0f0f0', padding: '10px', borderRadius: '5px', marginBottom: '10px'}}>
            <strong>🗳️ Holding: {solanaStatus.count || 0} / 3 Coins</strong>
            {solanaStatus.positions && solanaStatus.positions.length > 0 && (
              <ul style={{fontSize: '12px', paddingLeft: '20px', marginTop: '5px'}}>
                {solanaStatus.positions.map((pos, idx) => (
                  <li key={idx}>
                    <b>{pos.token}</b> (Qty: {pos.token_amount.toFixed(2)})
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div style={{marginBottom: '10px'}}>
             <label style={{marginRight: '10px'}}>Mode:</label>
             <select 
               value={solanaMode} 
               onChange={(e) => setSolanaMode(e.target.value)}
               disabled={solanaStatus.is_running}
               style={{padding: '5px'}}
             >
               <option value="AUTO_DISCOVERY">Auto Discovery (Scanner)</option>
               <option value="MANUAL_TARGET">Manual Target</option>
             </select>
          </div>

          <button 
            onClick={toggleSolanaBot}
            className={solanaStatus.is_running ? 'btn-danger' : 'btn-primary'}
            style={{width: '100%', backgroundColor: solanaStatus.is_running ? '#ff4444' : '#aa44ff'}}
          >
            {solanaStatus.is_running ? '🛑 STOP SNIPER' : '⚡ START SNIPER'}
          </button>
        </div>
      </div>

      {/* Mode Badge & Paper Account (Sama seperti sebelumnya) */}
      {botMode && (
        <div className="mode-badge" style={{borderColor: modeColors[botMode.mode]}}>
          <h3 style={{color: modeColors[botMode.mode]}}>🎯 System Mode: {botMode.mode}</h3>
        </div>
      )}
      
      {paperAccount && (
        <div className="card">
          <h3>💰 Paper Trading Account</h3>
          <div className="grid-2">
            <div className="stat"><label>Balance</label><value>${paperAccount.balance.toFixed(2)}</value></div>
            <div className="stat"><label>Total Equity</label><value>${paperAccount.total_equity.toFixed(2)}</value></div>
            <div className="stat"><label>Total P&L</label>
              <value style={{color: paperAccount.total_pnl >= 0 ? 'green' : 'red'}}>
                ${paperAccount.total_pnl.toFixed(2)} ({paperAccount.pnl_pct.toFixed(2)}%)
              </value>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}