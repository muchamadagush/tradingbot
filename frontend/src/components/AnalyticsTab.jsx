import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

const VITE_API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

// Custom CSS untuk Date Input styling
const dateInputStyles = `
  .analytics-date-input {
    width: 150px;
    padding: 10px 12px !important;
    border: 2px solid #d1d5db !important;
    border-radius: 4px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    background-color: #ffffff !important;
    color: #1f2937 !important;
    box-sizing: border-box !important;
    transition: border-color 0.2s !important;
    cursor: pointer !important;
    pointer-events: auto !important;
  }
  
  .analytics-date-input:focus {
    outline: none !important;
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
  }
  
  .analytics-date-input::placeholder {
    color: #9ca3af !important;
  }
  
  /* Ensure date picker icon is visible */
  .analytics-date-input::-webkit-calendar-picker-indicator {
    cursor: pointer !important;
    color: #6b7280 !important;
    filter: invert(0.8);
  }
`;

const AnalyticsTab = () => {
  // =========================================
  // STATE MANAGEMENT
  // =========================================
  const [activeTab, setActiveTab] = useState('solana'); // 'solana' or 'tokocrypto'
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [timeframe, setTimeframe] = useState('daily');
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Inject custom CSS saat component mount
  React.useEffect(() => {
    const style = document.createElement('style');
    style.innerHTML = dateInputStyles;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  // =========================================
  // API CALL FUNCTION
  // =========================================
  const fetchAnalytics = async (tab, start, end, tf) => {
    setLoading(true);
    setError(null);
    try {
      // Build URL dengan query parameters
      const endpoint = tab === 'solana' 
        ? `${VITE_API_URL}/api/analytics/solana`
        : `${VITE_API_URL}/api/analytics/tokocrypto`;

      const params = new URLSearchParams();
      if (start) {
        params.append('start_date', start);
      }
      if (end) {
        params.append('end_date', end);
      }
      params.append('timeframe', tf);

      const response = await axios.get(`${endpoint}?${params.toString()}`);
      setAnalyticsData(response.data);
    } catch (err) {
      setError(`Gagal load analytics: ${err.message}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // =========================================
  // EFFECT: Fetch data saat tab atau filter berubah
  // =========================================
  useEffect(() => {
    fetchAnalytics(activeTab, startDate, endDate, timeframe);
  }, [activeTab, timeframe]);

  // =========================================
  // HANDLER: Apply date filter
  // =========================================
  const handleApplyDateFilter = () => {
    fetchAnalytics(activeTab, startDate, endDate, timeframe);
  };

  // Handler: Reset filters
  const handleResetFilters = () => {
    setStartDate(null);
    setEndDate(null);
    setTimeframe('daily');
  };

  // =========================================
  // HELPER: Format currency
  // =========================================
  const formatCurrency = (value, isSol = false) => {
    if (isSol) {
      return `${value.toFixed(8)} SOL`;
    }
    return `$${value.toFixed(2)}`;
  };

  // =========================================
  // HELPER: Get color based on value
  // =========================================
  const getColorByValue = (value) => {
    return value >= 0 ? '#10b981' : '#ef4444'; // green if positive, red if negative
  };

  // =========================================
  // UI: RENDERING
  // =========================================

  return (
    <div style={styles.container}>
      {/* ===== HEADER ===== */}
      <h1 style={styles.title}>📊 Analytics Dashboard</h1>

      {/* ===== TAB SWITCHER ===== */}
      <div style={styles.tabSwitcher}>
        <button
          style={{
            ...styles.tabButton,
            ...(activeTab === 'solana' ? styles.tabButtonActive : {}),
          }}
          onClick={() => setActiveTab('solana')}
        >
          🌊 Solana Portfolio
        </button>
        <button
          style={{
            ...styles.tabButton,
            ...(activeTab === 'tokocrypto' ? styles.tabButtonActive : {}),
          }}
          onClick={() => setActiveTab('tokocrypto')}
        >
          💰 Tokocrypto Portfolio
        </button>
      </div>

      {/* ===== FILTER CONTROLS ===== */}
      <div style={styles.filterContainer}>
        <div style={styles.filterGroup}>
          <label style={styles.label}>Start Date:</label>
          <input
            type="date"
            value={startDate || ''}
            onChange={(e) => setStartDate(e.target.value)}
            className="analytics-date-input"
          />
        </div>

        <div style={styles.filterGroup}>
          <label style={styles.label}>End Date:</label>
          <input
            type="date"
            value={endDate || ''}
            onChange={(e) => setEndDate(e.target.value)}
            className="analytics-date-input"
          />
        </div>

        <div style={styles.filterGroup}>
          <label style={styles.label}>Timeframe:</label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            style={styles.select}
          >
            <option value="daily">📅 Daily</option>
            <option value="weekly">📆 Weekly</option>
            <option value="monthly">📊 Monthly</option>
            <option value="yearly">📈 Yearly</option>
          </select>
        </div>

        <div style={styles.filterButtons}>
          <button
            onClick={handleApplyDateFilter}
            style={styles.buttonApply}
            disabled={loading}
          >
            {loading ? '⏳ Loading...' : '🔍 Apply Filter'}
          </button>
          <button
            onClick={handleResetFilters}
            style={styles.buttonReset}
          >
            🔄 Reset
          </button>
        </div>
      </div>

      {/* ===== ERROR MESSAGE ===== */}
      {error && (
        <div style={styles.errorMessage}>
          ❌ {error}
        </div>
      )}

      {/* ===== LOADING STATE ===== */}
      {loading && (
        <div style={styles.loadingMessage}>
          ⏳ Loading analytics data...
        </div>
      )}

      {/* ===== SUMMARY CARDS ===== */}
      {analyticsData && !loading && (
        <>
          <div style={styles.summaryCardsContainer}>
            {/* Total Profit Card */}
            <SummaryCard
              title="Total Profit"
              value={
                activeTab === 'solana'
                  ? analyticsData.summary.net_profit_sol
                  : analyticsData.summary.net_profit_usdt
              }
              suffix={activeTab === 'solana' ? 'SOL' : 'USDT'}
              isSol={activeTab === 'solana'}
              color={getColorByValue(
                activeTab === 'solana'
                  ? analyticsData.summary.net_profit_sol
                  : analyticsData.summary.net_profit_usdt
              )}
              icon="💰"
            />

            {/* Win Rate Card */}
            <SummaryCard
              title="Win Rate"
              value={analyticsData.summary.win_rate}
              suffix="%"
              color="#3b82f6"
              icon="🎯"
            />

            {/* Total Trades Card */}
            <SummaryCard
              title="Total Trades"
              value={analyticsData.summary.total_trades}
              suffix=""
              color="#8b5cf6"
              icon="📈"
            />

            {/* Winning Trades Card */}
            <SummaryCard
              title="Winning Trades"
              value={analyticsData.summary.winning_trades}
              suffix=""
              color="#10b981"
              icon="✅"
            />

            {/* Losing Trades Card */}
            <SummaryCard
              title="Losing Trades"
              value={analyticsData.summary.losing_trades}
              suffix=""
              color="#ef4444"
              icon="❌"
            />

            {/* Additional Info (Profit vs Loss) */}
            {activeTab === 'solana' ? (
              <>
                <SummaryCard
                  title="Total Revenue (SOL)"
                  value={analyticsData.summary.total_profit_sol}
                  suffix="SOL"
                  color="#10b981"
                  icon="📈"
                />
                <SummaryCard
                  title="Total Invested (SOL)"
                  value={analyticsData.summary.total_loss_sol}
                  suffix="SOL"
                  color="#ef4444"
                  icon="📉"
                />
              </>
            ) : (
              <>
                <SummaryCard
                  title="Total Revenue (USDT)"
                  value={analyticsData.summary.total_profit_usdt}
                  suffix="USDT"
                  color="#10b981"
                  icon="📈"
                />
                <SummaryCard
                  title="Total Invested (USDT)"
                  value={analyticsData.summary.total_loss_usdt}
                  suffix="USDT"
                  color="#ef4444"
                  icon="📉"
                />
              </>
            )}
          </div>

          {/* ===== CHARTS ===== */}
          {analyticsData.data && analyticsData.data.length > 0 ? (
            <div style={styles.chartsContainer}>
              {/* Growth Chart (Cumulative Profit) */}
              <div style={styles.chartWrapper}>
                <h2 style={styles.chartTitle}>📈 Cumulative Profit Growth</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart
                    data={analyticsData.data}
                    margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="colorGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      style={{ fontSize: '12px', fontWeight: '500' }}
                      tick={{ fontSize: 12, fontWeight: 500 }}
                    />
                    <YAxis style={{ fontSize: '12px', fontWeight: '500' }} />
                    <Tooltip
                      formatter={(value) =>
                        activeTab === 'solana'
                          ? `${value.toFixed(8)} SOL`
                          : `$${value.toFixed(2)}`
                      }
                      contentStyle={{ fontSize: '13px', fontWeight: '600' }}
                    />
                    <Area
                      type="monotone"
                      dataKey={
                        activeTab === 'solana'
                          ? 'cumulative_profit_sol'
                          : 'cumulative_profit'
                      }
                      stroke="#10b981"
                      fillOpacity={1}
                      fill="url(#colorGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Profit/Loss Bar Chart */}
              <div style={styles.chartWrapper}>
                <h2 style={styles.chartTitle}>📊 Profit/Loss per Period</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={analyticsData.data}
                    margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      style={{ fontSize: '12px', fontWeight: '500' }}
                      tick={{ fontSize: 12, fontWeight: 500 }}
                    />
                    <YAxis style={{ fontSize: '12px', fontWeight: '500' }} />
                    <Tooltip
                      formatter={(value) =>
                        activeTab === 'solana'
                          ? `${value.toFixed(8)} SOL`
                          : `$${value.toFixed(2)}`
                      }
                      contentStyle={{ fontSize: '13px', fontWeight: '600' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '600' }} />
                    <Bar
                      dataKey={
                        activeTab === 'solana' ? 'profit_sol' : 'profit_usdt'
                      }
                      fill="#3b82f6"
                      name={
                        activeTab === 'solana' ? 'Profit (SOL)' : 'Profit (USDT)'
                      }
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Line Chart (Alternative View) */}
              <div style={styles.chartWrapper}>
                <h2 style={styles.chartTitle}>📉 Trend Analysis</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart
                    data={analyticsData.data}
                    margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      style={{ fontSize: '12px', fontWeight: '500' }}
                      tick={{ fontSize: 12, fontWeight: 500 }}
                    />
                    <YAxis style={{ fontSize: '12px', fontWeight: '500' }} />
                    <Tooltip
                      formatter={(value) =>
                        activeTab === 'solana'
                          ? `${value.toFixed(8)} SOL`
                          : `$${value.toFixed(2)}`
                      }
                      contentStyle={{ fontSize: '13px', fontWeight: '600' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '600' }} />
                    <Line
                      type="monotone"
                      dataKey={
                        activeTab === 'solana'
                          ? 'cumulative_profit_sol'
                          : 'cumulative_profit'
                      }
                      stroke="#10b981"
                      name={
                        activeTab === 'solana'
                          ? 'Cumulative Profit (SOL)'
                          : 'Cumulative Profit (USDT)'
                      }
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <div style={styles.noDataMessage}>
              📭 No data available for the selected filters
            </div>
          )}
        </>
      )}
    </div>
  );
};

// =========================================
// SUMMARY CARD COMPONENT
// =========================================
const SummaryCard = ({ title, value, suffix, color, icon }) => {
  const formattedValue =
    typeof value === 'number' && value % 1 !== 0
      ? value.toFixed(suffix === '' ? 0 : suffix === 'SOL' ? 8 : 2)
      : value;

  return (
    <div style={{ ...styles.summaryCard, borderLeft: `4px solid ${color}` }}>
      <div style={styles.cardIcon}>{icon}</div>
      <div style={styles.cardTitle}>{title}</div>
      <div style={{ ...styles.cardValue, color }}>
        {formattedValue} {suffix}
      </div>
    </div>
  );
};

// =========================================
// STYLING
// =========================================
const styles = {
  container: {
    padding: '20px',
    backgroundColor: '#f9fafb',
    borderRadius: '8px',
    fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
  },
  title: {
    fontSize: '32px',
    fontWeight: '900',
    marginBottom: '25px',
    color: '#0f172a',
  },
  tabSwitcher: {
    display: 'flex',
    gap: '10px',
    marginBottom: '20px',
    borderBottom: '2px solid #e5e7eb',
  },
  tabButton: {
    padding: '12px 24px',
    border: 'none',
    backgroundColor: 'transparent',
    color: '#6b7280',
    cursor: 'pointer',
    fontSize: '15px',
    fontWeight: '600',
    borderBottom: '3px solid transparent',
    transition: 'all 0.3s ease',
  },
  tabButtonActive: {
    color: '#1f2937',
    borderBottom: '3px solid #3b82f6',
    fontWeight: '700',
  },
  filterContainer: {
    display: 'flex',
    gap: '15px',
    marginBottom: '20px',
    padding: '18px',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    flexWrap: 'wrap',
    alignItems: 'flex-end',
    border: '1px solid #e5e7eb',
  },
  filterGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '5px',
    pointerEvents: 'auto',
  },
  label: {
    fontSize: '13px',
    fontWeight: '700',
    color: '#1f2937',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  select: {
    padding: '10px 12px',
    border: '2px solid #d1d5db',
    borderRadius: '4px',
    fontSize: '14px',
    fontWeight: '500',
    width: '150px',
    backgroundColor: 'white',
    color: '#1f2937',
    cursor: 'pointer',
    transition: 'border-color 0.2s',
  },
  filterButtons: {
    display: 'flex',
    gap: '10px',
  },
  buttonApply: {
    padding: '10px 18px',
    backgroundColor: '#3b82f6',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '700',
    transition: 'background-color 0.3s, box-shadow 0.2s',
    boxShadow: '0 2px 4px rgba(59, 130, 246, 0.3)',
  },
  buttonReset: {
    padding: '10px 18px',
    backgroundColor: '#e5e7eb',
    color: '#374151',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '700',
    transition: 'background-color 0.3s, box-shadow 0.2s',
  },
  errorMessage: {
    padding: '14px 16px',
    backgroundColor: '#fecaca',
    color: '#7f1d1d',
    borderRadius: '6px',
    marginBottom: '20px',
    fontSize: '14px',
    fontWeight: '600',
    border: '1px solid #fca5a5',
  },
  loadingMessage: {
    padding: '25px',
    textAlign: 'center',
    color: '#4b5563',
    fontSize: '16px',
    fontWeight: '600',
  },
  noDataMessage: {
    padding: '50px 20px',
    textAlign: 'center',
    color: '#6b7280',
    fontSize: '16px',
    fontWeight: '600',
  },
  summaryCardsContainer: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '15px',
    marginBottom: '30px',
  },
  summaryCard: {
    padding: '22px',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    transition: 'transform 0.2s, box-shadow 0.2s',
    borderLeft: '4px solid #d1d5db',
  },
  cardIcon: {
    fontSize: '32px',
    marginBottom: '12px',
  },
  cardTitle: {
    fontSize: '13px',
    color: '#374151',
    fontWeight: '700',
    textTransform: 'uppercase',
    marginBottom: '10px',
    letterSpacing: '0.5px',
  },
  cardValue: {
    fontSize: '24px',
    fontWeight: '900',
  },
  chartsContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '30px',
  },
  chartWrapper: {
    backgroundColor: 'white',
    padding: '25px',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: '1px solid #e5e7eb',
  },
  chartTitle: {
    fontSize: '18px',
    fontWeight: '800',
    marginBottom: '18px',
    color: '#0f172a',
  },
};

export default AnalyticsTab;
