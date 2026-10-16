import { useCallback, useRef } from "react";

/**
 * Lets a list page ignore responses that arrive out of order. Call start()
 * when a request is sent; apply its result only if the returned isLatest()
 * is still true. Otherwise a slow response for an old filter could replace
 * the rows for the filter now on screen.
 */
export function useRequestGuard() {
  const seq = useRef(0);
  return useCallback(() => {
    const id = ++seq.current;
    return () => id === seq.current;
  }, []);
}
