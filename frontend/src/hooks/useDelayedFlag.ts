import { useEffect, useState } from 'react';

/**
 * Turns true only after `delayMs` to suppress short loading flickers.
 */
export function useDelayedFlag(flag: boolean, delayMs = 150): boolean {
  const [delayed, setDelayed] = useState(false);

  useEffect(() => {
    if (!flag) {
      setDelayed(false);
      return;
    }

    const timer = window.setTimeout(() => setDelayed(true), delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [flag, delayMs]);

  return delayed;
}
