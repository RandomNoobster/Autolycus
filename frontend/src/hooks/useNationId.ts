/**
 * Custom hook for managing user's nation ID in localStorage
 */
import { useState } from 'react';

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

  const setNationId = (id: string) => {
    try {
      const trimmed = id.trim();
      localStorage.setItem(NATION_ID_KEY, trimmed);
      setNationIdState(trimmed);
    } catch (error) {
      console.error('Failed to save nation ID to localStorage:', error);
    }
  };

  const clearNationId = () => {
    try {
      localStorage.removeItem(NATION_ID_KEY);
      setNationIdState('');
    } catch (error) {
      console.error('Failed to clear nation ID from localStorage:', error);
    }
  };

  /**
   * Extract nation ID from a Politics & War nation link or return the ID as-is
   * Supports formats like:
   * - https://politicsandwar.com/nation/id=123456
   * - 123456
   */
  const parseNationId = (input: string): string | null => {
    const trimmed = input.trim();
    
    // Try to extract from URL
    const urlMatch = trimmed.match(/(?:nation\/id=|nation_id=)(\d+)/i);
    if (urlMatch) {
      return urlMatch[1];
    }
    
    // Check if it's just a number
    if (/^\d+$/.test(trimmed)) {
      return trimmed;
    }
    
    return null;
  };

  return {
    nationId,
    setNationId,
    clearNationId,
    parseNationId,
  };
}
