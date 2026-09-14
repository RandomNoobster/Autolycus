import { useEffect, useState } from 'react';

/** Current time in ms, refreshed on an interval so relative times ("in 5 minutes") stay current. */
export function useNow(intervalMs: number = 30_000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);

  return now;
}
