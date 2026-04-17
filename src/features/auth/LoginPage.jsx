export function LoginPage({
  authForm,
  authStatus,
  authMessage,
  publicOverview,
  publicOverviewStatus,
  onLogin,
  onUpdateAuthField
}) {
  const noticeLines = Array.isArray(publicOverview?.notice_lines) ? publicOverview.notice_lines : [];
  const onboardingSteps = [
    {
      id: "device",
      title: "准备连接设备",
      description: "在需要登录容器的电脑上准备一把 SSH 公钥，后续将用它完成身份授权"
    },
    {
      id: "key",
      title: "导入平台公钥",
      description: "登录平台后进入右上角个人设置，将这把 SSH 公钥添加到当前账户"
    },
    {
      id: "join",
      title: "授权并发起连接",
      description: "选择目标容器完成加入授权，再复制平台提供的 SSH 命令从本机连接"
    }
  ];

  return (
    <main className="page-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />
      <section className="hero-panel">
        <div className="brand-lockup">
          <h1>ACMIS Lab GPU资源管理</h1>
          <p>统一管理实验室 GPU 容器接入、SSH 授权与运行状态</p>
        </div>

        <div className="onboarding-flow">
          <div className="usage-notice-head">
            <strong>流程介绍</strong>
          </div>

          <ol className="onboarding-flow-list">
            {onboardingSteps.map((step, index) => (
              <li className="onboarding-step" key={step.id}>
                <span className="onboarding-step-index">{index + 1}</span>
                <div className="onboarding-step-copy">
                  <p>
                    <strong>{step.title}</strong>
                    <span>{step.description}</span>
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <div className="usage-notice">
          <div className="usage-notice-head">
            <strong>使用须知</strong>
          </div>

          {noticeLines.length > 0 ? (
            <ul className="usage-notice-list">
              {noticeLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : publicOverviewStatus === "loading" ? (
            <p className="usage-notice-loading">使用须知加载中</p>
          ) : null}
        </div>
      </section>

      <section className="login-panel">
        <div className="login-card">
          <div className="card-header">
            <h2>登陆平台</h2>
          </div>

          <form className="login-form" onSubmit={onLogin}>
            <label className="field">
              <span>用户名</span>
              <input
                type="text"
                value={authForm.username}
                onChange={(event) => onUpdateAuthField("username", event.target.value)}
                placeholder="请输入用户名"
                autoComplete="username"
              />
            </label>

            <label className="field">
              <span>密码</span>
              <input
                type="password"
                value={authForm.password}
                onChange={(event) => onUpdateAuthField("password", event.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
              />
            </label>

            <div className="form-row">
              <span className="hint-line">首次登录后请尽快修改默认密码</span>
            </div>

            {authMessage ? (
              <div className={`notice ${authStatus === "error" ? "is-error" : ""}`}>{authMessage}</div>
            ) : null}

            <button className="primary-button" type="submit" disabled={authStatus === "loading"}>
              {authStatus === "loading" ? "正在验证..." : "进入平台"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
