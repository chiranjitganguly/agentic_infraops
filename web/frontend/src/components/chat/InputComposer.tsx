import { useRef, useState, type KeyboardEvent } from 'react'

interface InputComposerProps {
  onSubmit: (text: string) => void
  loading?: boolean
  initialValue?: string
}

export function InputComposer({ onSubmit, loading = false, initialValue = '' }: InputComposerProps) {
  const [value, setValue] = useState(initialValue)
  const [shake, setShake] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function submit() {
    const trimmed = value.trim()
    if (!trimmed) {
      setShake(true)
      setTimeout(() => setShake(false), 400)
      return
    }
    onSubmit(trimmed)
    setValue('')
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!loading) submit()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  return (
    <div
      className={[
        'flex items-end gap-2 border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900',
        shake ? 'animate-[shake_0.4s_ease-in-out]' : '',
      ].join(' ')}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={loading}
        rows={1}
        placeholder="Ask anything about your infrastructure…"
        aria-label="Message input"
        className={[
          'flex-1 resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm',
          'text-slate-900 placeholder-slate-400 outline-none transition',
          'focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
          'dark:border-slate-600 dark:bg-slate-800 dark:text-slate-50 dark:placeholder-slate-500',
          'dark:focus:border-blue-400 dark:focus:ring-blue-400',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'max-h-[200px] overflow-y-auto scrollbar-thin',
        ].join(' ')}
      />

      <button
        onClick={submit}
        disabled={loading}
        aria-label="Send message"
        className={[
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition',
          'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800',
          'disabled:cursor-not-allowed disabled:opacity-40',
          'dark:bg-blue-500 dark:hover:bg-blue-600',
        ].join(' ')}
      >
        {loading ? (
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
          </svg>
        ) : (
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        )}
      </button>
    </div>
  )
}
