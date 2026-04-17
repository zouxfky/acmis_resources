import { useEffect, useRef, useState } from "react";

const LEADER_HEARTBEAT_MS = 4000;
const LEADER_STALE_MS = 12000;

function readLeaderState(storageKey) {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(storageKey);
    if (!rawValue) {
      return null;
    }
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeLeaderState(storageKey, tabId) {
  if (typeof window === "undefined") {
    return null;
  }

  const nextState = {
    tabId,
    expiresAt: Date.now() + LEADER_STALE_MS
  };
  window.localStorage.setItem(storageKey, JSON.stringify(nextState));
  return nextState;
}

function clearLeaderState(storageKey, tabId) {
  if (typeof window === "undefined") {
    return;
  }

  const currentState = readLeaderState(storageKey);
  if (currentState?.tabId === tabId) {
    window.localStorage.removeItem(storageKey);
  }
}

export function usePollingLeader({ enabled, scopeKey }) {
  const tabIdRef = useRef(
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `tab-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
  const [isPollingLeader, setIsPollingLeader] = useState(false);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      setIsPollingLeader(false);
      return undefined;
    }

    const storageKey = `acmis:polling-leader:${scopeKey}`;
    const tabId = tabIdRef.current;

    function refreshLeaderState() {
      if (document.visibilityState !== "visible") {
        clearLeaderState(storageKey, tabId);
        setIsPollingLeader(false);
        return;
      }

      const currentState = readLeaderState(storageKey);
      const isCurrentLeader = currentState?.tabId === tabId;
      const isStale = !currentState || Number(currentState.expiresAt) <= Date.now();

      if (isCurrentLeader || isStale) {
        writeLeaderState(storageKey, tabId);
        setIsPollingLeader(true);
        return;
      }

      setIsPollingLeader(false);
    }

    function handleStorage(event) {
      if (event.key === storageKey) {
        refreshLeaderState();
      }
    }

    function handleVisibilityChange() {
      refreshLeaderState();
    }

    function handlePageHide() {
      clearLeaderState(storageKey, tabId);
    }

    refreshLeaderState();

    const heartbeatId = window.setInterval(() => {
      refreshLeaderState();
    }, LEADER_HEARTBEAT_MS);

    window.addEventListener("storage", handleStorage);
    window.addEventListener("pagehide", handlePageHide);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(heartbeatId);
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("pagehide", handlePageHide);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      clearLeaderState(storageKey, tabId);
      setIsPollingLeader(false);
    };
  }, [enabled, scopeKey]);

  return { isPollingLeader };
}
