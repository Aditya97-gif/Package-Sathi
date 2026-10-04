import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function ScoreBadge({ score, status }) {
  const cls = status === 'compliant' ? 'badge-success' : score >= 50 ? 'badge-warning' : 'badge-error'
  return <span className={`badge ${cls}`}>{Math.round(score)}%</span>
}

export default function History() {
  const [scans, setScans]   = useState([])
  const [total, setTotal]   = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage]     = useState(0)
  const limit = 15

  const fetchScans = async (offset = 0) => {
    setLoading(true)
    try {
      const { data } = await axios.get(`/api/history?limit=${limit}&offset=${offset}`)
      setScans(data.scans)
      setTotal(data.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchScans(page * limit) }, [page])

  const totalPages = Math.ceil(total / limit)

  return (
    <>
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1>Scan History</h1>
          <p>{total} scan{total !== 1 ? 's' : ''} recorded</p>
        </div>
        <Link to="/" className="btn btn-primary">+ New Scan</Link>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
        ) : scans.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '3rem', marginBottom: 12 }}>🔍</div>
            <p>No scans yet. <Link to="/" style={{ color: 'var(--accent-light)' }}>Upload a label</Link> to get started.</p>
          </div>
        ) : (
          <table className="history-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Label File</th>
                <th>Status</th>
                <th>Score</th>
                <th>Violations</th>
                <th>Engine</th>
                <th>Scanned At</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {scans.map(s => (
                <tr key={s.id}>
                  <td className="mono text-muted">#{s.id}</td>
                  <td>
                    <Link to={`/results/${s.id}`} className="filename" title={s.image_filename}>
                      {s.image_filename}
                    </Link>
                  </td>
                  <td>
                    <span className={`badge ${s.overall_status === 'compliant' ? 'badge-success' : 'badge-error'}`}>
                      {s.overall_status === 'compliant' ? '✓ Compliant' : '✗ Non-Compliant'}
                    </span>
                  </td>
                  <td>
                    <ScoreBadge score={s.compliance_score} status={s.overall_status} />
                  </td>
                  <td className="mono" style={{ color: s.violation_count > 0 ? 'var(--error)' : 'var(--success)' }}>
                    {s.violation_count}
                  </td>
                  <td className="mono text-muted">{s.engine_used}{s.llm_used ? ' + llm' : ''}</td>
                  <td className="text-muted" style={{ fontSize: '0.8rem' }}>{formatDate(s.created_at)}</td>
                  <td>
                    <div className="flex gap-2">
                      <Link to={`/results/${s.id}`} className="btn btn-ghost btn-sm">View</Link>
                      <a href={`/api/report/${s.id}`} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">PDF</a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between" style={{ padding: '12px 20px', borderTop: '1px solid var(--border-subtle)' }}>
            <span className="text-muted" style={{ fontSize: '0.8rem' }}>
              Page {page + 1} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
                ← Prev
              </button>
              <button className="btn btn-secondary btn-sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
