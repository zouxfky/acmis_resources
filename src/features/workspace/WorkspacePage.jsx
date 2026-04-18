import { useState } from "react";

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

export function WorkspacePage({
  session,
  sshKeys,
  joinedContainers,
  workspaceContainers,
  workspaceMessage,
  workspaceLoading,
  onOpenJoinDialog,
  onOpenLeaveDialog,
  onCopySshCommand
}) {
  const maxJoinedContainerCount = Number(session?.max_containers_per_user);
  const maxSshKeyCount = Number(session?.max_ssh_keys_per_user);
  const joinedContainerSummaryLabel = `${joinedContainers.length} / ${workspaceContainers.length}`;
  const sshKeyLimitLabel = Number.isFinite(maxSshKeyCount) && maxSshKeyCount > 0
    ? `上限 ${maxSshKeyCount} 把`
    : "";
  const sshConnectionLimitLabel = Number.isFinite(maxJoinedContainerCount) && maxJoinedContainerCount > 0
    ? `上限 ${maxJoinedContainerCount} 台`
    : "";
  const [expandedProcessContainerIds, setExpandedProcessContainerIds] = useState({});

  function toggleProcessList(containerId) {
    setExpandedProcessContainerIds((current) => ({
      ...current,
      [containerId]: !current[containerId]
    }));
  }

  return (
    <>
      <section className="overview-grid workspace-overview-grid">
        <article className="overview-card accent-card quota-overview-card">
          <span>已加入容器</span>
          <strong>{joinedContainerSummaryLabel}</strong>
          <p>{joinedContainers.length > 0 ? joinedContainers.map((item) => item.name).join(" / ") : "当前还没有加入任何容器"}</p>
        </article>

        <article className="overview-card quota-overview-card">
          {sshKeyLimitLabel ? (
            <span className="quota-overview-pill">{sshKeyLimitLabel}</span>
          ) : null}
          <span>SSH 公钥</span>
          <strong>{sshKeys.length} 把</strong>
          <p>登录授权通过公钥下发到已开通容器</p>
        </article>

        <article className="overview-card ssh-overview-card quota-overview-card">
          {sshConnectionLimitLabel ? (
            <span className="quota-overview-pill">{sshConnectionLimitLabel}</span>
          ) : null}
          <span>SSH连接</span>
          {joinedContainers.length === 0 ? (
            <>
              <strong>暂无容器</strong>
              <p>当前还没有加入任何容器</p>
            </>
          ) : (
            <div className="joined-ssh-list is-grid-two">
              {joinedContainers.map((container) => {
                const sshCommand = `ssh -p ${container.ssh_port} ${session.username}@${container.host}`;

                return (
                  <div className="joined-ssh-item" key={container.id}>
                    <div className="joined-ssh-head">
                      <div className="joined-ssh-copy">
                        <strong>{container.name}</strong>
                        <span>{container.gpu}</span>
                      </div>
                      <button
                        className="ghost-button ssh-copy-button ssh-copy-label-button"
                        type="button"
                        onClick={() => onCopySshCommand(container.id, sshCommand)}
                        aria-label={`复制 ${container.name} SSH 连接`}
                      >
                        <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                          <path d="M16 1H6a2 2 0 0 0-2 2v12h2V3h10z" />
                          <path d="M19 5H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m0 16H10V7h9z" />
                        </svg>
                        <span>SSH</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </article>
      </section>

      <section className="dashboard-content no-sidebar">
        {workspaceMessage ? <div className="notice is-error">{workspaceMessage}</div> : null}

        <section className="container-stage">
          <div className="container-grid">
            {workspaceContainers.map((container) => {
              const isJoined = container.joinedKeyIds.length > 0;
              const isContainerActive = container.status === "active";
              const isContainerFull = Number(container.active_user_count) >= Number(container.max_users);
              const hasAvailableJoinKeys = sshKeys.some((item) => !(container.joinedKeyIds || []).includes(item.id));
              const isCooldownActive = container.actionCooldownActive;
              const cooldownLabel = container.actionCooldownLabel;
              const joinDisabled = workspaceLoading || isCooldownActive || !isContainerActive || isContainerFull || !hasAvailableJoinKeys;
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
              const processListExpanded = Boolean(expandedProcessContainerIds[container.id]);
              const visibleRuntimeProcesses = processListExpanded
                ? container.runtimeProcesses
                : container.runtimeProcesses.slice(0, 3);
              const hiddenProcessCount = Math.max(0, container.runtimeProcesses.length - 3);

              return (
                <article
                  className={`container-card${isJoined ? " is-joined" : ""}${container.status === "active" ? " is-active" : ""}${container.status === "offline" ? " is-offline" : ""}${container.status === "disabled" ? " is-disabled" : ""}`}
                  key={container.id}
                >
                  <div className="container-card-head">
                    <div>
                      <div className="container-title-row">
                        <strong className="container-name">{container.name}</strong>
                        <span className={`status-pill container-status-pill ${statusClassName}`}>{statusLabel}</span>
                        {isJoined ? <span className="container-joined-flag">已加入</span> : null}
                        {container.syncPending ? <span className="container-sync-flag">同步中</span> : null}
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

                  <div className="container-card-body">
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
                        <span className="container-runtime-label">GPU 占用进程</span>
                        {container.processRuntimeAvailable && container.runtimeProcesses.length > 0 ? (
                          <>
                            <div className="container-process-chip-list">
                              {visibleRuntimeProcesses.map((processItem) => {
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
                            {hiddenProcessCount > 0 || processListExpanded ? (
                              <div className="container-runtime-meta-row">
                                {hiddenProcessCount > 0 && !processListExpanded ? (
                                  <p className="container-runtime-meta">另有 {hiddenProcessCount} 个进程</p>
                                ) : (
                                  <span className="container-runtime-meta">共 {container.runtimeProcesses.length} 个进程</span>
                                )}
                                {container.runtimeProcesses.length > 3 ? (
                                  <button
                                    className="ghost-button container-process-toggle"
                                    type="button"
                                    onClick={() => toggleProcessList(container.id)}
                                  >
                                    {processListExpanded ? "收起" : "展开全部"}
                                  </button>
                                ) : null}
                              </div>
                            ) : null}
                          </>
                        ) : !container.processRuntimeAvailable ? (
                          <p className="container-runtime-empty">当前暂无数据</p>
                        ) : (
                          <p className="container-runtime-empty">当前暂无 GPU 占用进程</p>
                        )}
                      </div>
                    </div>
                  </div>

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
            })}
          </div>
        </section>
      </section>
    </>
  );
}
