import { useEffect, useRef, useState } from "react";

import {
  changePasswordRequest,
  fetchPublicOverviewRequest,
  fetchSession,
  loginRequest,
  logoutRequest
} from "../api/client";


export function useAuthController({ onSessionEstablished, onSessionCleared }) {
  const [authForm, setAuthForm] = useState({ username: "", password: "" });
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: ""
  });
  const [session, setSession] = useState(null);
  const [csrfToken, setCsrfToken] = useState("");
  const [authStatus, setAuthStatus] = useState("idle");
  const [authMessage, setAuthMessage] = useState("");
  const [publicOverview, setPublicOverview] = useState({ notice_lines: [] });
  const [publicOverviewStatus, setPublicOverviewStatus] = useState("idle");
  const [passwordStatus, setPasswordStatus] = useState("idle");
  const [passwordMessage, setPasswordMessage] = useState("");
  const sessionEstablishedRef = useRef(onSessionEstablished);
  const sessionClearedRef = useRef(onSessionCleared);

  useEffect(() => {
    sessionEstablishedRef.current = onSessionEstablished;
  }, [onSessionEstablished]);

  useEffect(() => {
    sessionClearedRef.current = onSessionCleared;
  }, [onSessionCleared]);

  useEffect(() => {
    let cancelled = false;

    async function loadPublicOverview() {
      setPublicOverviewStatus("loading");
      try {
        const data = await fetchPublicOverviewRequest();
        if (!cancelled) {
          setPublicOverview({
            notice_lines: Array.isArray(data.notice_lines) ? data.notice_lines : []
          });
          setPublicOverviewStatus("success");
        }
      } catch {
        if (!cancelled) {
          setPublicOverview({ notice_lines: [] });
          setPublicOverviewStatus("error");
        }
      }
    }

    async function loadSession() {
      try {
        const response = await fetchSession();
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (!cancelled) {
          setSession(data.user);
          setCsrfToken(data.csrf_token || "");
          setAuthMessage("");
          sessionEstablishedRef.current?.(data.user);
        }
      } catch {
        if (!cancelled) {
          setAuthMessage("后端未启动时，登录请求会失败");
        }
      }
    }

    loadPublicOverview();
    loadSession();
    return () => {
      cancelled = true;
    };
  }, []);

  function resetAuthState() {
    setSession(null);
    setCsrfToken("");
    setAuthStatus("idle");
    setAuthForm({ username: "", password: "" });
    setAuthMessage("");
    setPasswordStatus("idle");
    setPasswordMessage("");
    setPasswordForm({
      currentPassword: "",
      newPassword: "",
      confirmPassword: ""
    });
  }

  function updateAuthField(field, value) {
    setAuthForm((current) => ({ ...current, [field]: value }));
  }

  function updatePasswordField(field, value) {
    setPasswordForm((current) => ({ ...current, [field]: value }));
  }

  async function handleLogin(event) {
    event.preventDefault();
    setAuthStatus("loading");
    setAuthMessage("");

    try {
      const data = await loginRequest(authForm);
      setSession(data.user);
      setCsrfToken(data.csrf_token || "");
      setAuthStatus("success");
      setAuthMessage("");
      sessionEstablishedRef.current?.(data.user);
    } catch (error) {
      setAuthStatus("error");
      setAuthMessage(error instanceof Error ? error.message : "登录失败，请检查用户名或密码");
    }
  }

  async function handleLogout() {
    try {
      await logoutRequest(csrfToken);
    } catch {
      // ignore logout transport failures and clear local state anyway
    } finally {
      resetAuthState();
      sessionClearedRef.current?.();
    }
  }

  async function handleChangePassword(event) {
    event.preventDefault();
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordStatus("error");
      setPasswordMessage("两次输入的新密码不一致");
      return;
    }

    setPasswordStatus("loading");
    setPasswordMessage("");

    try {
      const data = await changePasswordRequest(
        {
          current_password: passwordForm.currentPassword,
          new_password: passwordForm.newPassword
        },
        csrfToken
      );
      setPasswordStatus("success");
      setPasswordMessage(data.message || "密码修改成功");
      if (data.user) {
        setSession(data.user);
        sessionEstablishedRef.current?.(data.user);
      }
      setCsrfToken(data.csrf_token || "");
      setPasswordForm({
        currentPassword: "",
        newPassword: "",
        confirmPassword: ""
      });
    } catch (error) {
      setPasswordStatus("error");
      setPasswordMessage(error instanceof Error ? error.message : "密码修改失败，请稍后再试");
    }
  }

  return {
    authForm,
    passwordForm,
    session,
    csrfToken,
    authStatus,
    authMessage,
    publicOverview,
    publicOverviewStatus,
    passwordStatus,
    passwordMessage,
    setSession,
    setCsrfToken,
    updateAuthField,
    updatePasswordField,
    handleLogin,
    handleLogout,
    handleChangePassword,
    resetAuthState
  };
}
