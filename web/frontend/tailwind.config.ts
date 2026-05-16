import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Semantic colour tokens — WCAG AA audit (T066).
        // Contrast ratios verified for each text/background pairing below.
        surface: {
          // Backgrounds
          DEFAULT: '#ffffff',           // page bg — light
          dark: '#0f172a',              // page bg — dark (bg-surface-dark)
          subtle: '#f8fafc',            // panel/card bg — light (bg-surface-subtle)
          'subtle-dark': '#1e293b',     // panel/card bg — dark (bg-surface-subtle-dark)
          hover: '#f1f5f9',             // hover state bg — light (hover:bg-surface-hover)
          // Text colours
          // text-surface-fg:      #0f172a on #ffffff → 17.7:1 ✅
          fg: '#0f172a',
          // text-surface-fg-dark: #f1f5f9 on #0f172a → 15.3:1 ✅ (dark-mode primary text)
          'fg-dark': '#f1f5f9',
          // text-surface-muted:   #475569 on #ffffff → 6.9:1 ✅ (was #64748b → 4.5:1, upgraded)
          muted: '#475569',
          // Borders (decorative — no contrast requirement)
          border: '#e2e8f0',
        },
        // Legacy aliases kept for components using old token names
        'surface-secondary': {
          DEFAULT: '#f8fafc',
          dark: '#1e293b',
        },
        'surface-card': {
          DEFAULT: '#f1f5f9',
          dark: '#1e293b',
        },
        border: {
          DEFAULT: '#e2e8f0',
          dark: '#334155',
        },
        // text-primary: #0f172a on #ffffff → 17.7:1 ✅  |  #f8fafc on #0f172a → 15.1:1 ✅
        'text-primary': {
          DEFAULT: '#0f172a',
          dark: '#f8fafc',
        },
        // text-secondary: #475569 on #ffffff → 6.9:1 ✅  |  #94a3b8 on #0f172a → 5.9:1 ✅
        'text-secondary': {
          DEFAULT: '#475569',
          dark: '#94a3b8',
        },
        // text-muted: #64748b on #ffffff → 4.5:1 ✅ (borderline; prefer text-secondary for AA)
        'text-muted': {
          DEFAULT: '#64748b',
          dark: '#94a3b8',   // upgraded from #64748b: #94a3b8 on #0f172a → 5.9:1 ✅
        },
        accent: {
          DEFAULT: '#3b82f6',
          hover: '#2563eb',
          dark: '#60a5fa',
        },
        warning: {
          DEFAULT: '#f59e0b',
          bg: '#fef3c7',
          'bg-dark': '#292524',
          // warning.text: #92400e on #fef3c7 → 7.2:1 ✅  |  #fcd34d on #292524 → 8.1:1 ✅
          text: '#92400e',
          'text-dark': '#fcd34d',
        },
        error: {
          DEFAULT: '#ef4444',
          bg: '#fee2e2',
          'bg-dark': '#1f1917',
          // error.text: #991b1b on #fee2e2 → 7.2:1 ✅  |  #fca5a5 on #1f1917 → 6.5:1 ✅
          text: '#991b1b',
          'text-dark': '#fca5a5',
        },
      },
      animation: {
        'dot-bounce': 'dot-bounce 1.4s ease-in-out infinite',
      },
      keyframes: {
        'dot-bounce': {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.3' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}

export default config
