import { create } from 'zustand'
import type { UserState, UserRole } from '@/types/entities'
import type { GetMeResponse } from '@/types/api'
import { clearStoredToken } from '@/api/client'

interface UserActions {
  setUser: (payload: GetMeResponse) => void
  incrementDailyCount: () => void
  logout: () => void
}

export const useUserStore = create<UserState & UserActions>()((set) => ({
  user_id: null,
  role: null as UserRole | null,
  daily_provisioning_count: 0,
  daily_provisioning_limit: 10,
  loaded: false,

  setUser: (payload) => {
    set({
      user_id: payload.user_id,
      role: payload.role as UserRole,
      daily_provisioning_count: payload.daily_provisioning_count,
      daily_provisioning_limit: payload.daily_provisioning_limit,
      loaded: true,
    })
  },

  incrementDailyCount: () => {
    set((state) => ({
      daily_provisioning_count: state.daily_provisioning_count + 1,
    }))
  },

  logout: () => {
    clearStoredToken()
    set({
      user_id: null,
      role: null,
      daily_provisioning_count: 0,
      daily_provisioning_limit: 10,
      loaded: false,
    })
  },
}))
