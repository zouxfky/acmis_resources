import { useEffect, useRef, useState } from "react";

const containerStatusLabelMap = {
  active: "在线",
  offline: "离线",
  disabled: "停用"
};

const containerStatusClassMap = {
  active: "is-active",
  offline: "is-offline",
  disabled: "is-disabled"
};

const COLLAPSED_CARD_HEIGHT = 600;
const CARD_AUTO_COLLAPSE_DELAY_MS = 60_000;

export function WorkspaceContainerCard({
  container,
  sshKeys,
  workspaceLoading,
  cardExpanded,
  onToggleCardExpand,
  onSetCardExpanded,
  onOpenJoinDialog,
  onOpenLeaveDialog
}) {
  const cardBodyRef = useRef(null);
  const autoCollapseTimeoutRef = useRef(null);
  const [cardCollapsible, setCardCollapsible] = useState(false);
  const isJoined = container.joinedKeyIds.length > 0;
  const isContainerActive = container.status === "active";
  const isContainerFull = Number(container.active_user_count) >= Number(container.max_users);
  const hasAvailableJoinKeys = sshKeys.some((item) => !(container.joinedKeyIds || []).includes(item.id));
  const isCooldownActive = container.actionCooldownActive;
  const cooldownLabel = container.actionCooldownLabel;
  const joinDisabled =
    workspaceLoading ||
    isCooldownActive ||
    !isContainerActive ||
    isContainerFull ||
    !hasAvailableJoinKeys;
  const leaveDisabled = workspaceLoading || isCooldownActive || !isJoined;
  const joinButtonLabel = isCooldownActive
    ? `冷却中 ${cooldownLabel}`
    : !isContainerActive
      ? container.status === "disabled"
        ? "容器停用"
        : "容器离线"
      : "加入容器";
  const leaveButtonLabel = isCooldownActive ? `冷却中 ${cooldownLabel}` : "退出容器";
  const statusLabel = containerStatusLabelMap[container.status] || container.status || "未知";
  const statusClassName = containerStatusClassMap[container.status] || "";

  function clearAutoCollapseTimeout() {
    if (autoCollapseTimeoutRef.current) {
      window.clearTimeout(autoCollapseTimeoutRef.current);
      autoCollapseTimeoutRef.current = null;
    }
  }

  function handleCardMouseEnter() {
    clearAutoCollapseTimeout();
  }

  function handleCardMouseLeave() {
    clearAutoCollapseTimeout();
    if (!cardExpanded) {
      return;
    }

    autoCollapseTimeoutRef.current = window.setTimeout(() => {
      onSetCardExpanded(container.id, false);
      autoCollapseTimeoutRef.current = null;
    }, CARD_AUTO_COLLAPSE_DELAY_MS);
  }

  useEffect(() => {
    if (cardExpanded) {
      return undefined;
    }

    function updateCollapsibleState() {
      const cardBodyElement = cardBodyRef.current;
      if (!cardBodyElement) {
        setCardCollapsible(false);
        return;
      }

      const nextCollapsible = cardBodyElement.scrollHeight > cardBodyElement.clientHeight + 1;

      setCardCollapsible((current) => (current === nextCollapsible ? current : nextCollapsible));
    }

    updateCollapsibleState();

    const cardBodyElement = cardBodyRef.current;
    const resizeObserver =
      typeof ResizeObserver !== "undefined" && cardBodyElement
        ? new ResizeObserver(() => {
            if (!cardExpanded) {
              updateCollapsibleState();
            }
          })
        : null;

    if (resizeObserver && cardBodyElement) {
      resizeObserver.observe(cardBodyElement);
    }

    function handleWindowResize() {
      if (!cardExpanded) {
        updateCollapsibleState();
      }
    }

    window.addEventListener("resize", handleWindowResize);

    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", handleWindowResize);
    };
  }, [container, cardExpanded]);

  useEffect(() => {
    if (!cardExpanded) {
      clearAutoCollapseTimeout();
    }

    return () => {
      clearAutoCollapseTimeout();
    };
  }, [cardExpanded]);

  return (
    <article
      className={`container-card${isJoined ? " is-joined" : ""}${container.status === "active" ? " is-active" : ""}${container.status === "offline" ? " is-offline" : ""}${container.status === "disabled" ? " is-disabled" : ""}${cardExpanded ? " is-expanded" : ""}${cardCollapsible ? " is-collapsible" : ""}`}
      key={container.id}
      onMouseEnter={handleCardMouseEnter}
      onMouseLeave={handleCardMouseLeave}
      style={{ "--container-card-collapsed-height": `${COLLAPSED_CARD_HEIGHT}px` }}
    >
      <div className="container-card-head">
        <div>
          <div className="container-title-row">
            <strong className="container-name">{container.name}</strong>
            <span className={`status-pill container-status-pill ${statusClassName}`}>{statusLabel}</span>
            {isJoined ? <span className="container-joined-flag">已加入</span> : null}
          </div>
          <span className="container-subtitle">{container.gpu}</span>
        </div>
        <div className="container-card-badges">
          <div className="container-occupancy-wrap">
            <button
              className="container-occupancy"
              type="button"
              aria-label={`${container.name} 当前占用 ${container.occupancy}`}
            >
              {container.occupancy}
            </button>
            <div className="container-occupancy-popover">
              <span className="container-occupancy-title">当前用户</span>
              {container.connectedUsers.length > 0 ? (
                <div className="container-occupancy-user-list">
                  {container.connectedUsers.map((userName) => (
                    <span className="container-user-chip" key={`${container.id}-${userName}`}>
                      {userName}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="container-runtime-empty">当前暂无用户连接</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="container-card-body" ref={cardBodyRef}>
        <div className="container-runtime">
          <div className="container-runtime-block">
            <div className="container-runtime-heading">
              <span className="container-runtime-label">资源使用情况</span>
              <strong>{container.runtimeGpus.length} 张卡</strong>
            </div>
            <div className="system-runtime-grid">
              <div className="system-runtime-card">
                <div className="system-runtime-head">
                  <strong>CPU</strong>
                  {container.cpuRuntimeAvailable ? <span>{container.cpuUsageSummary}</span> : null}
                </div>
                {container.cpuRuntimeAvailable ? (
                  <div className="gpu-runtime-stat system-runtime-stat">
                    <div className="gpu-runtime-bar system-runtime-bar">
                      <span style={{ width: `${container.cpuUsagePercent}%` }} />
                    </div>
                    <strong className="gpu-runtime-percent">{container.cpuUsageLabel}</strong>
                  </div>
                ) : (
                  <p className="container-runtime-empty">当前暂无数据</p>
                )}
              </div>
              <div className="system-runtime-card">
                <div className="system-runtime-head">
                  <strong>内存</strong>
                  {container.memoryRuntimeAvailable ? <span>{container.memoryUsageSummary}</span> : null}
                </div>
                {container.memoryRuntimeAvailable ? (
                  <div className="gpu-runtime-stat system-runtime-stat">
                    <div className="gpu-runtime-bar system-runtime-bar is-memory">
                      <span style={{ width: `${container.memoryUsagePercent}%` }} />
                    </div>
                    <strong className="gpu-runtime-percent">{container.memoryUsageLabel}</strong>
                  </div>
                ) : (
                  <p className="container-runtime-empty">当前暂无数据</p>
                )}
              </div>
            </div>
            {container.gpuRuntimeAvailable && container.runtimeGpus.length > 0 ? (
              <div className="gpu-runtime-grid">
                {container.runtimeGpus.map((gpuItem) => (
                  <div className="gpu-runtime-card" key={gpuItem.id}>
                    <div className="gpu-runtime-head">
                      <strong>{gpuItem.title}</strong>
                      <span>{gpuItem.memorySummary}</span>
                    </div>
                    <div className="gpu-runtime-stat">
                      <span className="gpu-runtime-name">利用率</span>
                      <div className="gpu-runtime-bar">
                        <span style={{ width: `${gpuItem.computePercent}%` }} />
                      </div>
                      <strong className="gpu-runtime-percent">{gpuItem.computeLabel}</strong>
                    </div>
                    <div className="gpu-runtime-stat">
                      <span className="gpu-runtime-name">显存</span>
                      <div className="gpu-runtime-bar is-memory">
                        <span style={{ width: `${gpuItem.memoryPercent}%` }} />
                      </div>
                      <strong className="gpu-runtime-percent">{gpuItem.memoryLabel}</strong>
                    </div>
                  </div>
                ))}
              </div>
            ) : !container.gpuRuntimeAvailable ? (
              <div className="gpu-runtime-grid">
                <div className="gpu-runtime-card is-empty">
                  <div className="gpu-runtime-head">
                    <strong>GPU</strong>
                  </div>
                  <p className="container-runtime-empty">当前暂无数据</p>
                </div>
              </div>
            ) : (
              <p className="container-runtime-empty">当前暂无 GPU 运行数据</p>
            )}
          </div>

          <div className="container-runtime-block">
            <span className="container-runtime-label">端口映射</span>
            {container.portMappings.length > 0 ? (
              <div className="container-port-mapping-list">
                {container.portMappings.map((portMapping) => (
                  <div className="container-port-mapping-card" key={`${container.id}-${portMapping.id}`}>
                    <strong className="container-port-mapping-title">{portMapping.title}</strong>
                    <div className="container-port-mapping-values">
                      <div className="container-port-mapping-endpoint">
                        <span className="container-port-mapping-label">公网</span>
                        <strong className="container-port-mapping-port">{portMapping.publicPort}</strong>
                      </div>
                      <div className="container-port-mapping-endpoint is-container">
                        <span className="container-port-mapping-label">容器</span>
                        <strong className="container-port-mapping-port">{portMapping.containerPort}</strong>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="container-runtime-empty">当前暂无端口映射</p>
            )}
          </div>

          <div className="container-runtime-block">
            <span className="container-runtime-label">疑似 GPU 占用进程</span>
            {container.processRuntimeAvailable && container.runtimeProcesses.length > 0 ? (
              <div className="container-process-chip-list">
                {container.runtimeProcesses.map((processItem) => {
                  return (
                    <div
                      className="container-process-chip"
                      key={processItem.id}
                      title={`${processItem.owner} / ${processItem.command}`}
                    >
                      <span className="container-process-owner">{processItem.owner}</span>
                      <strong className="container-process-command">{processItem.command}</strong>
                    </div>
                  );
                })}
              </div>
            ) : !container.processRuntimeAvailable ? (
              <p className="container-runtime-empty">当前暂无数据</p>
            ) : (
              <p className="container-runtime-empty">当前暂无疑似 GPU 占用进程</p>
            )}
          </div>
        </div>
      </div>

      {cardCollapsible ? (
        <div className="container-card-expand-row">
          <button
            className={`ghost-button container-card-toggle${cardExpanded ? " is-expanded" : ""}`}
            type="button"
            aria-expanded={cardExpanded}
            aria-label={cardExpanded ? "收起详情" : "展开详情"}
            onClick={() => onToggleCardExpand(container.id)}
          >
            <svg className="container-card-toggle-icon" viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5.5 8L10 12.5L14.5 8" />
            </svg>
          </button>
        </div>
      ) : null}

      <div className="container-card-footer">
        <button
          className={`primary-button container-button join-button${joinDisabled ? " is-disabled" : ""}`}
          type="button"
          disabled={joinDisabled}
          onClick={() => {
            if (!joinDisabled) {
              onOpenJoinDialog(container.id);
            }
          }}
        >
          {joinButtonLabel}
        </button>
        <button
          className={`ghost-button container-button leave-button${!leaveDisabled ? " is-joined" : " is-disabled"}`}
          type="button"
          disabled={leaveDisabled}
          onClick={() => {
            if (!leaveDisabled) {
              onOpenLeaveDialog(container.id);
            }
          }}
        >
          {leaveButtonLabel}
        </button>
      </div>
    </article>
  );
}
