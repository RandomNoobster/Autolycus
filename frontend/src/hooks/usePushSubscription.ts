/**
 * Browser push on this device for beige reminders: support, permission, subscription state,
 * and the enable / turn off / remove / test actions.
 */

import { useEffect, useRef, useState } from 'react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import {
  fetchPushDevices,
  fetchPushVapidPublicKey,
  registerPushDevice,
  removePushDevice,
  sendTestPush,
} from '@/api';
import { toApiError } from '@/api/errors';
import {
  endpointId,
  getExistingSubscription,
  getNotificationPermission,
  getPushSupport,
  sameDeviceId,
  subscribeThisDevice,
  subscriptionUsesKey,
  toRegisterRequest,
  type NotificationPermissionState,
  type PushSupport,
} from '@/lib/push';
import {
  PUSH_DEVICES_QUERY_KEY,
  PUSH_VAPID_KEY_QUERY_KEY,
  REMINDERS_QUERY_KEY,
  REMINDER_DELIVERY_QUERY_KEY,
  plural,
  pushErrorMessage,
} from '@/lib/reminderDelivery';
import type { PushDevice, PushDevicesResponse, ReminderDelivery } from '@/types';

interface LocalSubscription {
  /** False until this browser has been checked for an existing subscription. */
  checked: boolean;
  subscription: PushSubscription | null;
  /** Endpoint id of `subscription` (same format as `PushDevice.id`). */
  id: string | null;
}

export interface UsePushSubscriptionOptions {
  /** Only call the API when signed in with Discord. Default true. */
  enabled?: boolean;
}

function upsertDevice(queryClient: QueryClient, device: PushDevice) {
  queryClient.setQueryData<PushDevicesResponse>(PUSH_DEVICES_QUERY_KEY, (old) => {
    if (!old) return old;
    const known = old.devices.some((d) => sameDeviceId(d.id, device.id));
    return {
      ...old,
      devices: known
        ? old.devices.map((d) => (sameDeviceId(d.id, device.id) ? device : d))
        : [device, ...old.devices],
    };
  });
}

function dropDevice(queryClient: QueryClient, deviceId: string) {
  queryClient.setQueryData<PushDevicesResponse>(PUSH_DEVICES_QUERY_KEY, (old) =>
    old ? { ...old, devices: old.devices.filter((d) => !sameDeviceId(d.id, deviceId)) } : old
  );
}

function refreshAfterChange(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: REMINDERS_QUERY_KEY });
  void queryClient.invalidateQueries({ queryKey: PUSH_DEVICES_QUERY_KEY });
}

