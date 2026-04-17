export function AccountDialogs({
  accountDisplayName,
  session,
  sshKeys,
  joinedContainers,
  activeAccountPanel,
  onCloseAccountPanel,
  sshKeyNameDraft,
  sshKeyDraft,
  onSetSshKeyNameDraft,
  onSetSshKeyDraft,
  sshMessage,
  sshStatus,
  onAddSshKey,
  onDeleteSshKey,
  passwordForm,
  onUpdatePasswordField,
  passwordMessage,
  passwordStatus,
  onChangePassword
}) {
  if (!activeAccountPanel) {
    return null;
  }

  return (
    <div className="account-dialog-overlay" onClick={onCloseAccountPanel}>
      <div className={`account-dialog${activeAccountPanel === "ssh" ? " is-compact" : ""}`} onClick={(event) => event.stopPropagation()}>
        <div className="account-dialog-head">
          <div>
            {activeAccountPanel === "ssh" ? (
              <div className="account-dialog-title-row">
                <h2>SSH 公钥管理</h2>
              </div>
            ) : (
              <h2>{activeAccountPanel === "profile" ? "个人资料" : "修改密码"}</h2>
            )}
          </div>
          <button className="ghost-button account-dialog-close" type="button" onClick={onCloseAccountPanel}>
            关闭
          </button>
        </div>

        {activeAccountPanel === "profile" ? (
          <div className="account-profile-grid">
            <div className="account-profile-card">
              <span>姓名</span>
              <strong>{accountDisplayName}</strong>
            </div>
            <div className="account-profile-card">
              <span>用户名</span>
              <strong>{session.username}</strong>
            </div>
            <div className="account-profile-card">
              <span>角色</span>
              <strong>{session.role === "admin" ? "管理员" : "普通用户"}</strong>
            </div>
            <div className="account-profile-card">
              <span>SSH 公钥</span>
              <strong>{sshKeys.length} 把</strong>
            </div>
            <div className="account-profile-card is-wide">
              <span>已加入容器</span>
              <strong>{joinedContainers.length > 0 ? joinedContainers.map((item) => item.name).join(" / ") : "尚未加入容器"}</strong>
            </div>
          </div>
        ) : activeAccountPanel === "ssh" ? (
          <div className="account-ssh-stack">
            <form className="ssh-form account-ssh-form" onSubmit={onAddSshKey}>
              <label className="field">
                <span>公钥名称</span>
                <input
                  type="text"
                  value={sshKeyNameDraft}
                  onChange={(event) => onSetSshKeyNameDraft(event.target.value)}
                  placeholder="例如 MacBook Pro"
                />
              </label>
              <label className="field">
                <span>添加 SSH 公钥</span>
                <textarea
                  value={sshKeyDraft}
                  onChange={(event) => onSetSshKeyDraft(event.target.value)}
                  placeholder="粘贴完整 SSH 公钥，例如 ssh-ed25519 AAAA..."
                />
              </label>

              {sshMessage ? <div className={`notice ${sshStatus === "error" ? "is-error" : ""}`}>{sshMessage}</div> : null}

              <button className="primary-button" type="submit" disabled={sshStatus === "loading"}>
                {sshStatus === "loading" ? "正在添加..." : "添加公钥"}
              </button>
            </form>

            <div className="key-list">
              {sshKeys.length > 0 ? (
                sshKeys.map((item) => (
                  <div className="key-item" key={item.id}>
                    <div>
                      <strong>{item.label}</strong>
                      <p>{item.value}</p>
                    </div>
                    <button className="ghost-button key-delete" type="button" onClick={() => onDeleteSshKey(item.id)}>
                      删除
                    </button>
                  </div>
                ))
              ) : (
                <div className="key-item">
                  <div>
                    <strong>暂无 SSH 公钥</strong>
                    <p>先添加一把公钥，再去加入容器</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <form className="password-form compact-form account-password-form" onSubmit={onChangePassword}>
            <label className="field">
              <span>当前密码</span>
              <input
                type="password"
                value={passwordForm.currentPassword}
                onChange={(event) => onUpdatePasswordField("currentPassword", event.target.value)}
                placeholder="请输入当前密码"
                autoComplete="current-password"
              />
            </label>

            <label className="field">
              <span>新密码</span>
              <input
                type="password"
                value={passwordForm.newPassword}
                onChange={(event) => onUpdatePasswordField("newPassword", event.target.value)}
                placeholder="请输入新密码"
                autoComplete="new-password"
              />
            </label>

            <label className="field">
              <span>确认新密码</span>
              <input
                type="password"
                value={passwordForm.confirmPassword}
                onChange={(event) => onUpdatePasswordField("confirmPassword", event.target.value)}
                placeholder="请再次输入新密码"
                autoComplete="new-password"
              />
            </label>

            {passwordMessage ? (
              <div className={`notice ${passwordStatus === "error" ? "is-error" : ""}`}>{passwordMessage}</div>
            ) : null}

            <button className="primary-button" type="submit" disabled={passwordStatus === "loading"}>
              {passwordStatus === "loading" ? "正在更新..." : "修改密码"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
