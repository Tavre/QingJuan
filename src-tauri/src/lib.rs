// QingJuan
// Author: Tavre
// License: GPL-3.0-only

use std::{
    env,
    net::TcpListener,
    path::PathBuf,
    process::Command,
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

use serde::Serialize;
use tauri::{Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

#[derive(Default)]
struct BackendState {
    child: Arc<Mutex<Option<CommandChild>>>,
}

impl BackendState {
    fn stop(&self) -> Result<(), String> {
        let mut child_slot = self.child.lock().map_err(|err| err.to_string())?;
        stop_backend_child(&mut child_slot)
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        let mut child_slot = match self.child.lock() {
            Ok(slot) => slot,
            Err(err) => err.into_inner(),
        };
        let _ = stop_backend_child(&mut child_slot);
    }
}

#[derive(Serialize)]
struct BackendInfo {
    host: String,
    port: u16,
    already_running: bool,
}

fn stop_backend_child(child_slot: &mut Option<CommandChild>) -> Result<(), String> {
    if let Some(child) = child_slot.take() {
        child.kill().map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn resolve_backend_data_dir(_app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let executable_path = env::current_exe().map_err(|err| err.to_string())?;
    let install_dir = executable_path
        .parent()
        .map(PathBuf::from)
        .ok_or_else(|| format!("无法解析安装目录：{}", executable_path.display()))?;
    Ok(install_dir.join("data"))
}

fn resolve_powershell_executable() -> PathBuf {
    if let Some(system_root) = env::var_os("SystemRoot") {
        let candidate = PathBuf::from(system_root)
            .join("System32")
            .join("WindowsPowerShell")
            .join("v1.0")
            .join("powershell.exe");
        if candidate.exists() {
            return candidate;
        }
    }
    PathBuf::from("powershell.exe")
}

fn is_backend_port_available(host: &str, port: u16) -> bool {
    TcpListener::bind((host, port)).is_ok()
}

#[cfg(target_os = "windows")]
fn cleanup_stale_backend_processes() -> Result<(), String> {
    let output = Command::new("taskkill")
        .args(["/F", "/IM", "qingjuan-backend.exe"])
        .output()
        .map_err(|err| format!("清理旧后端进程失败：{err}"))?;

    if output.status.success() {
        return Ok(());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let combined = format!("{stdout}\n{stderr}");
    if combined.contains("找不到进程")
        || combined.contains("No tasks are running")
        || combined.contains("没有运行的实例")
    {
        return Ok(());
    }

    Err(format!("清理旧后端进程失败：{}", combined.trim()))
}

#[cfg(not(target_os = "windows"))]
fn cleanup_stale_backend_processes() -> Result<(), String> {
    Ok(())
}

fn ensure_backend_port_ready(host: &str, port: u16) -> Result<(), String> {
    if is_backend_port_available(host, port) {
        return Ok(());
    }

    cleanup_stale_backend_processes()?;
    thread::sleep(Duration::from_millis(400));

    if is_backend_port_available(host, port) {
        return Ok(());
    }

    Err(format!(
        "本地端口 {port} 已被其他进程占用，请关闭旧版青卷后端或相关占用后重试。"
    ))
}

fn export_dialog_config(format: &str) -> Result<(&'static str, &'static str), String> {
    match format {
        "txt" => Ok(("txt", "文本文档 (*.txt)|*.txt|所有文件 (*.*)|*.*")),
        "epub" => Ok(("epub", "EPUB 电子书 (*.epub)|*.epub|所有文件 (*.*)|*.*")),
        _ => Err(format!("不支持的导出格式：{format}")),
    }
}

#[cfg(target_os = "windows")]
fn choose_export_path_impl(suggested_name: &str, format: &str) -> Result<Option<String>, String> {
    let (default_ext, filter) = export_dialog_config(format)?;
    let script = r#"
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = '导出书籍'
$dialog.Filter = $env:QINGJUAN_EXPORT_FILTER
$dialog.DefaultExt = $env:QINGJUAN_EXPORT_EXTENSION
$dialog.AddExtension = $true
$dialog.OverwritePrompt = $true
$dialog.RestoreDirectory = $true
$dialog.FileName = $env:QINGJUAN_EXPORT_FILE_NAME
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.FileName
}
"#;

    let output = Command::new(resolve_powershell_executable())
        .args(["-NoProfile", "-NonInteractive", "-STA", "-Command", script])
        .env("QINGJUAN_EXPORT_EXTENSION", default_ext)
        .env("QINGJUAN_EXPORT_FILTER", filter)
        .env("QINGJUAN_EXPORT_FILE_NAME", suggested_name)
        .output()
        .map_err(|err| err.to_string())?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(if stderr.is_empty() {
            "打开导出保存对话框失败".into()
        } else {
            stderr
        });
    }

    let selected = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if selected.is_empty() {
        return Ok(None);
    }

    Ok(Some(selected))
}

#[cfg(not(target_os = "windows"))]
fn choose_export_path_impl(suggested_name: &str, format: &str) -> Result<Option<String>, String> {
    let _ = (suggested_name, format);
    Err("当前平台暂不支持导出保存对话框".into())
}

#[tauri::command]
fn choose_export_path(suggested_name: String, format: String) -> Result<Option<String>, String> {
    choose_export_path_impl(&suggested_name, &format)
}

#[tauri::command]
async fn start_python_backend(
    app: tauri::AppHandle,
    state: State<'_, BackendState>,
) -> Result<BackendInfo, String> {
    const BACKEND_HOST: &str = "127.0.0.1";
    const BACKEND_PORT: u16 = 19453;

    let mut child_slot = state.child.lock().map_err(|err| err.to_string())?;
    if child_slot.is_some() {
        return Ok(BackendInfo {
            host: BACKEND_HOST.into(),
            port: BACKEND_PORT,
            already_running: true,
        });
    }

    let data_dir = resolve_backend_data_dir(&app)?;
    ensure_backend_port_ready(BACKEND_HOST, BACKEND_PORT)?;

    let sidecar_command = app
        .shell()
        .sidecar("qingjuan-backend")
        .map_err(|err| err.to_string())?
        .args(["serve", "--host", BACKEND_HOST, "--port", "19453"])
        .env("QINGJUAN_DATA_DIR", data_dir.to_string_lossy().to_string());

    let (mut receiver, child) = sidecar_command.spawn().map_err(|err| err.to_string())?;
    let child_pid = child.pid();
    let child_state = Arc::clone(&state.child);

    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[qingjuan-backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[qingjuan-backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(error) => {
                    eprintln!("[qingjuan-backend] {error}");
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!(
                        "[qingjuan-backend] terminated with code {:?}, signal {:?}",
                        payload.code, payload.signal
                    );
                    let mut child_slot = match child_state.lock() {
                        Ok(slot) => slot,
                        Err(err) => err.into_inner(),
                    };
                    if child_slot
                        .as_ref()
                        .is_some_and(|running_child| running_child.pid() == child_pid)
                    {
                        let _ = child_slot.take();
                    }
                }
                _ => {}
            }
        }
    });

    *child_slot = Some(child);

    Ok(BackendInfo {
        host: BACKEND_HOST.into(),
        port: BACKEND_PORT,
        already_running: false,
    })
}

#[tauri::command]
fn stop_python_backend(state: State<'_, BackendState>) -> Result<(), String> {
    state.stop()
}

pub fn run() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            choose_export_path,
            start_python_backend,
            stop_python_backend
        ])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running qingjuan");
}
