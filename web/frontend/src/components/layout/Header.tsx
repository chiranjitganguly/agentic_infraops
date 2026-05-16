import { useUserStore } from '@/store/user'

interface HeaderProps {
  onSidebarToggle?: () => void
  themeToggleSlot?: React.ReactNode
}

export function Header({ onSidebarToggle, themeToggleSlot }: HeaderProps) {
  const { user_id, role, daily_provisioning_count, daily_provisioning_limit, loaded } =
    useUserStore()

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center gap-3">
        {onSidebarToggle && (
          <button
            onClick={onSidebarToggle}
            aria-label="Toggle sidebar"
            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 md:hidden"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
        )}

        <span className="text-sm font-semibold text-slate-900 dark:text-slate-50">
          InfraOps Q&amp;A
        </span>
      </div>

      <div className="flex items-center gap-4">
        {loaded && user_id && (
          <>
            <span className="hidden text-xs text-slate-500 dark:text-slate-400 sm:inline">
              {user_id}
            </span>
            {role && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {role}
              </span>
            )}
            {role === 'developer' && (
              <span
                className="hidden text-xs text-slate-500 dark:text-slate-400 sm:inline"
                aria-label={`${daily_provisioning_count} of ${daily_provisioning_limit} daily provisioning resources used`}
              >
                {daily_provisioning_count}&nbsp;/&nbsp;{daily_provisioning_limit} today
              </span>
            )}
          </>
        )}

        {themeToggleSlot}
      </div>
    </header>
  )
}
