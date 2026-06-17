import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';

// MethodChannel bridge to Kotlin side that wraps Chaquopy + yt-dlp.
// Kotlin counterpart lives at android/app/src/main/kotlin/com/videl/mobile/PythonBridge.kt
class PythonRunner {
  static const _ch = MethodChannel('videl/python');
  static const _events = EventChannel('videl/python/events');

  // Returns {title, duration, formats: [...]}.
  static Future<Map<String, dynamic>> ytdlpFormats(String url) async {
    final raw = await _ch.invokeMethod<String>('ytdlp_formats', {'url': url});
    if (raw == null || raw.isEmpty) return {'title': '', 'formats': []};
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  // Returns final output path on success.
  static Future<String> ytdlpDownload({
    required String url,
    required String outDir,
    String? format,
    double? startTime,
    double? endTime,
  }) async {
    final args = <String, dynamic>{
      'url': url,
      'out_dir': outDir,
      'format': format ?? 'b',
    };
    if (startTime != null && endTime != null) {
      args['start_time'] = startTime;
      args['end_time'] = endTime;
    }
    final res = await _ch.invokeMethod<String>('ytdlp_download', args);
    return res ?? '';
  }

  // Stream of progress events: {'job_id': ..., 'pct': 0.0-100.0, 'speed': '...'}.
  static Stream<Map<String, dynamic>> progress() => _events
      .receiveBroadcastStream()
      .map((e) => Map<String, dynamic>.from(e as Map));

  // Notify MediaStore so file appears in Photos/Gallery.
  static Future<void> mediaScan(String path) async {
    await _ch.invokeMethod('media_scan', {'path': path});
  }

  // Foreground service controls — keeps process alive during downloads.
  static Future<void> fgStart() => _ch.invokeMethod('fg_start').then((_) {});
  static Future<void> fgStop() => _ch.invokeMethod('fg_stop').then((_) {});
  static Future<void> fgUpdate(
          {required String title, required String text, int pct = -1}) =>
      _ch.invokeMethod('fg_update',
          {'title': title, 'text': text, 'pct': pct}).then((_) {});
}

class ShareBridge {
  static const _ch = MethodChannel('videl/share');

  // URL pending from a SEND/VIEW intent (one-shot).
  static Future<String?> pending() async =>
      _ch.invokeMethod<String>('get_pending');

  // Stream of URLs shared while app is already running.
  static Stream<String> incoming() {
    final ctrl = StreamController<String>.broadcast();
    _ch.setMethodCallHandler((call) async {
      if (call.method == 'shared' && call.arguments is String) {
        ctrl.add(call.arguments as String);
      }
    });
    return ctrl.stream;
  }
}
