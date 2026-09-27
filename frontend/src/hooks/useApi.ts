/**
 * Minimal data-fetching hook.
 *
 * Deliberately small — three states and a refetch — because the app has no
 * cross-page cache requirements yet. Swap for TanStack Query when it does.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: readonly unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // Keeps the latest fetcher without making it a dependency, so callers can
  // pass an inline arrow without triggering an infinite fetch loop.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Guards against setting state after unmount or after a newer request starts.
  const requestId = useRef(0);

  useEffect(() => {
    const current = ++requestId.current;
    setLoading(true);
    setError(null);

    fetcherRef
      .current()
      .then((result) => {
        if (current !== requestId.current) return;
        setData(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (current !== requestId.current) return;
        setData(null);
        setError(cause instanceof ApiError ? cause.message : "Unexpected error");
      })
      .finally(() => {
        if (current === requestId.current) setLoading(false);
      });

    return () => {
      // Invalidate this request if the component unmounts.
      requestId.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { data, error, loading, reload };
}
