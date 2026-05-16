import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from '@/components/layout/AppShell'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { Sidebar } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { useAuth } from '@/hooks/useAuth'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

function InfraOpsApp() {
  useAuth()

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
