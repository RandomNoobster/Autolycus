/**
 * Resolves access token from URL first, then localStorage (per data type).
 * When the URL contains a token, verifies with the API and refreshes storage.
 */

import { useEffect, useState } from 'react';
import { verifyToken } from '@/api/auth';
import {
  ACCESS_TOKEN_MAX_AGE_SEC,
  readStoredAccessToken,
  writeStoredAccessToken,
  type AccessDataType,
} from '@/lib/accessTokenStorage';

export function usePersistedAccessToken(
  dataType: AccessDataType,
  urlToken: string | null
) {
  const [storedToken, setStoredToken] = useState<string | null>(() =>
    readStoredAccessToken(dataType)?.token ?? null
  );

  useEffect(() => {
    setStoredToken(readStoredAccessToken(dataType)?.token ?? null);
  }, [dataType]);

  useEffect(() => {
    if (!urlToken) return;
    let cancelled = false;
    (async () => {
      try {
        const v = await verifyToken(urlToken);
        if (
          cancelled ||
          !v.valid ||
          !v.payload ||
          typeof v.payload.timestamp !== 'number'
        ) {
          return;
        }
        const expiresAt = v.payload.timestamp + ACCESS_TOKEN_MAX_AGE_SEC;
        writeStoredAccessToken(dataType, urlToken, expiresAt);
        setStoredToken(urlToken);
      } catch {
        /* Invalid / expired URL token — do not write to storage */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [urlToken, dataType]);

  const resolveToken = (memoryToken: string | null) =>
    urlToken || memoryToken || storedToken;

  return { resolveToken };
}
