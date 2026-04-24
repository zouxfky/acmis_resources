export function WorkspaceDialogs({
  sshKeys,
  joinDialogContainer,
  joinDialogAvailableKeys,
  joinDialogSelection,
  joinDialogSelectionUnchanged,
  joinDialogMessage,
  onCloseJoinDialog,
  onToggleJoinDialogKey,
  onConfirmJoinContainer,
  leaveDialogContainer,
  leaveDialogKeys,
  leaveDialogSelection,
  leaveDialogMessage,
  onCloseLeaveDialog,
  onToggleLeaveDialogKey,
  onConfirmLeaveContainer
}) {
  return (
    <>
      {joinDialogContainer ? (
        <div className="account-dialog-overlay" onClick={onCloseJoinDialog}>
          <div className="account-dialog workspace-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="workspace-dialog-body">
              <div className="account-dialog-head">
                <div>
                  <h2>加入 {joinDialogContainer.name}</h2>
                  <p className="dialog-subcopy">{joinDialogContainer.gpu}</p>
                </div>
              </div>

              {joinDialogAvailableKeys.length > 0 ? (
                <div className="join-dialog-copy">
                  <div>选择要写入这台容器的 SSH 公钥，可多选</div>
                  <div>提交成功后，5 分钟内将限制再次操作这台容器</div>
                </div>
              ) : null}

              <div className="join-key-list">
                {joinDialogAvailableKeys.length > 0 ? joinDialogAvailableKeys.map((keyItem) => {
                  const checked = joinDialogSelection.includes(keyItem.id);

                  return (
                    <label className={`join-key-card${checked ? " is-selected" : ""}`} key={keyItem.id}>
                      <input
                        className="join-key-checkbox"
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggleJoinDialogKey(keyItem.id)}
                      />
                      <div className="join-key-copy">
                        <strong>{keyItem.label}</strong>
                        <span>{keyItem.value}</span>
                      </div>
                    </label>
                  );
                }) : (
                  <div className="join-dialog-copy">
                    {sshKeys.length === 0
                      ? "当前没有可选公钥，请先到右上角菜单里添加 SSH 公钥"
                      : "当前公钥都已经加入这台容器，无法继续添加"}
                  </div>
                )}
              </div>

              {joinDialogMessage ? <div className="notice is-error join-dialog-notice">{joinDialogMessage}</div> : null}
            </div>

            <div className="detail-action-row workspace-dialog-actions">
              <button className="ghost-button detail-action-button" type="button" onClick={onCloseJoinDialog}>
                取消
              </button>
              <button
                className="primary-button detail-action-button"
                type="button"
                onClick={onConfirmJoinContainer}
                disabled={joinDialogAvailableKeys.length === 0 || joinDialogSelection.length === 0 || joinDialogSelectionUnchanged}
              >
                确认加入
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {leaveDialogContainer ? (
        <div className="account-dialog-overlay" onClick={onCloseLeaveDialog}>
          <div className="account-dialog workspace-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="workspace-dialog-body">
              <div className="account-dialog-head">
                <div>
                  <h2>退出 {leaveDialogContainer.name}</h2>
                </div>
              </div>

              <div className="join-dialog-copy">
                <div>选择要从这台容器撤销授权的 SSH 公钥，可多选</div>
                <div>确认后会移除对应的容器访问关系，提交成功后 5 分钟内将限制再次操作这台容器</div>
              </div>

              {leaveDialogKeys.length > 0 ? (
                <div className="join-key-list">
                  {leaveDialogKeys.map((keyItem) => {
                    const checked = leaveDialogSelection.includes(keyItem.id);

                    return (
                      <label className={`join-key-card${checked ? " is-selected" : ""}`} key={keyItem.id}>
                        <input
                          className="join-key-checkbox"
                          type="checkbox"
                          checked={checked}
                          onChange={() => onToggleLeaveDialogKey(keyItem.id)}
                        />
                        <div className="join-key-copy">
                          <strong>{keyItem.label}</strong>
                          <span>{keyItem.value}</span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <div className="join-dialog-copy">这台容器当前没有绑定 SSH 公钥，确认后会直接退出整台容器</div>
              )}

              {leaveDialogMessage ? <div className="notice is-error join-dialog-notice">{leaveDialogMessage}</div> : null}
            </div>

            <div className="detail-action-row workspace-dialog-actions">
              <button className="ghost-button detail-action-button" type="button" onClick={onCloseLeaveDialog}>
                取消
              </button>
              <button className="ghost-button detail-action-button is-danger" type="button" onClick={onConfirmLeaveContainer}>
                确认退出
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
