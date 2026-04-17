export function AdminPage({
  adminUsers,
  adminContainers,
  adminUsersMessage,
  adminUsersStatus,
  adminContainersMessage,
  adminContainersStatus,
  activeAdminSection,
  activeAdminSectionConfig,
  adminActiveUserCount,
  adminActiveContainerCount,
  adminSectionCatalog,
  onSetActiveAdminSection,
  onStartCreateAdminUser,
  onStartEditAdminUser,
  onDeleteAdminUser,
  onStartCreateAdminContainer,
  onStartEditAdminContainer,
  onDeleteAdminContainer
}) {
  return (
    <>
      <section className="overview-grid admin-overview-grid">
        <article className="overview-card accent-card">
          <span>激活用户</span>
          <strong>{adminActiveUserCount}</strong>
          <p>当前系统内可用账户数量</p>
        </article>

        <article className="overview-card">
          <span>在线服务器</span>
          <strong>{adminActiveContainerCount}</strong>
          <p>当前状态为 active 的服务器数量</p>
        </article>
      </section>

      <section className="admin-shell">
        <aside className="workspace-card admin-nav-panel">
          <div className="admin-nav-toggle-row">
            <div className="admin-nav-head">
              <h2>菜单</h2>
            </div>
          </div>

          <div className="admin-nav-list">
            {adminSectionCatalog.map((section) => (
              <button
                className={`admin-nav-item admin-nav-item-simple${activeAdminSection === section.id ? " is-active" : ""}`}
                type="button"
                key={section.id}
                onClick={() => onSetActiveAdminSection(section.id)}
              >
                <strong>{section.label}</strong>
              </button>
            ))}
          </div>
        </aside>

        <section className="workspace-card admin-panel">
          <div className="admin-panel-banner admin-panel-banner-inline">
            <strong>{activeAdminSectionConfig.label}</strong>
            <span>
              {activeAdminSection === "users"
                ? `当前共 ${adminUsers.length} 个账户`
                : `当前共 ${adminContainers.length} 台服务器`}
            </span>
          </div>

          {activeAdminSection === "users" ? (
            <>
              {adminUsersMessage ? (
                <div className={`notice ${adminUsersStatus === "error" ? "is-error" : ""}`}>{adminUsersMessage}</div>
              ) : null}

              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>姓名</th>
                      <th>角色</th>
                      <th>状态</th>
                      <th>密码</th>
                      <th>公钥数</th>
                      <th>授权数</th>
                      <th className="admin-table-actions">
                        <button
                          className="ghost-button admin-table-add-button"
                          type="button"
                          onClick={onStartCreateAdminUser}
                          aria-label="新增用户"
                        >
                          +
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.length > 0 ? (
                      adminUsers.map((userItem) => (
                        <tr key={userItem.id}>
                          <td>{userItem.username}</td>
                          <td>{userItem.real_name || "未设置姓名"}</td>
                          <td>{userItem.role}</td>
                          <td>{userItem.status}</td>
                          <td>-</td>
                          <td>{userItem.ssh_key_count}</td>
                          <td>{userItem.access_count}</td>
                          <td>
                            {userItem.role === "admin" ? (
                              <span className="admin-action-muted">管理员不可编辑</span>
                            ) : (
                              <div className="admin-row-actions">
                                <button className="ghost-button" type="button" onClick={() => onStartEditAdminUser(userItem)}>
                                  编辑
                                </button>
                                <button className="ghost-button is-danger" type="button" onClick={() => onDeleteAdminUser(userItem)}>
                                  删除
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="admin-table-empty" colSpan="8">暂无用户数据</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <>
              {adminContainersMessage ? (
                <div className={`notice ${adminContainersStatus === "error" ? "is-error" : ""}`}>{adminContainersMessage}</div>
              ) : null}

              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>GPU型号</th>
                      <th>主机地址</th>
                      <th>SSH端口</th>
                      <th>Root密码</th>
                      <th>最大人数</th>
                      <th>状态</th>
                      <th>使用中</th>
                      <th className="admin-table-actions">
                        <button
                          className="ghost-button admin-table-add-button"
                          type="button"
                          onClick={onStartCreateAdminContainer}
                          aria-label="新增服务器"
                        >
                          +
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminContainers.length > 0 ? (
                      adminContainers.map((containerItem) => (
                        <tr key={containerItem.id}>
                          <td>{containerItem.name}</td>
                          <td>{containerItem.gpu_model || "-"}</td>
                          <td>{containerItem.host}</td>
                          <td>{containerItem.ssh_port}</td>
                          <td>{containerItem.has_root_password ? "已设置" : "未设置"}</td>
                          <td>{containerItem.max_users}</td>
                          <td>{containerItem.status}</td>
                          <td>{containerItem.active_user_count}</td>
                          <td>
                            <div className="admin-row-actions">
                              <button className="ghost-button" type="button" onClick={() => onStartEditAdminContainer(containerItem)}>
                                编辑
                              </button>
                              <button className="ghost-button is-danger" type="button" onClick={() => onDeleteAdminContainer(containerItem)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="admin-table-empty" colSpan="9">暂无服务器数据</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </section>
    </>
  );
}
