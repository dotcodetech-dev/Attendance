import type { ReactNode } from "react";

/**
 * "Something is happening" banner: spinner, what is happening, and how long it can take.
 * Use it wherever the app waits on a reader or a long job, so the screen never just sits still.
 * `bar` adds a sliding bar for waits whose length is unknown.
 */
export function LoadingNote({ message, hint, bar = false }: { message: ReactNode; hint?: ReactNode; bar?: boolean }) {
  return (
    <div className="dev-loading" role="status" aria-live="polite">
      <span className="en-spinner" aria-hidden />
      <div className="dev-loading-body">
        <strong>{message}</strong>
        {hint && <p>{hint}</p>}
        {bar && <span className="dev-bar" aria-hidden><i /></span>}
      </div>
    </div>
  );
}

/** Shimmering placeholder rows, so a list keeps its height while it loads. */
export function SkeletonRows({ count = 4 }: { count?: number }) {
  return (
    <div className="dev-skeleton" aria-hidden>
      {Array.from({ length: count }, (_, i) => <div key={i} className="dev-skel-row" style={{ opacity: 1 - i * 0.15 }} />)}
    </div>
  );
}

/** Small inline spinner for a busy button label. */
export function BtnSpinner() {
  return <span className="en-spinner is-sm" aria-hidden />;
}