export function usePushSubscription({ enabled = true }: UsePushSubscriptionOptions = {}) {
  const queryClient = useQueryClient();
  const [support] = useState<PushSupport>(getPushSupport);
  const [permission, setPermission] = useState<NotificationPermissionState>(getNotificationPermission);
  const [local, setLocal] = useState<LocalSubscription>({ checked: false, subscription: null, id: null });
  /** True once this visit has refreshed or dropped the existing subscription, or the user changed it. */
  const syncedRef = useRef(false);
  const canUsePush = enabled && support === 'supported';

  const devicesQuery = useQuery({
    queryKey: PUSH_DEVICES_QUERY_KEY,
    queryFn: fetchPushDevices,
    enabled,
    retry: false,
    staleTime: 30_000,
  });

  // Loaded ahead of time so "Enable on this device" can ask for permission without a network wait first.
  const vapidKeyQuery = useQuery({
    queryKey: PUSH_VAPID_KEY_QUERY_KEY,
    queryFn: fetchPushVapidPublicKey,
    enabled: canUsePush,
    retry: false,
    staleTime: Infinity,
  });

  // Keep the permission current when it changes in the browser's site settings.
  useEffect(() => {
    if (support !== 'supported') return;
    const refresh = () => setPermission(getNotificationPermission());
    window.addEventListener('focus', refresh);
    let status: PermissionStatus | null = null;
    let active = true;
    try {
      navigator.permissions
        ?.query({ name: 'notifications' })
        .then((result) => {
          if (!active) return;
          status = result;
          result.addEventListener('change', refresh);
        })
        .catch(() => undefined);
    } catch {
      // Some browsers throw for unsupported permission names; the focus listener still covers changes.
    }
    return () => {
      active = false;
      window.removeEventListener('focus', refresh);
      status?.removeEventListener('change', refresh);
    };
  }, [support]);

  // Look for a subscription this browser already has. Never registers the service worker.
  useEffect(() => {
    if (!canUsePush) return;
    let active = true;
    void (async () => {
      const subscription = await getExistingSubscription();
      const id = subscription ? await endpointId(subscription.endpoint).catch(() => null) : null;
      if (!active || syncedRef.current) return;
      setLocal({ checked: true, subscription: id ? subscription : null, id });
    })();
    return () => {
      active = false;
    };
  }, [canUsePush]);

  const serverKey = vapidKeyQuery.data;
  const devices = devicesQuery.data?.devices;
  const devicesFetching = devicesQuery.isFetching;

  // Once per visit: drop a subscription made with an old server key, or refresh lastSeenAt for a listed one.
  useEffect(() => {
    if (syncedRef.current || !local.subscription || !local.id) return;
    if (!serverKey || !devices || devicesFetching) return;
    syncedRef.current = true;
    const subscription = local.subscription;
    const id = local.id;
    void (async () => {
      if (!subscriptionUsesKey(subscription, serverKey.publicKey)) {
        await subscription.unsubscribe().catch(() => false);
        setLocal({ checked: true, subscription: null, id: null });
        return;
      }
      // A device removed from another browser stays removed: only refresh devices the server still lists.
      if (!devices.some((device) => sameDeviceId(device.id, id))) return;
      try {
        const res = await registerPushDevice(
          toRegisterRequest(subscription, { keyId: serverKey.keyId, enableChannel: false })
        );
        queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, res.delivery);
        upsertDevice(queryClient, res.device);
      } catch {
        // Best-effort: the device just keeps an older lastSeenAt.
      }
    })();
  }, [local, serverKey, devices, devicesFetching, queryClient]);

  const enableMutation = useMutation({
    mutationFn: async (pendingSubscription: Promise<PushSubscription>) => {
      const subscription = await pendingSubscription;
      const request = toRegisterRequest(subscription, {
        keyId: vapidKeyQuery.data?.keyId,
        enableChannel: true,
      });
      const id = await endpointId(subscription.endpoint);
      try {
        const res = await registerPushDevice(request);
        return { device: res.device, delivery: res.delivery, subscription, id };
      } catch (err) {
        // The server didn't take it, so don't leave a subscription behind that nothing sends to.
        await subscription.unsubscribe().catch(() => false);
        throw err;
      }
    },
    onSuccess: ({ device, delivery, subscription, id }) => {
      syncedRef.current = true;
      setLocal({ checked: true, subscription, id });
      queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, delivery);
      upsertDevice(queryClient, device);
      refreshAfterChange(queryClient);
      notifications.show({
        title: 'Notifications on for this device',
        message: 'Reminders will show up here as browser notifications. Send a test push to check.',
        color: 'green',
      });
    },
    onError: (error) => {
      const apiError = toApiError(error);
      notifications.show({
        title: "Couldn't turn on notifications",
        message: pushErrorMessage(apiError),
        color: apiError.code.startsWith('PUSH_PERMISSION') ? 'yellow' : 'red',
      });
    },
    onSettled: () => setPermission(getNotificationPermission()),
  });

  const removeMutation = useMutation({
    mutationFn: async (deviceId: string) => {
      const previous = queryClient.getQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY);
      const isThisDevice = sameDeviceId(local.id, deviceId);
      const res = await removePushDevice(deviceId);
      if (isThisDevice && local.subscription) {
        await local.subscription.unsubscribe().catch(() => false);
      }
      return { delivery: res.delivery, deviceId, isThisDevice, previous };
    },
    onSuccess: ({ delivery, deviceId, isThisDevice, previous }) => {
      if (isThisDevice) {
        syncedRef.current = true;
        setLocal({ checked: true, subscription: null, id: null });
      }
      queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, delivery);
      dropDevice(queryClient, deviceId);
      refreshAfterChange(queryClient);
      const pushSwitchedOff = Boolean(previous?.channels.webPush && !delivery.channels.webPush);
      const dmSwitchedOn = Boolean(previous && !previous.channels.discordDm && delivery.channels.discordDm);
      notifications.show({
        title: isThisDevice ? 'Notifications off for this device' : 'Device removed',
        message: dmSwitchedOn
          ? 'No devices are left, so browser notifications are off and reminders will come by Discord DM.'
          : pushSwitchedOff
            ? 'No devices are left, so browser notifications are off.'
            : isThisDevice
              ? "This browser won't show reminder notifications any more."
              : "That device won't get reminder notifications any more.",
        color: dmSwitchedOn ? 'yellow' : 'blue',
      });
    },
    onError: (error) => {
      notifications.show({
        title: "Couldn't remove the device",
        message: pushErrorMessage(toApiError(error)),
        color: 'red',
      });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => sendTestPush(),
    onSuccess: ({ sent, failed, removed }) => {
      void queryClient.invalidateQueries({ queryKey: PUSH_DEVICES_QUERY_KEY });
      if (removed > 0) void queryClient.invalidateQueries({ queryKey: REMINDERS_QUERY_KEY });
      const removedNote =
        removed > 0
          ? ` ${plural(removed, 'device')} no longer accepted notifications and ${removed === 1 ? 'was' : 'were'} removed.`
          : '';
      if (sent > 0 && failed === 0) {
        notifications.show({
          title: 'Test notification sent',
          message: `Sent to ${plural(sent, 'device')}. It should appear within a few seconds.${removedNote}`,
          color: 'green',
        });
      } else if (sent > 0) {
        notifications.show({
          title: 'Test notification partly sent',
          message: `Sent to ${plural(sent, 'device')}, but ${plural(failed, 'device')} couldn't be reached.${removedNote}`,
          color: 'yellow',
        });
      } else {
        notifications.show({
          title: 'Test notification not delivered',
          message: `None of your devices could be reached.${removedNote} Turn notifications on again on the devices you use.`,
          color: 'red',
        });
      }
    },
    onError: (error) => {
      notifications.show({
        title: "Couldn't send a test notification",
        message: pushErrorMessage(toApiError(error)),
        color: 'red',
      });
    },
  });

  const { mutate: mutateEnable } = enableMutation;
  const { mutate: mutateRemove } = removeMutation;
  const { mutate: mutateTest } = testMutation;

  /** Call directly from a click handler: the permission prompt must be requested before any other await. */
  const enableThisDevice = () => {
    const publicKey = vapidKeyQuery.data?.publicKey;
    if (!publicKey) {
      notifications.show({
        title: "Couldn't turn on notifications",
        message: "Notification settings haven't loaded from the server yet. Wait a moment or reload the page, then try again.",
        color: 'red',
      });
      return;
    }
    const pendingSubscription = subscribeThisDevice(publicKey);
    // The mutation reports failures; this only stops an "unhandled rejection" before it awaits.
    pendingSubscription.catch(() => undefined);
    mutateEnable(pendingSubscription);
  };

  const deviceList = devicesQuery.data?.devices ?? [];
  const thisDeviceId =
    local.id && deviceList.some((device) => sameDeviceId(device.id, local.id)) ? local.id : null;

  return {
    support,
    permission,
    devices: deviceList,
    devicesLoading: devicesQuery.isLoading,
    devicesError: devicesQuery.error ? toApiError(devicesQuery.error) : null,
    keyReady: Boolean(vapidKeyQuery.data?.publicKey),
    keyError: vapidKeyQuery.error ? toApiError(vapidKeyQuery.error) : null,
    /** True while checking whether this browser already has a subscription. */
    checkingThisDevice: canUsePush && !local.checked,
    /** Id of this browser's device when the server lists it. */
    thisDeviceId,
    isThisDeviceEnabled: thisDeviceId !== null,
    enableThisDevice,
    disableThisDevice: () => {
      if (thisDeviceId) mutateRemove(thisDeviceId);
    },
    removeDevice: (deviceId: string) => mutateRemove(deviceId),
    sendTest: () => mutateTest(),
    enabling: enableMutation.isPending,
    removingDeviceId: removeMutation.isPending ? (removeMutation.variables ?? null) : null,
    testing: testMutation.isPending,
  };
}

export type PushSubscriptionController = ReturnType<typeof usePushSubscription>;
