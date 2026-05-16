import { useEffect } from 'react'
import { getMe } from '@/api/auth'
import { useUserStore } from '@/store/user'
import { getStoredToken } from '@/api/client'

export function useAuth(): { authenticated: boolean; loaded: boolean } {
  const setUser = useUserStore((s) => s.setUser)
  const logout = useUserStore((s) => s.logout)
  const loaded = useUserStore((s) => s.loaded)
  const user_id = useUserStore((s) => s.user_id)

  useEffect(() => {
    const token = getStoredToken()
    if (!token) {
      useUserStore.setState({ loaded: true })
      return
    }
    getMe()
      .then(setUser)
      .catch(() => {
        // Token invalid or expired — clear it and force login.
        logout()
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { authenticated: loaded && user_id !== null, loaded }
}
