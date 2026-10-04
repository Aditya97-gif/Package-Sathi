import { useEffect, useState } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import axios from 'axios'

const FIELD_META = {
  mrp:               { label: 'MRP', icon: '💰' },
  net_quantity:      { label: 'Net Quantity', icon: '⚖️' },
  mfg_date:          { label: 'Mfg / Packing Date', icon: '📅' },
  expiry_date:       { label: 'Expiry / Best Before', icon: '⏰' },
  batch_number:      { label: 'Batch / Lot Number', icon: '🔢' },
  fssai_license:     { label: 'FSSAI License', icon: '🏛️' },
  consumer_helpline: { label: 'Consumer Helpline', icon: '📞' },
  consumer_email:    { label: 'Consumer Email', icon: '✉️' },
  manufacturer_name: { label: 'Manufacturer / Packer', icon: '🏭' },
  inclusive_of_taxes:{ label: 'MRP Incl. All Taxes', icon: '✅' },
}

function ScoreGauge({ score, status }) {
  const color = status === 'compliant' ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--error)'
  const radius = 44
  const circ = 2 * Math.PI * radius
  const dash = (score / 100) * circ

  return (
    <div className="score-ring-container">
      <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r={radius} fill="none" stroke="var(--border-subtle)" strokeWidth="8"/>
        <circle
          cx="55" cy="55" r={radius}
          fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 55 55)"
          style={{ transition: 'stroke-dasharray 1s ease' }}
        />
        <text x="55" y="50" textAnchor="middle" fill={color} fontSize="20" fontWeight="800" fontFamily="Inter">
          {Math.round(score)}
        </text>
        <text x="55" y="66" textAnchor="middle" fill="var(--text-muted)" fontSize="9" fontFamily="Inter">
          / 100
        </text>
      </svg>
      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Compliance Score
      </span>
    </div>
  )
}

function CheckItem({ check, index }) {
  const icons = { pass: '✓', fail: '✗', warning: '⚠' }
  return (
    <div className={`check-item ${check.status}`} style={{ animationDelay: `${index * 40}ms` }}>
      <span className={`check-icon`} style={{ color: check.status === 'pass' ? 'var(--success)' : check.status === 'warning' ? 'var(--warning)' : 'var(--error)' }}>
        {icons[check.status] || '?'}
      </span>
      <div className="check-body">
        <div className="check-label">{check.field_label || check.field_id}</div>
        <div className="check-message">{check.message}</div>
        {check.extracted_value && (
          <div className="check-value">→ {check.extracted_value}</div>
        )}
        {check.rule_ref && <div className="check-rule">{check.rule_ref}</div>}
      </div>
      <span className={`badge ${check.status === 'pass' ? 'badge-success' : check.status === 'warning' ? 'badge-warning' : 'badge-error'}`}>
        {check.status}
      </span>
    </div>
  )
}

export default function Results() {
  const { scanId } = useParams()
  const location   = useLocation()
  const [data, setData]   = useState(location.state?.result || null)
  const [loading, setLoading] = useState(!location.state?.result)
  const [showOcr, setShowOcr] = useState(false)

  useEffect(() => {
    if (!data) {
      axios.get(`/api/scan/${scanId}`)
        .then(r => setData(r.data))
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [scanId, data])

  if (loading) return (
    <div className="spinner-overlay" style={{ position: 'static', background: 'transparent', minHeight: '60vh' }}>
      <div className="spinner" /><p className="spinner-text">Loading scan results…</p>
    </div>
  )
  if (!data) return <p className="text-muted">Scan not found.</p>

  const report  = data.compliance_report || {}
  const fields  = data.extracted_fields || {}
  const checks  = report.checks || []
  const overall = report.overall_status || 'unknown'
  const score   = report.compliance_score || 0

  return (
    <>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1>Compliance Report</h1>
          <p>Scan #{data.scan_id} · {data.image_filename} · Engine: <span className="font-mono" style={{ color: 'var(--accent-light)' }}>{data.engine_used}</span>{data.llm_used && ' + mistral:7b'}</p>
        </div>
        <div className="flex gap-2">
          <a href={`/api/report/${data.scan_id}`} target="_blank" rel="noreferrer" className="btn btn-primary">
            ⬇ Download PDF
          </a>
          <Link to="/" className="btn btn-secondary">+ New Scan</Link>
        </div>
      </div>

      {/* Overall Banner */}
      <div className={`result-banner ${overall}`}>
        <div>
          <div className="result-banner-title" style={{ color: overall === 'compliant' ? 'var(--success)' : 'var(--error)' }}>
            {overall === 'compliant' ? '✓ Compliant' : '✗ Non-Compliant'}
          </div>
          <div className="text-secondary" style={{ fontSize: '0.85rem', marginTop: 4 }}>
            {overall === 'compliant'
              ? 'This label meets core Legal Metrology requirements.'
              : `${report.violations?.length || 0} violation(s) detected — review details below.`}
          </div>
        </div>
        <ScoreGauge score={score} status={overall} />
      </div>

      <div className="two-col mt-6" style={{ alignItems: 'start' }}>
        {/* Left: Check Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="section-title">Compliance Checks</div>
            <div className="check-list">
              {checks.map((c, i) => <CheckItem key={c.field_id || i} check={c} index={i} />)}
            </div>
          </div>
        </div>

        {/* Right: Extracted Fields + OCR */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="section-title">Extracted Declarations</div>
            <div className="fields-grid">
              {Object.entries(FIELD_META).map(([key, { label, icon }]) => {
                const val = fields[key]
                const displayVal = val === null || val === undefined || val === ''
                  ? null
                  : val === true ? 'Yes'
                  : val === false ? 'No'
                  : String(val)
                return (
                  <div className="field-card" key={key}>
                    <div className="field-card-label">{icon} {label}</div>
                    <div className={`field-card-value ${!displayVal ? 'missing' : ''}`}>
                      {displayVal || 'Not detected'}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <div className="section-title" style={{ marginBottom: 0 }}>Raw OCR Text</div>
              <button
                id="toggle-ocr"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowOcr(v => !v)}
              >
                {showOcr ? '▲ Hide' : '▼ Show'}
              </button>
            </div>
            {showOcr && (
              <div className="ocr-box">{data.ocr_text || 'No OCR text captured.'}</div>
            )}
            {!showOcr && (
              <p className="text-muted" style={{ fontSize: '0.8rem' }}>
                {data.ocr_text ? `${data.ocr_text.length.toLocaleString()} characters extracted` : 'No text extracted.'}
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
