export function ConfirmDialog({ confirmDialog, submitting = false, onSubmit, onClose }) {
  if (!confirmDialog) {
    return null;
  }

  const destructiveTypes = new Set([
    "leave",
    "ssh-delete",
    "admin-user-delete",
    "admin-container-delete"
  ]);
  const confirmLabelMap = {
    "ssh-add": "Confirm add",
    "ssh-delete": "Confirm delete",
    join: "Confirm join",
    leave: "Confirm leave",
    "admin-user-create": "Confirm create",
    "admin-user-update": "Confirm save",
    "admin-user-delete": "Confirm delete",
    "admin-container-create": "Confirm create",
    "admin-container-update": "Confirm save",
    "admin-container-delete": "Confirm delete"
  };
  const confirmButtonLabel = submitting ? "Processing..." : confirmLabelMap[confirmDialog.type] || "Confirm";

  function handleClose() {
    if (!submitting) {
      onClose();
    }
  }

  return (
    <div className="account-dialog-overlay" onClick={handleClose}>
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
          <button className="ghost-button detail-action-button" type="button" onClick={handleClose} disabled={submitting}>
            Cancel
          </button>
          <button
            className={`detail-action-button ${destructiveTypes.has(confirmDialog.type) ? "ghost-button is-danger" : "primary-button"}`}
            type="button"
            onClick={onSubmit}
            disabled={submitting}
          >
            {confirmButtonLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
