import { useState } from 'react'
import type { ApiPackages } from './App'

type Props = {
  packages: ApiPackages | null
  loading: boolean
  error: string | null
  selectedPackage: string | null
  onLoadPackages: () => void
  onSelectPackage: (name: string) => void
}

export function PackageSelector({
  packages,
  loading,
  error,
  selectedPackage,
  onLoadPackages,
  onSelectPackage,
}: Props) {
  const [filter, setFilter] = useState('')
  const names = packages ? Object.keys(packages).sort() : []
  const filtered = filter.trim()
    ? names.filter((n) => n.toLowerCase().includes(filter.trim().toLowerCase()))
    : names.slice(0, 150)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onLoadPackages}
          disabled={loading}
          className="px-3 py-2 rounded-md bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 text-sm font-medium"
        >
          {packages == null ? 'Load packages' : 'Refresh'}
        </button>
      </div>
      {error && (
        <p className="text-red-400 text-sm" role="alert">
          {error}
        </p>
      )}
      {packages && (
        <>
          <input
            type="text"
            placeholder="Filter packages…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full px-3 py-2 rounded-md bg-surface border border-edge text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <ul className="flex-1 overflow-auto border border-edge rounded-md divide-y divide-edge max-h-64">
            {filtered.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  onClick={() => onSelectPackage(name)}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-muted transition-colors ${
                    selectedPackage === name ? 'bg-accent/20 text-accent' : ''
                  }`}
                >
                  {name}
                </button>
              </li>
            ))}
          </ul>
          {names.length > filtered.length && !filter && (
            <p className="text-slate-500 text-xs">
              Showing first 150. Use filter to narrow.
            </p>
          )}
        </>
      )}
    </div>
  )
}
