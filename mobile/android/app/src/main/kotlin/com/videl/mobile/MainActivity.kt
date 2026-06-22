package com.videl.mobile

import android.content.ContentValues
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class MainActivity : FlutterActivity() {
    private val methodCh = "videl/python"
    private val eventCh = "videl/python/events"
    private val shareCh = "videl/share"
    private var eventSink: EventChannel.EventSink? = null
    private var pendingSharedText: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        pendingSharedText = extractSharedText(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val txt = extractSharedText(intent) ?: return
        pendingSharedText = txt
        runOnUiThread {
            flutterEngine?.dartExecutor?.binaryMessenger?.let { msg ->
                MethodChannel(msg, shareCh).invokeMethod("shared", txt)
            }
        }
    }

    private fun registerWithMediaStore(path: String) {
        try {
            val file = File(path)
            if (!file.exists()) return
            val ext = file.extension.lowercase()
            val inDownloads = path.contains("/Download/")
            if (inDownloads && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
                    put(MediaStore.MediaColumns.SIZE, file.length())
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/Videl")
                }
                contentResolver.insert(
                    MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                    values
                )
                return
            }
            val (collection, mime, kind) = when (ext) {
                "mp4", "mkv", "mov", "webm", "m4v" ->
                    Triple(
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                            MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        else MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                        "video/$ext", "video"
                    )
                "jpg", "jpeg", "png", "gif", "webp" ->
                    Triple(
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                            MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        else MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        if (ext == "jpg") "image/jpeg" else "image/$ext", "image"
                    )
                "mp3", "m4a", "aac", "ogg", "opus", "flac", "wav" ->
                    Triple(
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                            MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        else MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                        "audio/$ext", "audio"
                    )
                else -> return
            }

            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.SIZE, file.length())
                put(MediaStore.MediaColumns.DATE_ADDED, System.currentTimeMillis() / 1000)
                put(MediaStore.MediaColumns.DATE_MODIFIED, file.lastModified() / 1000)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    val relative = when (kind) {
                        "video" -> "Movies/Videl"
                        "image" -> "DCIM/Videl"
                        else -> "Music/Videl"
                    }
                    put(MediaStore.MediaColumns.RELATIVE_PATH, relative)
                } else {
                    @Suppress("DEPRECATION")
                    put(MediaStore.MediaColumns.DATA, file.absolutePath)
                }
            }
            contentResolver.insert(collection, values)
        } catch (_: Throwable) {
            // Best-effort — fallback to MediaScanner.
        }
    }

    private fun extractSharedText(intent: Intent?): String? {
        if (intent == null) return null
        return when (intent.action) {
            Intent.ACTION_SEND -> intent.getStringExtra(Intent.EXTRA_TEXT)
            Intent.ACTION_VIEW -> intent.dataString
            else -> null
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, shareCh)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "get_pending" -> {
                        result.success(pendingSharedText)
                        pendingSharedText = null
                    }
                    else -> result.notImplemented()
                }
            }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, methodCh)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "fg_start" -> {
                        DownloadService.start(applicationContext)
                        result.success(true)
                    }
                    "fg_stop" -> {
                        DownloadService.stop(applicationContext)
                        result.success(true)
                    }
                    "fg_update" -> {
                        val title = call.argument<String>("title") ?: "Videl"
                        val text = call.argument<String>("text") ?: ""
                        val pct = call.argument<Int>("pct") ?: -1
                        DownloadService.update(title, text, pct)
                        result.success(true)
                    }
                    "media_scan" -> {
                        val path = call.argument<String>("path") ?: ""
                        registerWithMediaStore(path)
                        MediaScannerConnection.scanFile(
                            applicationContext, arrayOf(path), null
                        ) { _, _ -> }
                        result.success(true)
                    }
                    "ytdlp_formats" -> {
                        val url = call.argument<String>("url") ?: ""
                        Thread {
                            try {
                                val py = Python.getInstance()
                                val mod = py.getModule("videl_dl")
                                val res = mod.callAttr("list_formats", url).toString()
                                runOnUiThread { result.success(res) }
                            } catch (t: Throwable) {
                                runOnUiThread { result.error("PY", t.message, null) }
                            }
                        }.start()
                    }
                    "ytdlp_download" -> {
                        val url = call.argument<String>("url") ?: ""
                        val outDir = call.argument<String>("out_dir") ?: ""
                        val fmt = call.argument<String>("format") ?: "b"
                        Thread {
                            try {
                                val py = Python.getInstance()
                                val mod = py.getModule("videl_dl")
                                val res = mod.callAttr(
                                    "download",
                                    url, outDir, fmt,
                                    object {
                                        @Suppress("unused")
                                        fun on_progress(pct: Double, speed: String) {
                                            runOnUiThread {
                                                eventSink?.success(
                                                    mapOf("pct" to pct, "speed" to speed)
                                                )
                                            }
                                        }
                                    }
                                )
                                runOnUiThread { result.success(res.toString()) }
                            } catch (t: Throwable) {
                                runOnUiThread { result.error("PY", t.message, null) }
                            }
                        }.start()
                    }
                    "install_apk" -> {
                        val path = call.argument<String>("path") ?: ""
                        val file = File(path)
                        if (!file.exists()) {
                            result.error("NOT_FOUND", "APK not found: $path", null)
                            return@setMethodCallHandler
                        }
                        try {
                            val uri: Uri = FileProvider.getUriForFile(
                                applicationContext,
                                "${applicationContext.packageName}.fileprovider",
                                file
                            )
                            val intent = Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
                                setDataAndType(uri, "application/vnd.android.package-archive")
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            startActivity(intent)
                            result.success(true)
                        } catch (t: Throwable) {
                            result.error("INSTALL_ERR", t.message, null)
                        }
                    }
                    else -> result.notImplemented()
                }
            }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventCh)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(args: Any?, sink: EventChannel.EventSink?) { eventSink = sink }
                override fun onCancel(args: Any?) { eventSink = null }
            })
    }
}
