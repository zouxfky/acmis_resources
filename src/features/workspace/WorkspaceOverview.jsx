export function WorkspaceOverview({
  joinedContainers,
  session,
  sshKeys,
  workspaceContainers,
  onCopySshCommand
}) {
  const maxJoinedContainerCount = Number(session?.max_containers_per_user);
  const maxSshKeyCount = Number(session?.max_ssh_keys_per_user);
  const onlineContainers = workspaceContainers.filter((item) => item.status === "active");
  const abnormalContainers = workspaceContainers.filter((item) => item.status !== "active");
  const offlineContainers = workspaceContainers.filter((item) => item.status === "offline");
  const disabledContainers = workspaceContainers.filter((item) => item.status === "disabled");
  const onlineContainerSummaryLabel = `${onlineContainers.length} / ${workspaceContainers.length}`;
  const sshKeyLimitLabel = Number.isFinite(maxSshKeyCount) && maxSshKeyCount > 0
    ? `上限 ${maxSshKeyCount} 把`
    : "";
  const sshConnectionLimitLabel = Number.isFinite(maxJoinedContainerCount) && maxJoinedContainerCount > 0
    ? `上限 ${maxJoinedContainerCount} 台`
    : "";

  return (
    <section className="overview-grid workspace-overview-grid">
      <article className="overview-card accent-card quota-overview-card">
        <span>在线容器</span>
        <strong>{onlineContainerSummaryLabel}</strong>
        {abnormalContainers.length > 0 ? (
          <div className="container-health-summary">
            {offlineContainers.length > 0 ? (
              <p>
                <span>离线容器：</span>
                {offlineContainers.map((item) => item.name).join(" / ")}
              </p>
            ) : null}
            {disabledContainers.length > 0 ? (
              <p>
                <span>停用容器：</span>
                {disabledContainers.map((item) => item.name).join(" / ")}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="container-health-ok">全部在线</p>
        )}
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
  );
}
