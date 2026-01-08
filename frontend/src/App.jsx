import { useEffect, useState } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [serverStatus, setServerStatus] = useState("Checking...")

  // --- STATE BOT HUNTER (Tokocrypto) ---
  const [botStatus, setBotStatus] = useState({ is_running: false, current_activity: "Idle" })
  const [activeSymbol, setActiveSymbol] = useState("BTC/USDT")
  const [marketData, setMarketData] = useState(null)

  // --- STATE JUPITER SNIPER (Solana) ---
  const [balances, setBalances] = useState({ SOL: 0 })
  const [swapInput, setSwapInput] = useState(0.01)
  const [targetToken, setTargetToken] = useState("USDC")
  const [swapQuote, setSwapQuote] = useState(null)
  const [isQuoting, setIsQuoting] = useState(false)
  const [isSwapping, setIsSwapping] = useState(false)
  const [txResult, setTxResult] = useState(null)

  // --- STATE AUTO & GOD MODE ---
  const [solanaAutoStatus, setSolanaAutoStatus] = useState({ is_running: false, target: "", position: null })

  const [systemLogs, setSystemLogs] = useState([])

  // --- DATA PENDUKUNG ---
  const [history, setHistory] = useState([])
  const availableTokens = ["USDC", "USDT", "BONK", "WIF", "RAY", "JUP", "PYTH"]

  // --- FUNGSI UTAMA (FETCH DATA LOOP) ---
  const fetchData = async () => {
    try {
      // 1. Cek Status Bot Hunter
      const resBot = await axios.get('http://127.0.0.1:8000/api/bot/status')
      setBotStatus(resBot.data)

      let targetSymbol = "BTC/USDT"
      if (resBot.data.current_activity) {
        if (resBot.data.current_activity.includes("Managing") || resBot.data.current_activity.includes("Analyzing")) {
          const parts = resBot.data.current_activity.split(" ")
          if (parts.length > 1) targetSymbol = parts[1]
        }
      }
      setActiveSymbol(targetSymbol.replace(/\./g, "").trim())

      // 2. Harga Market Tokocrypto
      try {
        const cleanSymbol = targetSymbol.replace("/", "").replace(/\./g, "").trim()
        const resPrice = await axios.get(`http://127.0.0.1:8000/api/toko/price/${cleanSymbol}`)
        setMarketData(resPrice.data)
      } catch (e) { }

      // 3. Portfolio Solana
      try {
        const resBal = await axios.get('http://127.0.0.1:8000/api/solana/balance')
        setBalances(resBal.data)
      } catch (e) { console.error("Balance Error", e) }

      // 4. Status Auto Solana
      try {
        const resAuto = await axios.get('http://127.0.0.1:8000/api/solana/auto/status')
        setSolanaAutoStatus(resAuto.data)
      } catch (e) { }

      // 5. Global History
      try {
        const resToko = await axios.get('http://127.0.0.1:8000/api/trade/history')
        const tokoData = resToko.data.map(item => ({ ...item, source: 'Hunter' }))

        const resSol = await axios.get('http://127.0.0.1:8000/api/solana/history')
        const solData = resSol.data.map(item => ({ ...item, source: 'Jupiter' }))

        const combined = [...solData, ...tokoData].sort((a, b) => {
          const dateA = new Date(a.created_at || a.timestamp)
          const dateB = new Date(b.created_at || b.timestamp)
          return dateB - dateA
        })
        setHistory(combined)
      } catch (e) { console.error("History Error", e) }

      // 6. Ambil System Logs
      try {
        const resLogs = await axios.get('http://127.0.0.1:8000/api/system/logs')
        setSystemLogs(resLogs.data)
      } catch (e) { }

      setServerStatus("Connected")

    } catch (error) {
      setServerStatus("Error / Offline")
    }
  }

  // --- HANDLERS ---
  const handleToggleBot = async () => {
    try { await axios.post('http://127.0.0.1:8000/api/bot/toggle'); fetchData(); } catch { alert("Gagal koneksi bot") }
  }

  const handleGetQuote = async () => {
    setIsQuoting(true); setSwapQuote(null); setTxResult(null);
    try {
      const res = await axios.get(`http://127.0.0.1:8000/api/solana/quote?amount=${swapInput}&to_token=${targetToken}`)
      setSwapQuote(res.data)
    } catch { alert("Gagal mengambil quote.") } finally { setIsQuoting(false) }
  }

  const handleExecuteSwap = async () => {
    if (!swapQuote) return;
    setIsSwapping(true)
    try {
      const payload = { amount: parseFloat(swapInput), input_token: "SOL", output_token: targetToken }
      const res = await axios.post('http://127.0.0.1:8000/api/solana/swap', payload)
      setTxResult(res.data)
      setSwapQuote(null)
      setTimeout(fetchData, 4000)
    } catch (e) { alert("Gagal Swap: " + e.message) } finally { setIsSwapping(false) }
  }

  const handleToggleAuto = async (mode) => {
    try {
      await axios.post('http://127.0.0.1:8000/api/solana/auto/toggle', { mode: mode, token: targetToken })
      fetchData()
    } catch (e) { alert("Gagal toggle auto") }
  }

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 2000); return () => clearInterval(i) }, [])

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial', maxWidth: '900px', margin: '0 auto', color: '#ecf0f1', backgroundColor: '#2c3e50', minHeight: '100vh' }}>

      <div style={{ textAlign: 'center', marginBottom: '30px' }}>
        <h1>🦅 Crypto Hybrid Bot</h1>
        <p style={{ fontSize: '14px', color: '#bdc3c7' }}>System: <span style={{ color: serverStatus === 'Connected' ? '#2ecc71' : '#e74c3c', fontWeight: 'bold' }}>{serverStatus}</span></p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>

        {/* KIRI: HUNTER */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
            <h3 style={{ margin: 0, color: '#34495e' }}>🎮 Hunter</h3>
            <span style={{ fontSize: '10px', fontWeight: 'bold', background: botStatus.is_running ? '#d4edda' : '#f8d7da', color: botStatus.is_running ? '#155724' : '#721c24', padding: '2px 6px', borderRadius: '4px' }}>
              {botStatus.is_running ? "ON" : "OFF"}
            </span>
          </div>
          <div style={{ backgroundColor: '#ecf0f1', padding: '10px', borderRadius: '8px', textAlign: 'center', marginBottom: '15px' }}>
            <small style={{ color: '#7f8c8d' }}>ACTIVITY</small><br /><strong style={{ color: '#2980b9' }}>{botStatus.current_activity}</strong>
          </div>
          <button onClick={handleToggleBot} style={{ width: '100%', backgroundColor: botStatus.is_running ? '#e74c3c' : '#27ae60', color: 'white', padding: '10px', border: 'none', cursor: 'pointer', borderRadius: '8px', fontWeight: 'bold' }}>
            {botStatus.is_running ? "STOP SCANNING" : "START SCANNING"}
          </button>
        </div>

        {/* KANAN: SNIPER */}
        <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #8e44ad 0%, #c0392b 100%)', color: 'white', border: 'none' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h3 style={{ margin: 0 }}>🪐 Jupiter Sniper</h3>
            <span style={{ fontSize: '10px', background: 'rgba(0,0,0,0.3)', padding: '2px 8px', borderRadius: '10px' }}>Unified API</span>
          </div>

          <div style={{ marginBottom: '15px' }}>
            <div style={{ fontSize: '12px', opacity: 0.9, marginBottom: '5px' }}>My Portfolio</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {Object.entries(balances).map(([symbol, amount]) => (
                <div key={symbol} style={{ background: 'rgba(255,255,255,0.2)', padding: '5px 10px', borderRadius: '15px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <span style={{ fontWeight: 'bold' }}>{symbol}</span>
                  <span>{parseFloat(amount).toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                </div>
              ))}
              {Object.keys(balances).length === 0 && <span style={{ fontSize: '12px' }}>Loading...</span>}
            </div>
          </div>

          <div style={{ background: 'rgba(255,255,255,0.15)', padding: '15px', borderRadius: '8px' }}>
            {!txResult ? (
              <>
                <div style={{ fontSize: '11px', marginBottom: '5px', fontWeight: 'bold', textTransform: 'uppercase' }}>{swapQuote ? "Konfirmasi" : "Sniper Console"}</div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '5px 10px', borderRadius: '4px', flex: 1 }}>
                    <input type="number" value={swapInput} onChange={(e) => setSwapInput(e.target.value)} disabled={!!swapQuote} style={{ width: '50px', background: 'transparent', border: 'none', color: 'white', fontWeight: 'bold' }} />
                    <span style={{ fontSize: '12px' }}>SOL</span>
                  </div>
                  <span style={{ fontWeight: 'bold' }}>➜</span>
                  <select value={targetToken} onChange={(e) => setTargetToken(e.target.value)} disabled={!!swapQuote} style={{ padding: '5px', borderRadius: '4px', border: 'none', fontWeight: 'bold', color: '#2c3e50', background: '#ecf0f1', cursor: 'pointer' }}>
                    {availableTokens.map(token => <option key={token} value={token}>{token}</option>)}
                  </select>
                </div>

                {!swapQuote ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', gap: '5px' }}>
                      <button onClick={handleGetQuote} disabled={isQuoting} style={{ ...btnActionStyle, flex: 1 }}>
                        {isQuoting ? "..." : `CEK ${targetToken}`}
                      </button>
                      <button
                        onClick={() => handleToggleAuto('MANUAL_TARGET')}
                        style={{ ...btnActionStyle, background: '#8e44ad', flex: 1 }}>
                        🤖 AUTO {targetToken}
                      </button>
                    </div>

                    <button
                      onClick={() => handleToggleAuto('AUTO_DISCOVERY')}
                      style={{
                        ...btnActionStyle,
                        background: solanaAutoStatus.is_running && !availableTokens.includes(solanaAutoStatus.target) ? '#c0392b' : '#34495e',
                        border: '1px dashed #f1c40f', fontSize: '11px', padding: '10px'
                      }}>
                      {solanaAutoStatus.is_running && !availableTokens.includes(solanaAutoStatus.target)
                        ? `⛔ STOP HUNTING (${solanaAutoStatus.target})`
                        : "🕵️ AKTIFKAN GOD MODE (AUTO CARI COIN)"}
                    </button>

                    {solanaAutoStatus.position && (
                      <div style={{ fontSize: '10px', background: '#2ecc71', padding: '5px', borderRadius: '4px', textAlign: 'center', color: 'black' }}>
                        Holding: {parseFloat(solanaAutoStatus.position.token_amount).toFixed(2)} {solanaAutoStatus.position.token} ({solanaAutoStatus.position.entry_price_sol} SOL)
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '5px' }}>
                    <button onClick={() => setSwapQuote(null)} style={{ ...btnActionStyle, background: '#7f8c8d', flex: 1 }}>BATAL</button>
                    <button onClick={handleExecuteSwap} disabled={isSwapping} style={{ ...btnActionStyle, background: '#27ae60', flex: 1 }}>{isSwapping ? "PROSES..." : "BELI MANUAL"}</button>
                  </div>
                )}

                {swapQuote && !swapQuote.error && <div style={{ marginTop: '10px', padding: '10px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px', fontSize: '13px' }}>Estimasi: <span style={{ fontWeight: 'bold', color: '#55efc4' }}>{swapQuote.output_estimate} {targetToken}</span></div>}
                {swapQuote && swapQuote.error && <div style={{ marginTop: '10px', color: '#ff7675', fontSize: '11px' }}>Error: {swapQuote.error}</div>}
              </>
            ) : (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '40px', marginBottom: '10px' }}>{txResult.status === 'success' ? '✅' : '❌'}</div>
                <h4 style={{ margin: '0 0 5px 0' }}>{txResult.status === 'success' ? 'Sukses!' : 'Gagal'}</h4>
                {txResult.txid && <div style={{ fontSize: '11px', background: 'rgba(0,0,0,0.2)', padding: '5px', borderRadius: '4px', margin: '10px 0' }}>TX: {txResult.txid.slice(0, 10)}...</div>}
                <button onClick={() => { setTxResult(null); setSwapInput(0.01); }} style={{ ...btnActionStyle, width: '100%', marginTop: '10px' }}>KEMBALI</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #bdc3c7', paddingBottom: '10px', marginBottom: '15px' }}>
          <h3 style={{ margin: 0, color: '#34495e' }}>Market Monitor</h3>
          <span style={{ background: '#f1c40f', color: '#2c3e50', padding: '2px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold' }}>TARGET: {activeSymbol}</span>
        </div>
        {marketData ? (
          <div style={{ textAlign: 'center' }}>
            <h1 style={{ margin: '0', fontSize: '42px', color: '#2c3e50' }}>${parseFloat(marketData.current_price).toLocaleString()}</h1>
          </div>
        ) : <p style={{ textAlign: 'center', color: '#7f8c8d' }}>Scanner Idle...</p>}
      </div>

      {/* SYSTEM TERMINAL (LIVE LOGS) */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ margin: 0, color: '#34495e' }}>💻 Live Terminal</h3>
          <span style={{ fontSize: '10px', color: '#7f8c8d' }}>Real-time Scanner & Bot Activity</span>
        </div>
        <div style={{
          background: '#000',
          color: '#00ff00',
          fontFamily: 'monospace',
          fontSize: '12px',
          padding: '15px',
          borderRadius: '8px',
          height: '200px',
          overflowY: 'auto',
          border: '1px solid #333'
        }}>
          {systemLogs.length === 0 ? (
            <div style={{ color: '#555' }}>Checking system logs...</div>
          ) : (
            systemLogs.slice().reverse().map((log, index) => (
              <div key={index} style={{ marginBottom: '4px', borderBottom: '1px solid #111' }}>
                {log}
              </div>
            ))
          )}
        </div>
      </div>

      <div style={cardStyle}>
        <h3 style={{ color: '#34495e' }}>📜 Global History</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '10px', fontSize: '13px', color: '#2c3e50' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid #ecf0f1', color: '#7f8c8d' }}>
              <th style={{ padding: '8px' }}>Time</th><th>Source</th><th>Pair</th><th>Side</th><th>Amount</th><th>Info</th>
            </tr>
          </thead>
          <tbody>
            {history.map((trade, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid #ecf0f1' }}>
                <td style={{ padding: '8px', color: '#7f8c8d' }}>{new Date(trade.created_at || trade.timestamp).toLocaleTimeString()}</td>
                <td><span style={{ padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontWeight: 'bold', color: 'white', background: trade.source === 'Jupiter' ? 'linear-gradient(135deg, #8e44ad, #c0392b)' : '#2980b9' }}>{trade.source}</span></td>
                <td style={{ fontWeight: 'bold' }}>{trade.symbol}</td>
                <td style={{ fontWeight: 'bold', color: trade.side === 'BUY' ? '#27ae60' : '#c0392b' }}>{trade.side}</td>
                <td>{trade.source === 'Jupiter' ? `${trade.amount_out} ${trade.symbol.split('/')[0]}` : `$${trade.buy_price?.toFixed(2)}`}</td>
                <td style={{ fontSize: '11px', color: '#95a5a6' }}>{trade.source === 'Jupiter' ? (trade.txid === 'UNKNOWN' ? '-' : <a href={`https://solscan.io/tx/${trade.txid}`} target="_blank" style={{ color: '#3498db' }}>View TX</a>) : (trade.profit_usdt ? `$${trade.profit_usdt}` : '-')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const cardStyle = { borderRadius: '12px', padding: '20px', marginBottom: '20px', backgroundColor: '#ffffff', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }
const btnActionStyle = { background: '#f39c12', color: 'white', border: 'none', padding: '8px 15px', borderRadius: '4px', cursor: 'pointer', fontSize: '12px', fontWeight: 'bold' }
export default App