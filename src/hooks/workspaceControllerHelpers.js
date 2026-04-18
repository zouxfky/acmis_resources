import { enrichWorkspaceContainer } from "../utils/formatters";

const CONTAINER_ACTION_COOLDOWN_MS = 5 * 60 * 1000;

export function buildContainerCooldownStorageKey(userId) {
  return `acmis:workspace-container-cooldowns:${userId}`;
}

export function pruneCooldownEntries(cooldowns, now = Date.now()) {
  return Object.fromEntries(
    Object.entries(cooldowns || {}).filter(([, expiresAt]) => Number(expiresAt) > now)
  );
}

export function readContainerCooldowns(userId) {
  if (!userId || typeof window === "undefined") {
    return {};
  }

  try {
    const stored = window.localStorage.getItem(buildContainerCooldownStorageKey(userId));
    if (!stored) {
      return {};
    }
    const parsed = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return pruneCooldownEntries(parsed);
  } catch {
    return {};
  }
}

export function writeContainerCooldowns(userId, cooldowns) {
  if (!userId || typeof window === "undefined") {
    return;
  }

  const nextCooldowns = pruneCooldownEntries(cooldowns);
  const storageKey = buildContainerCooldownStorageKey(userId);

  if (Object.keys(nextCooldowns).length === 0) {
    window.localStorage.removeItem(storageKey);
    return;
  }

  window.localStorage.setItem(storageKey, JSON.stringify(nextCooldowns));
}

export function formatCooldownLabel(remainingMs) {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function getCooldownExpiryTimestamp(now = Date.now()) {
  return now + CONTAINER_ACTION_COOLDOWN_MS;
}

export function mapWorkspaceSshKeys(sshKeyItems) {
  return (sshKeyItems || []).map((item) => ({
    id: item.id,
    label: item.key_name,
    value: item.public_key,
    fingerprint: item.fingerprint
  }));
}

export function mapWorkspaceContainers(containerItems) {
  return (containerItems || []).map(enrichWorkspaceContainer);
}

export function decorateWorkspaceContainers(containerItems, cooldowns, now) {
  return containerItems.map((item) => {
    const expiresAt = Number(cooldowns[String(item.id)]) || 0;
    const actionCooldownRemainingMs = Math.max(0, expiresAt - now);
    return {
      ...item,
      actionCooldownActive: actionCooldownRemainingMs > 0,
      actionCooldownRemainingMs,
      actionCooldownLabel:
        actionCooldownRemainingMs > 0 ? formatCooldownLabel(actionCooldownRemainingMs) : ""
    };
  });
}
