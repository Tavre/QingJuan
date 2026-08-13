import {
  clearSessionSecurity,
  checkTranslationModel,
  deleteBook,
  getRuntimeLogs,
  getServiceDiagnostics,
  login,
  revealConnectionToken,
  setDeviceBanned,
} from "./api";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("admin API client", () => {
  it("adds the session CSRF header to protected writes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        authenticated: true,
        expiresAt: "2030-01-01T00:00:00Z",
        csrfToken: "csrf-value",
        csrfHeader: "X-QingJuan-CSRF",
      }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok", bookId: "book-1" }));
    vi.stubGlobal("fetch", fetchMock);

    await login("correct horse battery staple");
    await deleteBook("book-1");

    const deleteOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(deleteOptions.method).toBe("DELETE");
    expect((deleteOptions.headers as Headers).get("X-QingJuan-CSRF")).toBe("csrf-value");
    expect(deleteOptions.credentials).toBe("same-origin");
    clearSessionSecurity();
  });

  it("returns the backend detail for failed login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "管理密码错误" }, 401)));

    await expect(login("wrong-password")).rejects.toMatchObject({
      message: "管理密码错误",
      status: 401,
    });
  });

  it("sends device ban changes with JSON and CSRF protection", async () => {
    const device = {
      id: "0123456789abcdef0123456789abcdef",
      name: "测试电脑",
      platform: "windows",
      ipAddress: "127.0.0.1",
      firstSeenAt: "2030-01-01T00:00:00Z",
      lastSeenAt: "2030-01-01T00:00:00Z",
      banned: true,
      bannedAt: "2030-01-01T00:00:00Z",
      online: false,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        authenticated: true,
        expiresAt: "2030-01-01T00:00:00Z",
        csrfToken: "device-csrf",
        csrfHeader: "X-QingJuan-CSRF",
      }))
      .mockResolvedValueOnce(jsonResponse(device));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin-password");
    await setDeviceBanned(device.id, true);

    const request = fetchMock.mock.calls[1];
    const options = request[1] as RequestInit;
    expect(request[0]).toBe(`/api/v1/devices/${device.id}/ban`);
    expect(options.method).toBe("PUT");
    expect(options.body).toBe(JSON.stringify({ banned: true }));
    expect((options.headers as Headers).get("X-QingJuan-CSRF")).toBe("device-csrf");
    clearSessionSecurity();
  });

  it("protects token reveal while keeping runtime log reads non-mutating", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        authenticated: true,
        expiresAt: "2030-01-01T00:00:00Z",
        csrfToken: "observability-csrf",
        csrfHeader: "X-QingJuan-CSRF",
      }))
      .mockResolvedValueOnce(jsonResponse({ token: "connection-token-value" }))
      .mockResolvedValueOnce(jsonResponse({ items: [], sources: [], total: 0 }))
      .mockResolvedValueOnce(jsonResponse({ schemaVersion: 1, status: "healthy" }))
      .mockResolvedValueOnce(jsonResponse({ status: "ready", available: true }));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin-password");
    await revealConnectionToken();
    await getRuntimeLogs(1000);
    await getServiceDiagnostics();
    await checkTranslationModel(true);

    const revealOptions = fetchMock.mock.calls[1][1] as RequestInit;
    const logsOptions = fetchMock.mock.calls[2][1] as RequestInit;
    const diagnosticsOptions = fetchMock.mock.calls[3][1] as RequestInit;
    const modelCheckOptions = fetchMock.mock.calls[4][1] as RequestInit;
    expect(fetchMock.mock.calls[1][0]).toBe("/admin/api/connection-token/reveal");
    expect(revealOptions.method).toBe("POST");
    expect((revealOptions.headers as Headers).get("X-QingJuan-CSRF")).toBe("observability-csrf");
    expect(fetchMock.mock.calls[2][0]).toBe("/admin/api/runtime-logs?limit=1000");
    expect(logsOptions.method).toBe("GET");
    expect((logsOptions.headers as Headers).has("X-QingJuan-CSRF")).toBe(false);
    expect(fetchMock.mock.calls[3][0]).toBe("/admin/api/diagnostics");
    expect(diagnosticsOptions.method).toBe("GET");
    expect((diagnosticsOptions.headers as Headers).has("X-QingJuan-CSRF")).toBe(false);
    expect(fetchMock.mock.calls[4][0]).toBe("/api/v1/translation-model/check?force=true");
    expect(modelCheckOptions.method).toBe("POST");
    expect((modelCheckOptions.headers as Headers).get("X-QingJuan-CSRF")).toBe("observability-csrf");
    clearSessionSecurity();
  });
});
