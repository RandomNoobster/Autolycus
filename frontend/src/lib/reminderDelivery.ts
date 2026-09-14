/**
 * Shared query keys, formatting and user-facing copy for reminder delivery
 * (Discord DM + browser push).
 */

import type {
  ApiError,
  DmDeliveryState,
  DmFailureReason,
  ReminderDelivery,
  ReminderProblem,
} from '@/types';

export const REMINDERS_QUERY_KEY = ['reminders'] as const;
export const REMINDER_DELIVERY_QUERY_KEY = ['reminders', 'delivery'] as const;
export const PUSH_DEVICES_QUERY_KEY = ['push', 'subscriptions'] as const;
export const PUSH_VAPID_KEY_QUERY_KEY = ['push', 'vapid-key'] as const;

const TEST_DM_ACTIVE_POLL_MS = 2_500;
const TEST_DM_SENT_POLL_MS = 10_000;
const TEST_DM_SENT_POLL_WINDOW_MS = 10 * 60_000;

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Polling for the delivery query: quick while a test DM is being sent, slower while we wait for
 * "Got it" on a recent one, otherwise off.
 */
export function deliveryPollInterval(
  delivery: ReminderDelivery | undefined,
  now: number = Date.now()
): number | false {
  const test = delivery?.latestTestDm;
  if (!test) return false;
  if (test.state === 'queued' || test.state === 'sending') return TEST_DM_ACTIVE_POLL_MS;
  if (test.state === 'sent') {
    const requestedAt = toMs(test.requestedAt);
    if (requestedAt !== null && now - requestedAt < TEST_DM_SENT_POLL_WINDOW_MS) return TEST_DM_SENT_POLL_MS;
  }
  return false;
}

export function isTestDmInFlight(delivery: ReminderDelivery | undefined): boolean {
  const state = delivery?.latestTestDm?.state;
  return state === 'queued' || state === 'sending' || delivery?.dm.state === 'pending';
}

const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

/** e.g. "5 minutes ago", "in 2 hours", "now". Empty string for a missing or invalid time. */
export function formatRelativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  const ms = toMs(iso);
  if (ms === null) return '';
  const seconds = Math.round((ms - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 10) return relativeTimeFormatter.format(0, 'second');
  if (abs < 60) return relativeTimeFormatter.format(seconds, 'second');
  if (abs < 90 * 60) return relativeTimeFormatter.format(Math.round(seconds / 60), 'minute');
  if (abs < 36 * 3600) return relativeTimeFormatter.format(Math.round(seconds / 3600), 'hour');
  return relativeTimeFormatter.format(Math.round(seconds / 86_400), 'day');
}

/** Local date and time, e.g. "Sep 14, 2026, 6:45 PM". */
export function formatLocalDateTime(iso: string | null | undefined): string {
  const ms = toMs(iso);
  return ms === null ? '' : dateTimeFormatter.format(ms);
}

/** Local date, e.g. "Sep 14, 2026". */
export function formatLocalDate(iso: string | null | undefined): string {
  const ms = toMs(iso);
  return ms === null ? '' : dateFormatter.format(ms);
}

/** Whether time `a` is later than time `b` (missing times count as never). */
export function isLater(a: string | null | undefined, b: string | null | undefined): boolean {
  const aMs = toMs(a);
  if (aMs === null) return false;
  const bMs = toMs(b);
  return bMs === null || aMs > bMs;
}

export function plural(count: number, singular: string, pluralForm: string = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/** e.g. "45 seconds", "3 minutes", "5 hours" */
export function formatWait(seconds: number): string {
  if (seconds < 60) return plural(Math.max(1, Math.ceil(seconds)), 'second');
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return plural(minutes, 'minute');
  return plural(Math.ceil(minutes / 60), 'hour');
}

export const DM_STATE_BADGES: Record<DmDeliveryState, { label: string; color: string }> = {
  unknown: { label: 'Not checked yet', color: 'gray' },
  pending: { label: 'Checking…', color: 'blue' },
  ok: { label: 'Delivered', color: 'green' },
  confirmed: { label: 'Confirmed', color: 'teal' },
  failed: { label: 'Not delivered', color: 'red' },
};

export function dmFailureReasonText(reason: DmFailureReason | null): string {
  switch (reason) {
    case 'no_mutual_server':
      return "You don't share a server with Autolycus, so Discord won't let it DM you.";
    case 'dms_closed':
      return 'Your Discord privacy settings block DMs from Autolycus, or you have blocked it.';
    case 'unknown_user':
      return "Discord couldn't find your account. Log out, then log in with Discord again.";
    default:
      return 'Discord refused the DM.';
  }
}

/** One line per recent delivery problem. */
export function describeProblem(problem: ReminderProblem): string {
  const nation = problem.nationName?.trim() || `Nation ${problem.nationId}`;
  const removed = problem.reminderRemoved ? ' — reminder removed' : '';
  switch (problem.kind) {
    case 'not_delivered': {
      const which =
        problem.offsetMinutes != null ? `the ${problem.offsetMinutes}-minute reminder` : 'a reminder';
      return `Couldn't deliver ${which} for ${nation}${removed}`;
    }
    case 'dm_refused':
      return `Discord refused the DM for ${nation}; push delivered it`;
    case 'push_failed':
      return `Push failed for ${nation}; the DM delivered it`;
    case 'not_protected':
      return `${nation} wasn't in beige or vacation mode${removed}`;
    case 'nation_missing':
      return `${nation} no longer exists${removed}`;
    default:
      return `Something went wrong with a reminder for ${nation}${removed}`;
  }
}

/** PUT /api/raids/reminders/channels errors. */
export function channelErrorMessage(error: ApiError): string {
  switch (error.code) {
    case 'CHANNEL_REQUIRED':
      return 'Keep at least one delivery method on. Turn the other one on first, then try again.';
    case 'NO_PUSH_DEVICES':
      return 'Turn on notifications on at least one device before switching browser notifications on.';
    case 'PUSH_NOT_CONFIGURED':
      return "Browser notifications aren't set up on this server. Use Discord DMs instead.";
    default:
      return error.message || "Couldn't save your delivery settings. Try again.";
  }
}

/** POST /api/raids/reminders/test-dm errors. */
export function testDmErrorMessage(error: ApiError): string {
  if (error.code === 'RATE_LIMITED') {
    return error.retryAfterSeconds !== undefined
      ? `You've sent test DMs recently. You can send another in ${formatWait(error.retryAfterSeconds)}.`
      : "You've sent test DMs recently. You can send 1 per minute and 10 per day, so wait a minute and try again.";
  }
  return error.message || "Couldn't send a test DM. Try again.";
}

/** Browser push errors, from the API or from the browser (PushSetupError). */
export function pushErrorMessage(error: ApiError): string {
  switch (error.code) {
    case 'DEVICE_LIMIT':
      return 'You already have 10 devices with notifications on. Remove one you no longer use, then try again.';
    case 'INVALID_SUBSCRIPTION':
      return "The server didn't accept this browser's notification subscription. Reload the page and try again.";
    case 'NO_PUSH_DEVICES':
      return 'No device has notifications on yet. Click Enable on this device first.';
    case 'PUSH_NOT_CONFIGURED':
      return "Browser notifications aren't set up on this server. Use Discord DMs instead.";
    case 'RATE_LIMITED':
      return error.retryAfterSeconds !== undefined
        ? `You've sent test notifications recently. Try again in ${formatWait(error.retryAfterSeconds)}.`
        : "You've sent test notifications recently. Wait a minute, then try again.";
    default:
      return error.message || 'Something went wrong with browser notifications. Try again.';
  }
}
