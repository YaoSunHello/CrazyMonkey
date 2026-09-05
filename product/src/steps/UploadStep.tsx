import { useRef, useState } from 'react'
import { usePipeline } from '../PipelineContext'
import { detectFiles } from '../pipeline'
import './steps.css'

const ACCEPT = '.pdf,.xlsx,.xls,.csv,image/*'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function UploadStep({ onContinue }: { onContinue: () => void }) {
  const { rawFiles, setRawFiles, files, setFiles } = usePipeline()
  const [dragActive, setDragActive] = useState(false)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function addFiles(list: FileList | File[]) {
    const incoming = Array.from(list)
    if (incoming.length === 0) return
    setBusy(true)
    const nextRaw = [...rawFiles, ...incoming]
    setRawFiles(nextRaw)
    const detected = await detectFiles(nextRaw)
    setFiles(detected)
    setBusy(false)
  }

  function removeAt(index: number) {
    const nextRaw = rawFiles.filter((_, i) => i !== index)
    setRawFiles(nextRaw)
    setFiles(files.filter((_, i) => i !== index))
  }

  return (
    <div className="step">
      <p className="step__kicker">Step 1 of 4</p>
      <h1 className="step__title">Upload the messy documents</h1>
      <p className="step__lede">
        PDFs, NAV packs, fund statements, spreadsheets, or scanned images — drop in whatever
        you have. Nothing leaves this run.
      </p>

      <div
        className={`dropzone${dragActive ? ' dropzone--active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragActive(false)
          void addFiles(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            if (e.target.files) void addFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <p className="dropzone__title">Drag files here, or click to browse</p>
        <p className="dropzone__hint">PDF, XLSX, CSV, or image files</p>
      </div>

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file, i) => (
            <li key={file.id} className="file-list__item">
              <span className="file-list__name">{file.name}</span>
              <span className="file-list__size">{formatSize(file.size)}</span>
              <button
                type="button"
                className="file-list__remove"
                onClick={() => removeAt(i)}
                aria-label={`Remove ${file.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="step__actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={files.length === 0 || busy}
          onClick={onContinue}
        >
          Continue
        </button>
      </div>
    </div>
  )
}
