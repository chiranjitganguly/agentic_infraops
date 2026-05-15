import { useState } from 'react'
import { Header } from './Header'

interface AppShellProps {
  sidebarSlot?: React.ReactNode
  mainSlot?: React.ReactNode
  themeToggleSlot?: React.ReactNode
}

export function AppShell({ sidebarSlot, mainSlot, themeToggleSlot }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white dark:bg-slate-900">
      {/* Skip navigation link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-blue-600 focus:px-3 focus:py-2 focus:text-sm focus:text-white focus:no-underline"
      >
        Skip to main content
      </a>
      <Header
        onSidebarToggle={() => setSidebarOpen((o) => !o)}
        themeToggleSlot={themeToggleSlot}
      />

      <div className="relative flex flex-1 overflow-hidden">
        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div
            className="absolute inset-0 z-20 bg-black/40 md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Sidebar */}
        <aside
          className={[
            'absolute inset-y-0 left-0 z-30 w-64 shrink-0 transform transition-transform duration-200',
            'border-r border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
            'md:relative md:translate-x-0',
            sidebarOpen ? 'translate-x-0' : '-translate-x-full',
          ].join(' ')}
          aria-label="Conversation history"
        >
          {sidebarSlot}
        </aside>

        {/* Main content — min-w-0 prevents flex child from overflowing at 320px */}
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden" id="main-content">
          {mainSlot}
        </main>
      </div>
    </div>
  )
}
