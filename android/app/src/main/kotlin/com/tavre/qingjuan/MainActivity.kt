package com.tavre.qingjuan

import android.app.Activity
import android.content.Intent
import android.view.KeyEvent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream

class MainActivity : FlutterActivity() {
    companion object {
        private const val FILE_CHANNEL = "qingjuan/files"
        private const val READER_CHANNEL = "qingjuan/reader"
        private const val CREATE_DOCUMENT_REQUEST = 0x514A
    }

    private var pendingResult: MethodChannel.Result? = null
    private var pendingSource: File? = null
    private var readerChannel: MethodChannel? = null
    private var volumeKeyReadingEnabled = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, FILE_CHANNEL)
            .setMethodCallHandler(::handleFileMethod)
        readerChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            READER_CHANNEL,
        ).also { channel ->
            channel.setMethodCallHandler { call, result ->
                if (call.method != "setVolumeKeyEnabled") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                volumeKeyReadingEnabled = call.arguments as? Boolean ?: false
                result.success(null)
            }
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (volumeKeyReadingEnabled &&
            (keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN)
        ) {
            if (event?.repeatCount == 0) {
                readerChannel?.invokeMethod(
                    "volumeKey",
                    if (keyCode == KeyEvent.KEYCODE_VOLUME_UP) "up" else "down",
                )
            }
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (volumeKeyReadingEnabled &&
            (keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN)
        ) {
            return true
        }
        return super.onKeyUp(keyCode, event)
    }

    private fun handleFileMethod(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "saveFile") {
            result.notImplemented()
            return
        }
        if (pendingResult != null) {
            result.error("save_in_progress", "已有文件正在等待保存", null)
            return
        }

        val sourcePath = call.argument<String>("sourcePath")
        val suggestedName = call.argument<String>("suggestedName")
        val mimeType = call.argument<String>("mimeType") ?: "application/octet-stream"
        if (sourcePath.isNullOrBlank() || suggestedName.isNullOrBlank()) {
            result.error("invalid_arguments", "保存文件参数不完整", null)
            return
        }

        val canonicalSource = try {
            File(sourcePath).canonicalFile
        } catch (error: Exception) {
            result.error("invalid_source", "无法读取导出缓存文件", error.message)
            return
        }
        val cacheRoot = cacheDir.canonicalFile
        if (!canonicalSource.isFile ||
            !canonicalSource.path.startsWith(cacheRoot.path + File.separator)
        ) {
            result.error("invalid_source", "只能保存应用缓存中的导出文件", null)
            return
        }

        pendingResult = result
        pendingSource = canonicalSource
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = mimeType
            putExtra(Intent.EXTRA_TITLE, suggestedName)
        }
        try {
            startActivityForResult(intent, CREATE_DOCUMENT_REQUEST)
        } catch (error: Exception) {
            pendingResult = null
            pendingSource = null
            result.error("document_picker_unavailable", "无法打开系统文档选择器", error.message)
        }
    }

    @Deprecated("Deprecated in Android; retained for Flutter 3.24 compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != CREATE_DOCUMENT_REQUEST) {
            super.onActivityResult(requestCode, resultCode, data)
            return
        }

        val result = pendingResult
        val source = pendingSource
        pendingResult = null
        pendingSource = null
        if (result == null || source == null) return
        if (resultCode != Activity.RESULT_OK || data?.data == null) {
            result.success(null)
            return
        }

        val target = data.data!!
        try {
            contentResolver.openOutputStream(target, "w").use { output ->
                requireNotNull(output) { "无法打开系统文档目标" }
                FileInputStream(source).use { input -> input.copyTo(output) }
            }
            result.success(target.toString())
        } catch (error: Exception) {
            result.error("save_failed", "写入系统文档失败", error.message)
        }
    }
}
