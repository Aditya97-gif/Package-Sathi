import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell, Legend,
} from 'recharts'

// ── Colour tokens (match index.css design system) ────────────────────────────
const C = {
  accent:  '#6366f1',
  success: '#22c55e',
  error:   '#ef4444',
  warning: '#f59e0b',
  muted:   '#64748b',
  text:    '#e2e8f0',
  border:  'rgba(148,163,184,0.08)',
  card:    '#1e293b',
}

const PIE_COLORS = [C.success, C.error, '#818cf8']

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent }) {
  return (
    <div className="card" style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '2.4rem', fontWeight: 800, color: accent || C.accent, letterSpacing: '-0.04em', lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      <div style={{ fontWeight: 600, fontSize: '0.875rem', color: C.text, marginTop: 8 }}>{label}</div>
      {sub && <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.accent}44`, borderRadius: 8,
      padding: '8px 14px', fontSize: '0.8rem', color: C.text,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: <b>{typeof p.value === 'number' ? p.value.toFixed(p.name === 'Score' ? 1 : 0) : p.value}</b>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    axios.get('/api/dashboard')
      .then(r => setStats(r.data))
      .catch(e => setError(e.message || 'Failed to load dashboard data'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="spinner-overlay" style={{ position: 'static', background: 'transparent', minHeight: '60vh' }}>
      <div className="spinner" /><p className="spinner-text">Loading dashboard…</p>
    </div>
  )

  if (error) return (
    <div className="card" style={{ color: C.error, textAlign: 'center', padding: 48 }}>
      <div style={{ fontSize: '2rem', marginBottom: 8 }}>⚠</div>
      <p>{error}</p>
    </div>
  )

  const { total_scans, compliant_count, non_compliant_count, avg_compliance_score,
          engine_breakdown, top_violations, recent_scans } = stats

  const complianceRate = total_scans > 0 ? Math.round((compliant_count / total_scans) * 100) : 0

  const pieData = [
    { name: 'Compliant', value: compliant_count },
    { name: 'Non-Compliant', value: non_compliant_count },
  ]

  // Colour trend line by status
  const trendData = (recent_scans || []).map((s, i) => ({
    name: `#${s.id}`,
    Score: s.score,
    fill: s.status === 'compliant' ? C.success : C.error,
  }))

  const violationData = (top_violations || []).map(v => ({
    name: (v.field || '').replace(' / ', '/').replace(' & ', '&'),
    count: v.count,
  }))

  return (
    <>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1>Dashboard</h1>
          <p>Compliance analytics across all label scans</p>
        </div>
        <Link to="/" className="btn btn-primary">+ New Scan</Link>
      </div>

      {/* Stat Row */}
      <div className="three-col" style={{ marginBottom: 20 }}>
        <StatCard label="Total Scans" value={total_scans} sub="all time" />
        <StatCard label="Compliance Rate" value={`${complianceRate}%`} sub={`${compliant_count} compliant / ${non_compliant_count} non-compliant`} accent={complianceRate >= 70 ? C.success : C.error} />
        <StatCard label="Avg Compliance Score" value={`${avg_compliance_score}%`} sub="across all scans" accent={avg_compliance_score >= 70 ? C.success : C.warning} />
      </div>

      <div className="two-col" style={{ marginBottom: 20 }}>
        {/* Compliance Score Trend */}
        <div className="card">
          <div className="section-title">Compliance Score Trend</div>
          {trendData.length === 0 ? (
            <p className="text-muted" style={{ textAlign: 'center', paddingTop: 40 }}>No scans yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: C.muted, fontSize: 10 }} />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  type="monotone" dataKey="Score"
                  stroke={C.accent} strokeWidth={2.5}
                  dot={(props) => {
                    const { cx, cy, payload } = props
                    return <circle key={cx} cx={cx} cy={cy} r={4} fill={payload.fill} stroke="none" />
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Compliant vs Non-Compliant Pie */}
        <div className="card">
          <div className="section-title">Status Breakdown</div>
          {total_scans === 0 ? (
            <p className="text-muted" style={{ textAlign: 'center', paddingTop: 40 }}>No scans yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData} cx="50%" cy="50%"
                  outerRadius={80} innerRadius={42}
                  dataKey="value" paddingAngle={3}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={PIE_COLORS[idx]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  formatter={(value) => <span style={{ color: C.text, fontSize: '0.78rem' }}>{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Top Violations Bar Chart */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-title">Most Common Violations</div>
        {violationData.length === 0 ? (
          <p className="text-muted" style={{ textAlign: 'center', padding: '24px 0' }}>
            No violations recorded yet. {' '}
            <Link to="/" style={{ color: C.accent }}>Run a scan</Link> to populate this chart.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={violationData} layout="vertical" margin={{ left: 8, right: 16, top: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} horizontal={false} />
              <XAxis type="number" tick={{ fill: C.muted, fontSize: 10 }} allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={160} tick={{ fill: C.text, fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" name="Violations" fill={C.error} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Engine Breakdown */}
      {(engine_breakdown || []).length > 0 && (
        <div className="card">
          <div className="section-title">OCR Engine Usage</div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 8 }}>
            {engine_breakdown.map(e => (
              <div key={e.engine} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                background: 'var(--bg-surface)', borderRadius: 10,
                padding: '16px 28px', border: '1px solid var(--border-subtle)',
              }}>
                <div style={{ fontSize: '1.8rem', fontWeight: 800, color: C.accent }}>{e.count}</div>
                <div style={{ fontSize: '0.78rem', color: C.muted, marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {e.engine}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
