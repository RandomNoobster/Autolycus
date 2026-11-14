import { useMediaQuery } from '@mantine/hooks';

/**
 * Below Mantine's `sm` breakpoint (768px). This is the exact query AppShell uses to collapse
 * the navbar, `em(768 - 0.1)`, so the app's mobile layout and AppShell's agree at 768px.
 */
export const MOBILE_MEDIA_QUERY = '(max-width: 47.99375em)';

/** True on phone-sized viewports. Read synchronously on first render to avoid a layout flash. */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_MEDIA_QUERY, false, { getInitialValueInEffect: false }) ?? false;
}
