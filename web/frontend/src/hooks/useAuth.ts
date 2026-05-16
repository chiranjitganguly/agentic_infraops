import { useEffect } from 'react'
import { getMe } from '@/api/auth'
import { useUserStore } from '@/store/user'

export function useAuth(): void {
  const setUser = useUserStore((s) => s.setUser)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // Auth failure degrades gracefully — store stays with loaded: false.
        // The header will show no user info; requests will get 401 responses.
        useUserStore.setState({ loaded: true })
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
