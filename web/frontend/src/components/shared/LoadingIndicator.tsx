interface LoadingIndicatorProps {
  label?: string
}

export function LoadingIndicator({ label = 'Thinking…' }: LoadingIndicatorProps) {
  return (
    <span
      className="inline-flex items-center gap-1.5"
      role="status"
      aria-label={label}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500"
          style={{
            animation: 'dot-bounce 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.16}s`,
          }}
          aria-hidden="true"
        />
      ))}
      <span className="sr-only">{label}</span>
    </span>
  )
}
