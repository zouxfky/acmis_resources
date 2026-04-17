export function ConfirmDialog({ confirmDialog, onSubmit, onClose }) {
  if (!confirmDialog) {
    return null;
  }

  return (
    <div className="account-dialog-overlay" onClick={onClose}>
      <div className="account-dialog confirm-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="account-dialog-head">
          <div>
            <h2>{confirmDialog.title}</h2>
            <p className="dialog-subcopy">{confirmDialog.copy}</p>
          </div>
        </div>

        {confirmDialog.keyItems.length > 0 ? (
          <div className="confirm-key-list">
            {confirmDialog.keyItems.map((keyItem) => (
              <div className="confirm-key-chip" key={keyItem.id}>
                <strong>{keyItem.label}</strong>
                <span>{keyItem.value}</span>
              </div>
            ))}
          </div>
        ) : null}

        <div className="detail-action-row">
          <button className="ghost-button detail-action-button" type="button" onClick={onClose}>
            取消
          </button>
          <button
            className={`detail-action-button ${
              confirmDialog.type === "leave" || confirmDialog.type === "ssh-delete"
                ? "ghost-button is-danger"
                : "primary-button"
            }`}
            type="button"
            onClick={onSubmit}
          >
            {confirmDialog.type === "join"
              ? "确认加入"
              : confirmDialog.type === "leave"
                ? "确认退出"
                : confirmDialog.type === "ssh-add"
                  ? "确认添加"
                  : confirmDialog.type === "ssh-delete"
                    ? "确认删除"
                    : confirmDialog.type === "admin-user-create"
                      ? "确认新增"
                      : confirmDialog.type === "admin-user-update"
                        ? "确认保存"
                        : confirmDialog.type === "admin-user-delete"
                          ? "确认删除"
                          : confirmDialog.type === "admin-container-create"
                            ? "确认新增"
                            : confirmDialog.type === "admin-container-update"
                              ? "确认保存"
                              : "确认删除"}
          </button>
        </div>
      </div>
    </div>
  );
}
