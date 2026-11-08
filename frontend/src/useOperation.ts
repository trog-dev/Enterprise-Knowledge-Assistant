import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface ScreenProps {
  token: string;
  onBusyChange: (value: boolean) => void;
  onSessionExpired: () => void;
}

export function useOperation(onBusyChange: ScreenProps["onBusyChange"], onSessionExpired: () => void) {
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const running = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; onBusyChange(false); };
  }, [onBusyChange]);

  const run = useCallback(async (label: string, action: () => Promise<void>) => {
    if (running.current) return;
    running.current = true;
    setError("");
    setPending(label);
    onBusyChange(true);
    try {
      await action();
    } catch (value) {
      if (value instanceof ApiError && value.status === 401) {
        onSessionExpired();
      } else if (mounted.current) {
        setError(value instanceof Error ? value.message : "Đã xảy ra lỗi.");
      }
    } finally {
      running.current = false;
      if (mounted.current) { setPending(""); onBusyChange(false); }
    }
  }, [onBusyChange, onSessionExpired]);

  return { pending, busy: pending !== "", error, setError, run };
}
