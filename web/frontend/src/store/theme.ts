import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Theme } from '@/types/entities'

interface ThemeState {
  theme: Theme
}

interface ThemeActions {
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
}

function applyThemeClass(theme: Theme): void {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

export const useThemeStore = create<ThemeState & ThemeActions>()(
  persist(
    (set) => ({
      theme: 'light' as Theme,

      toggleTheme: () => {
        set((state) => {
          const next: Theme = state.theme === 'light' ? 'dark' : 'light'
          applyThemeClass(next)
          return { theme: next }
        })
      },

      setTheme: (theme) => {
        applyThemeClass(theme)
        set({ theme })
      },
    }),
    {
      name: 'infraops-ui-theme',
      onRehydrateStorage: () => (state) => {
        // Apply the persisted theme class on page load before first paint.
        if (state) applyThemeClass(state.theme)
      },
    },
  ),
)
