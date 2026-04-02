/**
 * Persists API access tokens (from Discord code exchange) in localStorage.
 * Expiry aligns with API TOKEN_MAX_AGE / TOKEN_MAX_AGE_SEC; override with VITE_TOKEN_MAX_AGE_SEC.
 */

import { verifyToken } from '@/api/auth';

function parseTokenMaxAgeSec(): number {
  const raw = import.meta.env.VITE_TOKEN_MAX_AGE_SEC;
  if (raw === undefined || raw === '') {
    return 7 * 24 * 3600;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    return 7 * 24 * 3600;
  }
  return Math.max(60, Math.min(Math.floor(n), 3600 * 24 * 400));
}

export const ACCESS_TOKEN_MAX_AGE_SEC = parseTokenMaxAgeSec();

/** Fired on same-tab writes to auth storage so the sidebar can refresh. */
export const AUTH_STORAGE_CHANGED_EVENT = 'autolycus-auth-changed';

const STORAGE_PREFIX = 'autolycus-access-token-v1';

function notifyAuthStorageChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_STORAGE_CHANGED_EVENT));
  }
}

export type AccessDataType = 'raids' | 'builds' | 'damage';

type StoredRecord = {
  token: string;
  /** Unix seconds — token should not be used at or after this instant */
  expiresAt: number;
  dataType: AccessDataType;
};

function storageKey(dataType: AccessDataType): string {
  return `${STORAGE_PREFIX}-${dataType}`;
}

export function normalizeAccessDataType(value: unknown): AccessDataType {
  if (value === 'builds' || value === 'damage' || value === 'raids') {
    return value;
  }
  return 'raids';
}

export function readStoredAccessToken(
  dataType: AccessDataType
): { token: string; expiresAt: number } | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(storageKey(dataType));
    if (!raw) return null;
    const rec = JSON.parse(raw) as StoredRecord;
    if (!rec?.token || typeof rec.expiresAt !== 'number') {
      localStorage.removeItem(storageKey(dataType));
      return null;
    }
    if (rec.dataType !== dataType) {
      return null;
    }
    const now = Math.floor(Date.now() / 1000);
    if (now >= rec.expiresAt) {
      localStorage.removeItem(storageKey(dataType));
      return null;
    }
    return { token: rec.token, expiresAt: rec.expiresAt };
  } catch {
    return null;
  }
}

export function writeStoredAccessToken(
  dataType: AccessDataType,
  token: string,
  expiresAtUnix: number
): void {
  if (typeof localStorage === 'undefined') return;
  try {
    const rec: StoredRecord = {
      token,
      expiresAt: expiresAtUnix,
      dataType,
    };
    localStorage.setItem(storageKey(dataType), JSON.stringify(rec));
    notifyAuthStorageChanged();
  } catch {
    // Quota or privacy mode
  }
}

export function clearStoredAccessToken(dataType: AccessDataType): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.removeItem(storageKey(dataType));
    notifyAuthStorageChanged();
  } catch {
    /* ignore */
  }
}

/**
 * Prefer server-signed timestamp + max age; fall back to exchange expires_at or "now + max age".
 */
export async function persistAccessTokenFromExchange(response: {
  token: string;
  data_type?: string;
  expires_at?: number;
}): Promise<void> {
  const dataType = normalizeAccessDataType(response.data_type);
  let expiresAt =
    typeof response.expires_at === 'number'
      ? response.expires_at
      : Math.floor(Date.now() / 1000) + ACCESS_TOKEN_MAX_AGE_SEC;

  try {
    const v = await verifyToken(response.token);
    if (v.valid && v.payload && typeof v.payload.timestamp === 'number') {
      expiresAt = v.payload.timestamp + ACCESS_TOKEN_MAX_AGE_SEC;
    }
  } catch {
    expiresAt = Math.max(
      expiresAt,
      Math.floor(Date.now() / 1000) + ACCESS_TOKEN_MAX_AGE_SEC
    );
  }

  writeStoredAccessToken(dataType, response.token, expiresAt);
}
