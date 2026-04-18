export function AdminDialogs({
  adminUserDialogOpen,
  adminUserForm,
  adminUsersMessage,
  adminUsersStatus,
  onCancelAdminUserEdit,
  onUpdateAdminUserField,
  onSubmitAdminUser,
  adminContainerDialogOpen,
  adminContainerForm,
  adminContainersMessage,
  adminContainersStatus,
  onCancelAdminContainerEdit,
  onUpdateAdminContainerField,
  onSubmitAdminContainer
}) {
  return (
    <>
      {adminUserDialogOpen ? (
        <div className="account-dialog-overlay" onClick={onCancelAdminUserEdit}>
          <div className="account-dialog is-wide admin-form-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="account-dialog-head">
              <div>
                <h2>{adminUserForm.id ? "编辑用户" : "新增用户"}</h2>
                <p className="dialog-subcopy">
                  {adminUserForm.id ? "修改这名用户的账户信息" : "创建新的用户账户"}
                </p>
              </div>
              <button className="ghost-button account-dialog-close" type="button" onClick={onCancelAdminUserEdit}>
                关闭
              </button>
            </div>

            {adminUsersMessage ? (
              <div className={`notice ${adminUsersStatus === "error" ? "is-error" : ""}`}>{adminUsersMessage}</div>
            ) : null}

            <form className="compact-form admin-dialog-form" onSubmit={onSubmitAdminUser}>
              <div className="admin-form-grid">
                <label className="field">
                  <span>用户名</span>
                  <input
                    type="text"
                    value={adminUserForm.username}
                    onChange={(event) => onUpdateAdminUserField("username", event.target.value)}
                    placeholder="请输入用户名"
                    autoComplete="off"
                  />
                </label>

                <label className="field">
                  <span>姓名</span>
                  <input
                    type="text"
                    value={adminUserForm.real_name}
                    onChange={(event) => onUpdateAdminUserField("real_name", event.target.value)}
                    placeholder="请输入姓名"
                    autoComplete="off"
                  />
                </label>

                <label className="field">
                  <span>角色</span>
                  <select value={adminUserForm.role} onChange={(event) => onUpdateAdminUserField("role", event.target.value)}>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </label>

                <label className="field">
                  <span>{adminUserForm.id ? "重置密码" : "初始密码"}</span>
                  <input
                    type="password"
                    value={adminUserForm.id ? adminUserForm.new_password : adminUserForm.password}
                    onChange={(event) => onUpdateAdminUserField(adminUserForm.id ? "new_password" : "password", event.target.value)}
                    placeholder={adminUserForm.id ? "留空则不修改" : "请输入初始密码"}
                    autoComplete="new-password"
                  />
                </label>
              </div>

              <div className="admin-inline-actions">
                <button className="ghost-button" type="button" onClick={onCancelAdminUserEdit}>
                  取消
                </button>
                <button className="primary-button" type="submit">
                  {adminUserForm.id ? "保存" : "创建"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {adminContainerDialogOpen ? (
        <div className="account-dialog-overlay" onClick={onCancelAdminContainerEdit}>
          <div className="account-dialog is-wide admin-form-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="account-dialog-head">
              <div>
                <h2>{adminContainerForm.id ? "编辑服务器" : "新增服务器"}</h2>
                <p className="dialog-subcopy">
                  {adminContainerForm.id ? "修改这台服务器的静态配置" : "创建新的服务器记录"}
                </p>
              </div>
              <button className="ghost-button account-dialog-close" type="button" onClick={onCancelAdminContainerEdit}>
                关闭
              </button>
            </div>

            {adminContainersMessage ? (
              <div className={`notice ${adminContainersStatus === "error" ? "is-error" : ""}`}>{adminContainersMessage}</div>
            ) : null}

            <form className="compact-form admin-dialog-form" onSubmit={onSubmitAdminContainer}>
              <div className="admin-form-grid">
                <label className="field">
                  <span>名称</span>
                  <input
                    type="text"
                    value={adminContainerForm.name}
                    onChange={(event) => onUpdateAdminContainerField("name", event.target.value)}
                    placeholder="请输入名称"
                  />
                </label>

                <label className="field">
                  <span>主机地址</span>
                  <input
                    type="text"
                    value={adminContainerForm.host}
                    onChange={(event) => onUpdateAdminContainerField("host", event.target.value)}
                    placeholder="请输入主机地址"
                  />
                </label>

                <label className="field">
                  <span>SSH端口</span>
                  <input
                    type="number"
                    min="1"
                    max="65535"
                    value={adminContainerForm.ssh_port}
                    onChange={(event) => onUpdateAdminContainerField("ssh_port", event.target.value)}
                    placeholder="22"
                  />
                </label>

                <label className="field">
                  <span>Root密码</span>
                  <input
                    type="password"
                    value={adminContainerForm.root_password}
                    onChange={(event) => onUpdateAdminContainerField("root_password", event.target.value)}
                    placeholder={adminContainerForm.id ? "留空则不修改" : "请输入 Root 密码"}
                    autoComplete="new-password"
                  />
                </label>

                <label className="field">
                  <span>最大人数</span>
                  <input
                    type="number"
                    min="1"
                    value={adminContainerForm.max_users}
                    onChange={(event) => onUpdateAdminContainerField("max_users", event.target.value)}
                    placeholder="3"
                  />
                </label>

                <label className="field">
                  <span>状态</span>
                  <select value={adminContainerForm.status} onChange={(event) => onUpdateAdminContainerField("status", event.target.value)}>
                    <option value="active">active</option>
                    <option value="offline">offline</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
              </div>

              <div className="admin-inline-actions">
                <button className="ghost-button" type="button" onClick={onCancelAdminContainerEdit}>
                  取消
                </button>
                <button className="primary-button" type="submit">
                  {adminContainerForm.id ? "保存" : "创建"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
