"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";

export interface QueryState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useApi<T>(load: () => Promise<T>, key = "initial"): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loadRef.current());
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason
          : new ApiError("The dashboard could not load this data.", 0),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refresh);
  }, [key, refresh]);

  return { data, error, loading, refresh };
}
