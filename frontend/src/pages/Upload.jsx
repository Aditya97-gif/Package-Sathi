import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const ACCEPTED_TYPES = { 'image/jpeg': [], 'image/png': [], 'image/webp': [] }

function LoadingOverlay({ text }) {
  return (
    <div className="spinner-overlay">
      <div className="spinner" />
      <p className="spinner-text">{text}</p>
    </div>
  )
}

export default function Upload() {
  const [file, setFile]           = useState(null)
  const [preview, setPreview]     = useState(null)
  const [engine, setEngine]       = useState('tesseract')
  const [useLlm, setUseLlm]       = useState(true)
  const [loading, setLoading]     = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError]         = useState(null)
  const navigate = useNavigate()

  const onDrop = useCallback((accepted) => {
    if (!accepted.length) return
    const f = accepted[0]
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setError(null)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxFiles: 1,
    maxSize: 20 * 1024 * 1024,
    onDropRejected: () => setError('Invalid file. Please upload a JPEG, PNG, or WebP image under 20 MB.'),
  })

  const handleScan = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      setLoadingMsg('Running OCR on label…')
      const formData = new FormData()
      formData.append('file', file)
      formData.append('engine', engine)
      formData.append('use_llm', useLlm)

      // Small delay so the first message is visible
      await new Promise(r => setTimeout(r, 500))
      setLoadingMsg('Extracting compliance fields…')

      const { data } = await axios.post('/api/scan', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: () => setLoadingMsg('Uploading image…'),
      })

      setLoadingMsg('Generating compliance report…')
      await new Promise(r => setTimeout(r, 300))

      navigate(`/results/${data.scan_id}`, { state: { result: data } })
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Something went wrong. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setPreview(null)
    setError(null)
  }

  return (
    <>
      {loading && <LoadingOverlay text={loadingMsg} />}

      <div className="page-header">
        <h1>Label Compliance Scanner</h1>
        <p>Upload a packaged commodity label to check compliance with the Legal Metrology (PC) Rules, 2011</p>
      </div>

      <div className="two-col" style={{ alignItems: 'start' }}>
        {/* Left: Upload */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="section-title">Label Image</div>

          {!preview ? (
            <div
              {...getRootProps()}
              className={`upload-zone ${isDragActive ? 'drag-active' : ''}`}
            >
              <input {...getInputProps()} id="label-upload-input" />
              <span className="upload-icon">🖼️</span>
              <h3>Drop your label image here</h3>
              <p>or <span className="browse-text">browse files</span></p>
              <p style={{ marginTop: 8 }}>JPEG · PNG · WebP · max 20 MB</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <img src={preview} alt="Label preview" className="image-preview" />
              <div className="flex gap-2">
                <button className="btn btn-ghost btn-sm" onClick={handleReset}>✕ Remove</button>
                <span className="text-muted" style={{ fontSize: '0.8rem', alignSelf: 'center' }}>{file.name}</span>
              </div>
            </div>
          )}

          {error && (
            <div className="check-item fail" style={{ marginTop: 0 }}>
              <span className="check-icon">✗</span>
              <div className="check-body">
                <div className="check-message">{error}</div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Settings + Action */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="section-title">OCR Engine</div>
            <div className="toggle-group" style={{ width: '100%' }}>
              {['tesseract', 'easyocr'].map(e => (
                <button
                  key={e}
                  id={`engine-${e}`}
                  className={`toggle-btn flex-1 ${engine === e ? 'active' : ''}`}
                  onClick={() => setEngine(e)}
                >
                  {e === 'tesseract' ? '🔤 Tesseract' : '🤖 EasyOCR'}
                </button>
              ))}
            </div>
            <p className="text-muted mt-4" style={{ fontSize: '0.78rem' }}>
              {engine === 'tesseract'
                ? 'Tesseract: Fast, best for clean high-contrast labels.'
                : 'EasyOCR: Deep-learning, better on curved/wrinkled packaging.'}
            </p>
          </div>

          <div className="card">
            <div className="section-title">AI Field Extraction</div>
            <div className="flex items-center justify-between">
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Ollama mistral:7b</div>
                <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: 2 }}>
                  Local LLM fallback when regex misses fields
                </div>
              </div>
              <button
                id="toggle-llm"
                className={`toggle-btn ${useLlm ? 'active' : ''}`}
                onClick={() => setUseLlm(v => !v)}
                style={{ borderRadius: 999, minWidth: 52 }}
              >
                {useLlm ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="section-title">About This Check</div>
            <ul style={{ display: 'flex', flexDirection: 'column', gap: 6, listStyle: 'none' }}>
              {[
                ['📦', 'Manufacturer name & address'],
                ['⚖️', 'Net Quantity (SI units)'],
                ['💰', 'MRP incl. all taxes'],
                ['📅', 'Month & Year of Manufacture'],
                ['⏰', 'Expiry / Best Before date'],
                ['📞', 'Consumer care contact'],
                ['🏛️', 'FSSAI license number'],
                ['🔢', 'Batch / Lot number'],
              ].map(([icon, label]) => (
                <li key={label} style={{ display: 'flex', gap: 8, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  <span>{icon}</span><span>{label}</span>
                </li>
              ))}
            </ul>
          </div>

          <button
            id="scan-btn"
            className="btn btn-primary btn-lg w-full"
            onClick={handleScan}
            disabled={!file || loading}
          >
            🔍 Run Compliance Check
          </button>
        </div>
      </div>
    </>
  )
}
