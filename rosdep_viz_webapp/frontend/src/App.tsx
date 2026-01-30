import { useState, useCallback } from 'react'
import { PackageSelector } from './PackageSelector'
import { DependencyGraph } from './DependencyGraph'
import type { TreeNode } from './types'

const API_BASE = '/api'

export type ApiPackages = Record<string, string>

async function fetchPackages(): Promise<ApiPackages> {
  const res = await fetch(`${API_BASE}/packages`)
  if (!res.ok) throw new Error('Failed to fetch packages')
  const data = await res.json()
  return data.packages ?? {}
}

async function fetchTree(packageName: string, maxDepth?: number): Promise<TreeNode> {
  const url = new URL(`${API_BASE}/tree/${encodeURIComponent(packageName)}`, window.location.origin)
  if (maxDepth != null) url.searchParams.set('max_depth', String(maxDepth))
  const res = await fetch(url.toString())
  if (!res.ok) {
    if (res.status === 404) throw new Error(`Package not found: ${packageName}`)
    throw new Error('Failed to fetch tree')
  }
  return res.json()
}

function App() {
  const [packages, setPackages] = useState<ApiPackages | null>(null)
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null)
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadPackages = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const pkgs = await fetchPackages()
      setPackages(pkgs)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load packages')
    } finally {
      setLoading(false)
    }
  }, [])

  const selectPackage = useCallback(async (name: string) => {
    setError(null)
    setSelectedPackage(name)
    setLoading(true)
    try {
      const t = await fetchTree(name)
      setTree(t)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tree')
      setTree(null)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="min-h-screen flex flex-col bg-surface text-slate-200">
      <header className="border-b border-edge px-6 py-4">
        <h1 className="font-display font-semibold text-xl text-accent tracking-tight">
          rosdep_viz
        </h1>
        <p className="text-sm text-slate-400 mt-0.5">
          ROS 2 package dependency tree
        </p>
      </header>

      <div className="flex-1 flex flex-col md:flex-row gap-4 p-4 overflow-hidden">
        <aside className="w-full md:w-72 shrink-0 flex flex-col gap-2">
          <PackageSelector
            packages={packages}
            loading={loading}
            error={error}
            selectedPackage={selectedPackage}
            onLoadPackages={loadPackages}
            onSelectPackage={selectPackage}
          />
        </aside>

        <main className="flex-1 min-h-0 rounded-lg border border-edge bg-surface-elevated overflow-hidden">
          {tree ? (
            <DependencyGraph tree={tree} />
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500">
              {loading
                ? 'Loading…'
                : selectedPackage
                  ? (error ?? 'No tree data')
                  : 'Select or load a package to view its dependency tree'}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

export default App
