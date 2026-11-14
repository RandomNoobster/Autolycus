/**
 * Custom hook for managing user's nation ID in localStorage
 */
import { useState, useCallback } from 'react';

import { parseNationId } from '@/utils/nationId';

const NATION_ID_KEY = 'autolycus_nation_id';

export function useNationId() {
  const [nationId, setNationIdState] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(NATION_ID_KEY);
      return stored || '';
    } catch {
      return '';
    }
  });

  const setNationId = useCallback((id: string) => {
    const trimmed = id.trim();
    // Keep the id for this visit even when storage is unavailable (private mode, quota).
    setNationIdState(trimmed);
    try {
      localStorage.setItem(NATION_ID_KEY, trimmed);
    } catch (error) {
      console.error('Failed to save nation ID to localStorage:', error);
    }
  }, []);

  return {
    nationId,
    setNationId,
    parseNationId,
  };
}
