import { createContext, useContext } from 'react';

/** Whether the mobile AppShell navbar drawer is open. */
export const MobileNavOpenContext = createContext(false);

export function useMobileNavOpen(): boolean {
  return useContext(MobileNavOpenContext);
}
