export function formatErrorDetail(detail, fallback) {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item.trim();
        }
        if (item && typeof item === "object") {
          if (typeof item.msg === "string" && item.msg.trim()) {
            const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
            return location ? `${location}: ${item.msg.trim()}` : item.msg.trim();
          }
          return "";
        }
        return "";
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join("；");
    }
  }

  if (detail && typeof detail === "object") {
    if (typeof detail.msg === "string" && detail.msg.trim()) {
      return detail.msg.trim();
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }

  return fallback;
}

export function splitUsageSummary(summary, fallbackPercent) {
  if (summary == null) {
    return {
      percentLabel: "暂无数据",
      detailLabel: "暂无数据"
    };
  }

  const normalized = typeof summary === "string" ? summary.trim() : "";
  const [percentPart, detailPart] = normalized.split("·").map((item) => item?.trim() || "");

  return {
    percentLabel: percentPart || `${fallbackPercent}%`,
    detailLabel: detailPart || "-"
  };
}

export function formatCapacityInG(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return "0G";
  }

  const rounded = Math.round(numericValue * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}G` : `${rounded.toFixed(1)}G`;
}

export function splitProcessDisplay(processItem) {
  const normalized = typeof processItem === "string" ? processItem.trim() : "";
  const delimiterIndex = normalized.indexOf("/");
  const ownerPart = delimiterIndex >= 0 ? normalized.slice(0, delimiterIndex).trim() : "";
  const commandPart = delimiterIndex >= 0 ? normalized.slice(delimiterIndex + 1).trim() : normalized;

  return {
    owner: ownerPart || "未知用户",
    command: commandPart || normalized || "-"
  };
}

export function formatPortMappingSummary(portMapping) {
  const slotIndex = Number(portMapping?.slot_index);
  const publicPort = Number(portMapping?.public_port);
  const containerPort = Number(portMapping?.container_port);

  if (!Number.isInteger(slotIndex) || !Number.isInteger(publicPort) || !Number.isInteger(containerPort)) {
    return null;
  }

  return {
    id: `slot-${slotIndex}`,
    slotIndex,
    title: `端口${slotIndex}`,
    summary: `公网 ${publicPort} -> 容器 ${containerPort}`,
    publicPort,
    containerPort
  };
}

export function areIdSetsEqual(left, right) {
  const leftIds = [...new Set((left || []).map(Number))].sort((a, b) => a - b);
  const rightIds = [...new Set((right || []).map(Number))].sort((a, b) => a - b);

  if (leftIds.length !== rightIds.length) {
    return false;
  }

  return leftIds.every((value, index) => value === rightIds[index]);
}

export function enrichWorkspaceContainer(container) {
  const cpuRuntimeAvailable = container.cpu_runtime_available !== false;
  const memoryRuntimeAvailable = container.memory_runtime_available !== false;
  const gpuRuntimeAvailable = container.gpu_runtime_available !== false;
  const processRuntimeAvailable = container.process_runtime_available !== false;
  const connectedUsers = Array.isArray(container.connected_users)
    ? container.connected_users.filter(Boolean)
    : [];
  const gpuProcesses = Array.isArray(container.gpu_processes)
    ? container.gpu_processes.filter(Boolean)
    : [];
  const runtimeProcesses = Array.isArray(container.runtime_processes)
    ? container.runtime_processes
        .filter((item) => item && typeof item === "object")
        .map((item, index) => ({
          id: Number.isFinite(Number(item.pid))
            ? `${container.id}-pid-${Number(item.pid)}`
            : `${container.id}-process-${index}`,
          pid: Number.isFinite(Number(item.pid)) ? Number(item.pid) : null,
          owner: String(item.process_user || item.linux_username || "未知用户"),
          command: String(item.process_name || "").trim() || "-"
        }))
    : [];
  const portMappings = Array.isArray(container.port_mappings)
    ? container.port_mappings
        .map(formatPortMappingSummary)
        .filter(Boolean)
        .sort((left, right) => left.slotIndex - right.slotIndex)
    : [];
  const runtimeGpus = Array.isArray(container.runtime_gpus)
    ? container.runtime_gpus
        .map((gpuRow, index) => {
          const gpuIndex = Number.isFinite(Number(gpuRow?.gpu_index))
            ? Number(gpuRow.gpu_index)
            : index;
          const computePercent = Number.isFinite(Number(gpuRow?.compute_percent))
            ? Math.max(0, Math.min(100, Number(gpuRow.compute_percent)))
            : 0;
          const memoryPercent = Number.isFinite(Number(gpuRow?.memory_percent))
            ? Math.max(0, Math.min(100, Number(gpuRow.memory_percent)))
            : 0;
          const memoryUsedG = Number.isFinite(Number(gpuRow?.memory_used_g))
            ? Math.max(0, Number(gpuRow.memory_used_g))
            : 0;
          const memoryTotalG = Number.isFinite(Number(gpuRow?.memory_total_g))
            ? Math.max(0, Number(gpuRow.memory_total_g))
            : 0;

          return {
            id: `${container.id}-${gpuIndex}`,
            index: gpuIndex,
            title: `GPU ${gpuIndex}`,
            computePercent,
            computeLabel: `${computePercent}%`,
            memoryPercent,
            memoryLabel: `${memoryPercent}%`,
            memoryUsedG,
            memoryTotalG,
            memorySummary: `${formatCapacityInG(memoryUsedG)} / ${formatCapacityInG(memoryTotalG)}`
          };
        })
        .sort((left, right) => left.index - right.index)
    : [];
  const cpuUsagePercent = cpuRuntimeAvailable && Number.isFinite(Number(container.cpu_usage_percent))
    ? Math.max(0, Math.min(100, Number(container.cpu_usage_percent)))
    : 0;
  const memoryUsagePercent = memoryRuntimeAvailable && Number.isFinite(Number(container.memory_usage_percent))
    ? Math.max(0, Math.min(100, Number(container.memory_usage_percent)))
    : 0;
  const cpuUsageInfo = splitUsageSummary(container.cpu_usage_summary, cpuUsagePercent);
  const memoryUsageInfo = splitUsageSummary(container.memory_usage_summary, memoryUsagePercent);

  return {
    ...container,
    gpu: container.gpu_model && container.gpu_count ? `${container.gpu_model} x${container.gpu_count}` : "CPU容器",
    gpuName: container.gpu_model || "-",
    gpuMemory: container.gpu_memory || "-",
    gpuCount: container.gpu_count || "-",
    cpuCores: container.cpu_cores || "-",
    memorySize: container.memory_size || "-",
    connectedUsers,
    gpuProcesses,
    runtimeProcesses,
    portMappings,
    runtimeGpus,
    gpuRuntimeAvailable,
    processRuntimeAvailable,
    cpuRuntimeAvailable,
    memoryRuntimeAvailable,
    cpuUsagePercent,
    cpuUsageSummary: cpuUsageInfo.detailLabel,
    cpuUsageLabel: cpuUsageInfo.percentLabel,
    memoryUsagePercent,
    memoryUsageSummary: memoryUsageInfo.detailLabel,
    memoryUsageLabel: memoryUsageInfo.percentLabel,
    occupancy: `${container.active_user_count} / ${container.max_users}`,
    joinedKeyIds: container.joined_key_ids || []
  };
}
