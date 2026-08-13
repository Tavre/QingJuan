import { useEffect, useState } from "react";
import { Spin } from "antd";

import { clearSessionSecurity, getAdminSession, login, logout } from "./api";
import { AdminShell } from "./components/AdminShell";
import { BrandLogo } from "./components/BrandLogo";
import { LoginScreen } from "./components/LoginScreen";
import type { SessionInfo } from "./types";

type AuthenticationState =
  | { status: "checking" }
  | { status: "anonymous" }
  | { status: "authenticated"; session: SessionInfo };

export function QingjuanAdmin() {
  const [authentication, setAuthentication] = useState<AuthenticationState>({ status: "checking" });

  useEffect(() => {
    let active = true;
    getAdminSession()
      .then((session) => {
        if (active) setAuthentication({ status: "authenticated", session });
      })
      .catch(() => {
        clearSessionSecurity();
        if (active) setAuthentication({ status: "anonymous" });
      });

    const handleExpiredSession = () => {
      clearSessionSecurity();
      setAuthentication({ status: "anonymous" });
    };
    window.addEventListener("qingjuan:session-expired", handleExpiredSession);
    return () => {
      active = false;
      window.removeEventListener("qingjuan:session-expired", handleExpiredSession);
    };
  }, []);

  if (authentication.status === "checking") {
    return (
      <main className="startup-screen" aria-label="正在检查管理会话">
        <BrandLogo />
        <Spin size="large" />
        <span>正在连接青卷服务…</span>
      </main>
    );
  }

  if (authentication.status === "anonymous") {
    return (
      <LoginScreen
        onLogin={async (password) => {
          const session = await login(password);
          setAuthentication({ status: "authenticated", session });
        }}
      />
    );
  }

  return (
    <AdminShell
      session={authentication.session}
      onLogout={async () => {
        try {
          await logout();
        } finally {
          clearSessionSecurity();
          setAuthentication({ status: "anonymous" });
        }
      }}
    />
  );
}
