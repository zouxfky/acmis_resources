import { adminSectionCatalog } from "./app/constants";
import { LoginPage } from "./features/auth/LoginPage";
import { AdminPage } from "./features/admin/AdminPage";
import { ConfirmDialog } from "./features/shared/ConfirmDialog";
import { FloatingTip } from "./features/shared/FloatingTip";
import { OverlayDialogs } from "./features/shared/OverlayDialogs";
import { WorkspacePage } from "./features/workspace/WorkspacePage";
import { useAppController } from "./hooks/useAppController";


export default function App() {
  const controller = useAppController();

  if (!controller.session) {
    return (
      <LoginPage
        authForm={controller.authForm}
        authStatus={controller.authStatus}
        authMessage={controller.authMessage}
        publicOverview={controller.publicOverview}
        publicOverviewStatus={controller.publicOverviewStatus}
        onLogin={controller.handleLogin}
        onUpdateAuthField={controller.updateAuthField}
      />
    );
  }

  const accountDisplayName = controller.session.real_name || controller.session.username;
  const isAdmin = controller.session.role === "admin";
  const adminUserCount = controller.adminUsers.length;
  const adminActiveContainerCount = controller.adminContainers.filter((item) => item.status === "active").length;
  const activeAdminSectionConfig =
    adminSectionCatalog.find((item) => item.id === controller.activeAdminSection) || adminSectionCatalog[0];

  return (
    <main className="dashboard-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <div className="dashboard-frame">
        <header className="dashboard-topbar">
          <div className="dashboard-title-group">
            <div className="dashboard-title dashboard-brand-title">
              <h1>ACMIS Lab GPU资源管理</h1>
              <p>统一管理实验室 GPU 容器接入、SSH 授权与运行状态</p>
            </div>
          </div>

          <div className="dashboard-actions">
            <div className="account-menu-wrap" ref={controller.accountMenuRef}>
              <button
                className={`account-trigger${controller.accountMenuOpen ? " is-open" : ""}`}
                type="button"
                onClick={() => controller.setAccountMenuOpen((current) => !current)}
              >
                <span className="account-trigger-label">{accountDisplayName}</span>
                <span className="account-trigger-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <path d="M19.14 12.94a7.43 7.43 0 0 0 .05-.94 7.43 7.43 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.63l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.24 7.24 0 0 0-1.63-.94l-.36-2.54A.5.5 0 0 0 13.9 2h-3.8a.5.5 0 0 0-.49.41l-.36 2.54c-.58.22-1.12.53-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.71 8.47a.5.5 0 0 0 .12.63l2.03 1.58a7.43 7.43 0 0 0-.05.94 7.43 7.43 0 0 0 .05.94l-2.03 1.58a.5.5 0 0 0-.12.63l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.41 1.05.72 1.63.94l.36 2.54a.5.5 0 0 0 .49.41h3.8a.5.5 0 0 0 .49-.41l.36-2.54c.58-.22 1.12-.53 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.63zm-7.14 2.56A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5z" />
                  </svg>
                </span>
              </button>

              {controller.accountMenuOpen ? (
                <div className="account-dropdown">
                  <div className="account-dropdown-head">
                    <strong>{accountDisplayName}</strong>
                    <span>{controller.session.username}</span>
                  </div>

                  <button
                    className={`account-menu-item${isAdmin ? " is-disabled" : ""}`}
                    type="button"
                    onClick={() => controller.openAccountPanel("profile")}
                    disabled={isAdmin}
                  >
                    个人资料
                  </button>
                  <button
                    className={`account-menu-item${isAdmin ? " is-disabled" : ""}`}
                    type="button"
                    onClick={() => controller.openAccountPanel("ssh")}
                    disabled={isAdmin}
                  >
                    SSH 公钥管理
                  </button>
                  <button
                    className={`account-menu-item${isAdmin ? " is-disabled" : ""}`}
                    type="button"
                    onClick={() => controller.openAccountPanel("password")}
                    disabled={isAdmin}
                  >
                    修改密码
                  </button>
                  <button className="account-menu-item is-danger" type="button" onClick={controller.handleLogout}>
                    退出登录
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {isAdmin ? (
          <AdminPage
            adminUsers={controller.adminUsers}
            adminContainers={controller.adminContainers}
            adminUsersMessage={controller.adminUsersMessage}
            adminUsersStatus={controller.adminUsersStatus}
            adminContainersMessage={controller.adminContainersMessage}
            adminContainersStatus={controller.adminContainersStatus}
            activeAdminSection={controller.activeAdminSection}
            activeAdminSectionConfig={activeAdminSectionConfig}
            adminUserCount={adminUserCount}
            adminActiveContainerCount={adminActiveContainerCount}
            adminSectionCatalog={adminSectionCatalog}
            onSetActiveAdminSection={controller.setActiveAdminSection}
            onStartCreateAdminUser={controller.startCreateAdminUser}
            onStartEditAdminUser={controller.startEditAdminUser}
            onDeleteAdminUser={controller.handleDeleteAdminUser}
            onStartCreateAdminContainer={controller.startCreateAdminContainer}
            onStartEditAdminContainer={controller.startEditAdminContainer}
            onDeleteAdminContainer={controller.handleDeleteAdminContainer}
          />
        ) : (
          <WorkspacePage
            session={controller.session}
            sshKeys={controller.sshKeys}
            joinedContainers={controller.joinedContainers}
            workspaceContainers={controller.workspaceContainers}
            workspaceMessage={controller.workspaceMessage}
            workspaceLoading={controller.workspaceLoading}
            onOpenJoinDialog={controller.openJoinDialog}
            onOpenLeaveDialog={controller.openLeaveDialog}
            onCopySshCommand={controller.handleCopySshCommand}
          />
        )}
      </div>

      <OverlayDialogs
        accountDisplayName={accountDisplayName}
        session={controller.session}
        sshKeys={controller.sshKeys}
        joinedContainers={controller.joinedContainers}
        activeAccountPanel={controller.activeAccountPanel}
        onCloseAccountPanel={() => controller.setActiveAccountPanel(null)}
        sshKeyNameDraft={controller.sshKeyNameDraft}
        sshKeyDraft={controller.sshKeyDraft}
        onSetSshKeyNameDraft={controller.setSshKeyNameDraft}
        onSetSshKeyDraft={controller.setSshKeyDraft}
        sshMessage={controller.sshMessage}
        sshStatus={controller.sshStatus}
        onAddSshKey={controller.handleAddSshKey}
        onDeleteSshKey={controller.handleDeleteSshKey}
        passwordForm={controller.passwordForm}
        onUpdatePasswordField={controller.updatePasswordField}
        passwordMessage={controller.passwordMessage}
        passwordStatus={controller.passwordStatus}
        onChangePassword={controller.handleChangePassword}
        joinDialogContainer={controller.joinDialogContainer}
        joinDialogAvailableKeys={controller.joinDialogAvailableKeys}
        joinDialogSelection={controller.joinDialogSelection}
        joinDialogSelectionUnchanged={controller.joinDialogSelectionUnchanged}
        joinDialogMessage={controller.joinDialogMessage}
        onCloseJoinDialog={() => controller.setJoinDialogContainerId(null)}
        onToggleJoinDialogKey={controller.toggleJoinDialogKey}
        onConfirmJoinContainer={controller.confirmJoinContainer}
        leaveDialogContainer={controller.leaveDialogContainer}
        leaveDialogKeys={controller.leaveDialogKeys}
        leaveDialogSelection={controller.leaveDialogSelection}
        leaveDialogMessage={controller.leaveDialogMessage}
        onCloseLeaveDialog={() => controller.setLeaveDialogContainerId(null)}
        onToggleLeaveDialogKey={controller.toggleLeaveDialogKey}
        onConfirmLeaveContainer={controller.confirmLeaveContainer}
        adminUserDialogOpen={controller.adminUserDialogOpen}
        adminUserForm={controller.adminUserForm}
        adminUsersMessage={controller.adminUsersMessage}
        adminUsersStatus={controller.adminUsersStatus}
        onCancelAdminUserEdit={controller.cancelAdminUserEdit}
        onUpdateAdminUserField={controller.updateAdminUserField}
        onSubmitAdminUser={controller.handleAdminUserSubmit}
        adminContainerDialogOpen={controller.adminContainerDialogOpen}
        adminContainerForm={controller.adminContainerForm}
        adminContainersMessage={controller.adminContainersMessage}
        adminContainersStatus={controller.adminContainersStatus}
        onCancelAdminContainerEdit={controller.cancelAdminContainerEdit}
        onUpdateAdminContainerField={controller.updateAdminContainerField}
        onUpdateAdminContainerPortMapping={controller.updateAdminContainerPortMapping}
        onSubmitAdminContainer={controller.handleAdminContainerSubmit}
      />

      <ConfirmDialog
        confirmDialog={controller.confirmDialog}
        onSubmit={controller.handleConfirmDialogSubmit}
        onClose={() => controller.setConfirmDialog(null)}
      />

      <FloatingTip tip={controller.sshCopyState} />
    </main>
  );
}
