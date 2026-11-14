/**
 * The Discord account's linked P&W nation, shared through the query cache.
 */

import { useQuery } from '@tanstack/react-query';

import { getLinkedNation } from '@/api/auth';
import { isTransientApiError } from '@/api/errors';
import type { ApiError, LinkedNationResponse } from '@/types';

export const LINKED_NATION_QUERY_KEY = ['linkedNation'] as const;

/**
 * `data` is null when signed out (the API answers 401). Any other failure stays an error,
 * so an outage is not cached as "no nation linked".
 */
export function useLinkedNation() {
  return useQuery({
    queryKey: LINKED_NATION_QUERY_KEY,
    queryFn: async (): Promise<LinkedNationResponse | null> => {
      try {
        return await getLinkedNation();
      } catch (error) {
        if ((error as Partial<ApiError> | null)?.status === 401) return null;
        throw error;
      }
    },
    retry: (failureCount, error) => failureCount < 1 && isTransientApiError(error),
  });
}
