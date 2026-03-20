// QingJuan
// Author: Tavre
// License: GPL-3.0-only

use std::{path::PathBuf, sync::Mutex};

use serde::Serialize;
use tauri::{Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Serialize)]
struct BackendInfo {
    host: String,
    port: u16,
    already_running: bool,
}

fn resolve_backend_data_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Ok(local_data_dir) = app.path().local_data_dir() {
        return Ok(local_data_dir.join("QingJuan").join("data"));
    }

    app.path()
        .app_local_data_dir()
        .map(|path| path.join("data"))
        .map_err(|err| err.to_string())
}

#[tauri::command]
async fn start_python_backend(
    app: tauri::AppHandle,
    state: State<'_, BackendState>,
) -> Result<BackendInfo, String> {
    let mut child_slot = state.child.lock().map_err(|err| err.to_string())?;
    if child_slot.is_some() {
        return Ok(BackendInfo {
            host: "127.0.0.1".into(),
            port: 19453,
            already_running: true,
        });
    }

    let data_dir = resolve_backend_data_dir(&app)?;

    let sidecar_command = app
        .shell()
        .sidecar("qingjuan-backend")
        .map_err(|err| err.to_string())?
        .args(["serve", "--host", "127.0.0.1", "--port", "19453"])
        .env("QINGJUAN_DATA_DIR", data_dir.to_string_lossy().to_string());

    let (mut receiver, child) = sidecar_command.spawn().map_err(|err| err.to_string())?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[qingjuan-backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[qingjuan-backend] {}", String::from_utf8_lossy(&line));
                }
                _ => {}
            }
        }
    });

    *child_slot = Some(child);

    Ok(BackendInfo {
        host: "127.0.0.1".into(),
        port: 19453,
        already_running: false,
    })
}

#[tauri::command]
fn stop_python_backend(state: State<'_, BackendState>) -> Result<(), String> {
    let mut child_slot = state.child.lock().map_err(|err| err.to_string())?;
    if let Some(child) = child_slot.take() {
        child.kill().map_err(|err| err.to_string())?;
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![start_python_backend, stop_python_backend])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running qingjuan");
}
