import { useEffect, useRef, useState } from "react";

import { useAdminController } from "./useAdminController";
import { useAuthController } from "./useAuthController";
import { useWorkspaceController } from "./useWorkspaceController";


function fallbackCopyText(text) {
  if (typeof document === "undefined") {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    document.body.removeChild(textarea);
  }

  return copied;
}


export function useAppController() {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [activeAccountPanel, setActiveAccountPanel] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [activeView, setActiveView] = useState("workspace");
  const [sshCopyState, setSshCopyState] = useState(null);
  const accountMenuRef = useRef(null);

  function resetTransientUiState() {
    setAccountMenuOpen(false);
    setActiveAccountPanel(null);
    setConfirmDialog(null);
    setSshCopyState(null);
  }

  function handleSessionEstablished(user) {
    resetTransientUiState();
    setActiveView(user?.role === "admin" ? "admin" : "workspace");
    workspaceController.setWorkspaceMessage("");
    adminController.setActiveAdminSection("users");
  }

  function handleSessionCleared() {
    resetTransientUiState();
    setActiveView("workspace");
    workspaceController.resetWorkspaceState();
    adminController.resetAdminState();
  }

  const authController = useAuthController({
    onSessionEstablished: handleSessionEstablished,
    onSessionCleared: handleSessionCleared
  });

  function showFloatingTip(message, status = "success", containerId = null) {
    setSshCopyState({
      containerId,
      message,
      status
    });
  }

  const workspaceController = useWorkspaceController({
    session: authController.session,
    activeView,
    csrfToken: authController.csrfToken,
    showFloatingTip,
    setConfirmDialog
  });

  const adminController = useAdminController({
    session: authController.session,
    activeView,
    csrfToken: authController.csrfToken,
    showFloatingTip,
    setConfirmDialog
  });

  useEffect(() => {
    if (!sshCopyState) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSshCopyState(null);
    }, 1800);

    return () => window.clearTimeout(timer);
  }, [sshCopyState]);

  useEffect(() => {
    const hasOpenDialog =
      Boolean(activeAccountPanel) ||
      Boolean(workspaceController.joinDialogContainerId) ||
      Boolean(workspaceController.leaveDialogContainerId) ||
      Boolean(confirmDialog) ||
      adminController.adminUserDialogOpen ||
      adminController.adminContainerDialogOpen;

    if (!hasOpenDialog) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [
    activeAccountPanel,
    workspaceController.joinDialogContainerId,
    workspaceController.leaveDialogContainerId,
    confirmDialog,
    adminController.adminUserDialogOpen,
    adminController.adminContainerDialogOpen
  ]);

  useEffect(() => {
    if (!accountMenuOpen) {
      return;
    }

    function handleOutsidePointerDown(event) {
      if (!accountMenuRef.current?.contains(event.target)) {
        setAccountMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handleOutsidePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointerDown);
    };
  }, [accountMenuOpen]);

  function updateAuthField(field, value) {
    authController.updateAuthField(field, value);
  }

  function updatePasswordField(field, value) {
    authController.updatePasswordField(field, value);
  }

  function openAccountPanel(panelName) {
    if (authController.session?.role === "admin") {
      setAccountMenuOpen(false);
      return;
    }
    setActiveAccountPanel(panelName);
    setAccountMenuOpen(false);
  }

  async function handleConfirmDialogSubmit() {
    if (!confirmDialog) {
      return;
    }

    const pendingDialog = confirmDialog;
    setConfirmDialog(null);

    try {
      if (pendingDialog.type === "ssh-add") {
        await workspaceController.executeAddSshKey(pendingDialog.keyName, pendingDialog.publicKey);
        return;
      }

      if (pendingDialog.type === "ssh-delete") {
        await workspaceController.executeDeleteSshKey(pendingDialog.sshKeyId);
        return;
      }

      if (pendingDialog.type === "join") {
        await workspaceController.executeJoinContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
        return;
      }

      if (pendingDialog.type === "leave") {
        await workspaceController.executeLeaveContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
        return;
      }

      if (pendingDialog.type === "admin-user-create" || pendingDialog.type === "admin-user-update") {
        await adminController.executeAdminUserSubmit(pendingDialog.userId, pendingDialog.payload);
        return;
      }

      if (pendingDialog.type === "admin-user-delete") {
        await adminController.executeDeleteAdminUser(pendingDialog.userId);
        return;
      }

      if (pendingDialog.type === "admin-container-create" || pendingDialog.type === "admin-container-update") {
        await adminController.executeAdminContainerSubmit(pendingDialog.containerId, pendingDialog.payload);
        return;
      }

      if (pendingDialog.type === "admin-container-delete") {
        await adminController.executeDeleteAdminContainer(pendingDialog.containerId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "操作失败";
      workspaceController.setWorkspaceMessage(message);
    }
  }

  async function handleCopySshCommand(containerId, sshCommand) {
    if (!sshCommand) {
      return;
    }

    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(sshCommand);
      } else if (!fallbackCopyText(sshCommand)) {
        throw new Error("fallback-copy-failed");
      }
      showFloatingTip("SSH 命令已复制", "success", containerId);
    } catch {
      showFloatingTip("复制失败", "error", containerId);
    }
  }

  return {
    accountMenuRef,
    accountMenuOpen,
    activeAccountPanel,
    confirmDialog,
    activeView,
    sshCopyState,
    setAccountMenuOpen,
    setActiveAccountPanel,
    setConfirmDialog,
    setActiveView,
    updateAuthField,
    updatePasswordField,
    openAccountPanel,
    handleConfirmDialogSubmit,
    handleCopySshCommand,
    ...authController,
    ...workspaceController,
    ...adminController
  };
}
