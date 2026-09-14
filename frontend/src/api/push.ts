/**
 * Browser push API functions (requires Discord session).
 */

import { apiDelete, apiGet, apiPost } from './client';
import type {
  PushDeviceRegisterRequest,
  PushDeviceRegisterResponse,
  PushDeviceRemoveResponse,
  PushDevicesResponse,
  PushTestResponse,
  PushVapidKeyResponse,
} from '@/types';

/** The server's VAPID public key (base64url). 503 PUSH_NOT_CONFIGURED when the server has no push keys. */
export function fetchPushVapidPublicKey(): Promise<PushVapidKeyResponse> {
  return apiGet<PushVapidKeyResponse>('/api/push/vapid-public-key');
}

/** Devices registered for reminder notifications. */
export function fetchPushDevices(): Promise<PushDevicesResponse> {
  return apiGet<PushDevicesResponse>('/api/push/subscriptions');
}

/**
 * Register (or refresh) a browser push subscription.
 * 400 INVALID_SUBSCRIPTION, 409 DEVICE_LIMIT (max 10), 503 PUSH_NOT_CONFIGURED.
 */
export function registerPushDevice(
  data: PushDeviceRegisterRequest
): Promise<PushDeviceRegisterResponse> {
  return apiPost<PushDeviceRegisterResponse, PushDeviceRegisterRequest>('/api/push/subscriptions', data);
}

/** Remove a device by id (first 32 hex chars of SHA-256 of its endpoint). */
export function removePushDevice(deviceId: string): Promise<PushDeviceRemoveResponse> {
  return apiDelete<PushDeviceRemoveResponse>(`/api/push/subscriptions/${encodeURIComponent(deviceId)}`);
}

/** Send a test notification to every registered device. 409 NO_PUSH_DEVICES, 429 RATE_LIMITED. */
export function sendTestPush(): Promise<PushTestResponse> {
  return apiPost<PushTestResponse, Record<string, never>>('/api/push/test', {});
}
