/**
 * Browser push helpers for beige reminders (service worker + Push API).
 *
 * Nothing here registers the service worker until the user turns notifications on for this
 * device (`subscribeThisDevice`). iPhone and iPad aren't supported for now.
 */

import type { PushDeviceRegisterRequest } from '@/types';

export type PushSupport = 'supported' | 'unsupported' | 'ios-unsupported';

export type NotificationPermissionState = NotificationPermission | 'unsupported';

const SERVICE_WORKER_URL = '/sw.js';
const SERVICE_WORKER_SCOPE = '/';
const SERVICE_WORKER_READY_TIMEOUT_MS = 20_000;

export type PushSetupErrorCode =
  | 'PUSH_UNSUPPORTED'
  | 'PUSH_IOS_UNSUPPORTED'
  | 'PUSH_PERMISSION_DENIED'
  | 'PUSH_PERMISSION_DISMISSED'
  | 'PUSH_KEY_INVALID'
  | 'PUSH_SUBSCRIBE_FAILED';

/** A push setup failure inside the browser. Shaped like `ApiError` so the same error handling applies. */
export class PushSetupError extends Error {
  readonly error = 'Browser notifications';
  readonly code: PushSetupErrorCode;

  constructor(code: PushSetupErrorCode, message: string) {
    super(message);
    this.name = 'PushSetupError';
    this.code = code;
  }
}

/** iPhone, iPod or iPad, including iPadOS (which reports a desktop Mac user agent). */
export function isAppleMobileDevice(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  if (/iPhone|iPad|iPod/i.test(ua)) return true;
  return /Macintosh/i.test(ua) && navigator.maxTouchPoints > 1;
}

/**
 * Whether this browser can receive reminder notifications. `unsupported` covers browsers without
 * the Push API, such as Discord's in-app browser and some private windows.
 */
export function getPushSupport(): PushSupport {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return 'unsupported';
  if (isAppleMobileDevice()) return 'ios-unsupported';
  if (
    !window.isSecureContext ||
    !('serviceWorker' in navigator) ||
    !('PushManager' in window) ||
    !('Notification' in window)
  ) {
    return 'unsupported';
  }
  return 'supported';
}

export function getNotificationPermission(): NotificationPermissionState {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
  return Notification.permission;
}

/** Decode a base64url VAPID public key into bytes for `applicationServerKey`. */
export function urlBase64ToUint8Array(base64Url: string): Uint8Array {
  const padding = '='.repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }
  return bytes;
}

/** Device id used by the API: the first 32 hex characters of SHA-256(endpoint). */
export async function endpointId(endpoint: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(endpoint));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 32);
}

export function sameDeviceId(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a.toLowerCase() === b.toLowerCase());
}

/**
 * Whether `subscription` was made with this server key. Returns true when the browser doesn't
 * expose the key, so a working subscription is never dropped on a guess.
 */
export function subscriptionUsesKey(subscription: PushSubscription, publicKey: string): boolean {
  const current = subscription.options?.applicationServerKey;
  if (!current) return true;
  let expected: Uint8Array;
  try {
    expected = urlBase64ToUint8Array(publicKey);
  } catch {
    return true;
  }
  const actual = new Uint8Array(current);
  return actual.length === expected.length && actual.every((byte, index) => byte === expected[index]);
}

/** This browser's push subscription, if any. Never registers a service worker. */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (getPushSupport() !== 'supported') return null;
  try {
    const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_SCOPE);
    return registration ? await registration.pushManager.getSubscription() : null;
  } catch {
    return null;
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('the service worker took too long to start')), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (reason: unknown) => {
        window.clearTimeout(timer);
        reject(reason);
      }
    );
  });
}

/**
 * Turn on push for this browser and return its subscription.
 *
 * Call it straight from a click handler: the permission prompt is requested before any other
 * await, because browsers only show it in response to a user gesture.
 */
