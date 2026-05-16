import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from '@/components/layout/AppShell'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { Sidebar } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { LoginPage } from '@/pages/LoginPage'
import { useAuth } from '@/hooks/useAuth'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

function InfraOpsApp() {
  const { authenticated, loaded } = useAuth()

  if (!loaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (!authenticated) {
    return <LoginPage />
  }

  return (
    <AppShell
      sidebarSlot={<Sidebar />}
      mainSlot={<ChatWindow />}
      themeToggleSlot={<ThemeToggle />}
    />
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <InfraOpsApp />
    </QueryClientProvider>
  )
}