export async function subscribeThisDevice(publicKey: string): Promise<PushSubscription> {
  const support = getPushSupport();
  if (support === 'ios-unsupported') {
    throw new PushSetupError(
      'PUSH_IOS_UNSUPPORTED',
      "Browser notifications aren't available on iPhone and iPad yet. Use Discord DMs."
    );
  }
  if (support === 'unsupported') {
    throw new PushSetupError(
      'PUSH_UNSUPPORTED',
      "This browser can't show notifications. Open Autolycus in your regular browser and try again."
    );
  }

  const permission = await Notification.requestPermission();
  if (permission === 'denied') {
    throw new PushSetupError(
      'PUSH_PERMISSION_DENIED',
      "Notifications are blocked for this site. Allow them in your browser's site settings, then try again."
    );
  }
  if (permission !== 'granted') {
    throw new PushSetupError(
      'PUSH_PERMISSION_DISMISSED',
      "Notifications weren't allowed. Click Enable on this device again and choose Allow."
    );
  }

  let applicationServerKey: Uint8Array;
  try {
    applicationServerKey = urlBase64ToUint8Array(publicKey);
  } catch {
    throw new PushSetupError(
      'PUSH_KEY_INVALID',
      "The server's notification key couldn't be read. Reload the page and try again."
    );
  }

  try {
    await navigator.serviceWorker.register(SERVICE_WORKER_URL, { scope: SERVICE_WORKER_SCOPE });
    const registration = await withTimeout(navigator.serviceWorker.ready, SERVICE_WORKER_READY_TIMEOUT_MS);
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      if (subscriptionUsesKey(existing, publicKey)) return existing;
      // Made with an old server key: it can't receive reminders and blocks subscribing with the new key.
      await existing.unsubscribe();
    }
    return await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
  } catch (err) {
    const detail = err instanceof Error && err.message ? ` (${err.message})` : '';
    const hint =
      'brave' in navigator
        ? ' In Brave, turn on "Use Google services for push messaging" in Settings → Privacy and security, then try again.'
        : ' Private windows and some privacy settings block notifications, so try a regular window.';
    throw new PushSetupError('PUSH_SUBSCRIBE_FAILED', `This browser couldn't turn on notifications${detail}.${hint}`);
  }
}

/** Remove this browser's local push subscription. Returns false when there was none. */
export async function unsubscribeThisDevice(): Promise<boolean> {
  const subscription = await getExistingSubscription();
  if (!subscription) return false;
  try {
    return await subscription.unsubscribe();
  } catch {
    return false;
  }
}

const BROWSER_NAMES: Array<[RegExp, string]> = [
  [/Edg(A|iOS)?\//, 'Edge'],
  [/OPR\/|Opera/, 'Opera'],
  [/SamsungBrowser\//, 'Samsung Internet'],
  [/Firefox\/|FxiOS\//, 'Firefox'],
  [/Chrome\/|CriOS\/|Chromium\//, 'Chrome'],
  [/Safari\//, 'Safari'],
];

const SYSTEM_NAMES: Array<[RegExp, string]> = [
  [/Android/, 'Android'],
  [/iPhone|iPad|iPod/, 'iOS'],
  [/Windows/, 'Windows'],
  [/CrOS/, 'ChromeOS'],
  [/Macintosh|Mac OS X/, 'macOS'],
  [/Linux/, 'Linux'],
];

/** Short label for this browser, e.g. "Chrome on Windows". */
export function describeThisDevice(): string {
  if (typeof navigator === 'undefined') return 'Browser';
  const ua = navigator.userAgent || '';
  const browser = BROWSER_NAMES.find(([pattern]) => pattern.test(ua))?.[1] ?? 'Browser';
  const system = SYSTEM_NAMES.find(([pattern]) => pattern.test(ua))?.[1];
  return system ? `${browser} on ${system}` : browser;
}

/** Request body for POST /api/push/subscriptions. */
export function toRegisterRequest(
  subscription: PushSubscription,
  options: { keyId?: string; enableChannel: boolean }
): PushDeviceRegisterRequest {
  const keys = subscription.toJSON().keys;
  if (!keys?.p256dh || !keys?.auth) {
    throw new PushSetupError(
      'PUSH_SUBSCRIBE_FAILED',
      "This browser's notification subscription is missing its encryption keys. Turn notifications off and on again on this device."
    );
  }
  return {
    endpoint: subscription.endpoint,
    keys: { p256dh: keys.p256dh, auth: keys.auth },
    ...(options.keyId ? { keyId: options.keyId } : {}),
    label: describeThisDevice(),
    enableChannel: options.enableChannel,
  };
}
