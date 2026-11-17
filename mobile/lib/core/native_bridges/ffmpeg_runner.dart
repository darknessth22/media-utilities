import 'dart:io';

import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit_config.dart';
import 'package:ffmpeg_kit_flutter_new/return_code.dart';
import 'package:ffmpeg_kit_flutter_new/statistics.dart';
import 'package:path/path.dart' as p;

typedef ProgressCb = void Function(double pct);

class FfmpegRunner {
  // Mux video-only + audio-only into a single mp4. Stream-copies if compatible,
  // otherwise re-encodes audio to AAC. Returns merged path.
  static Future<String> mux(String videoPath, String audioPath) async {
    final dir = p.dirname(videoPath);
    // The parts arrive as "<title> [id].video.<ext>" and ".audio.<ext>" (videl_dl.py),
    // so the merged file can take the plain name without overwriting either.
    final base = p.basenameWithoutExtension(videoPath).replaceFirst(RegExp(r'\.video$'), '');
    final out = p.join(dir, '$base.mp4');
    // Try copy-only first (works when audio is AAC/m4a). Falls back to re-encode.
    final isM4a = audioPath.toLowerCase().endsWith('.m4a');
    final aCodec = isM4a ? 'copy' : 'aac';
    final cmd =
        '-y -i "$videoPath" -i "$audioPath" -c:v copy -c:a $aCodec -shortest "$out"';
    final session = await FFmpegKit.execute(cmd);
    final rc = await session.getReturnCode();
    if (!ReturnCode.isSuccess(rc)) {
      throw Exception(
          'mux failed: ${await session.getAllLogsAsString()}');
    }
    return out;
  }

  // Run an arbitrary FFmpeg command. cmd uses %input/%output placeholders OR pass full command.
  static Future<void> run(String cmd,
      {double durationSec = 0, ProgressCb? onProgress}) async {
    FFmpegKitConfig.enableStatisticsCallback((Statistics s) {
      if (durationSec <= 0 || onProgress == null) return;
      final pct = (s.getTime() / 1000.0) / durationSec * 100.0;
      onProgress(pct.clamp(0, 100).toDouble());
    });
    final session = await FFmpegKit.execute(cmd);
    final rc = await session.getReturnCode();
    if (!ReturnCode.isSuccess(rc)) {
      throw Exception('ffmpeg failed: ${await session.getAllLogsAsString()}');
    }
  }

  // Probe duration (seconds) via FFprobe.
  static Future<double> duration(String input) async {
    final session = await FFmpegKit.execute(
        '-i "$input" -hide_banner -f null -');
    final logs = await session.getAllLogsAsString() ?? '';
    final m = RegExp(r'Duration: (\d+):(\d+):(\d+\.\d+)').firstMatch(logs);
    if (m == null) return 0;
    return int.parse(m.group(1)!) * 3600 +
        int.parse(m.group(2)!) * 60 +
        double.parse(m.group(3)!);
  }

  // Trim a video/audio file to [startSec, endSec]. Stream-copy — no re-encode.
  // Returns the trimmed output path.
  static Future<String> trim(String input, double startSec, double endSec) async {
    final dir = p.dirname(input);
    final base = p.basenameWithoutExtension(input);
    final ext = p.extension(input);
    final ss = startSec.toInt();
    final to = endSec.toInt();
    final out = p.join(dir, '${base}_trim_${ss}s_${to}s$ext');
    final cmd = '-y -ss $ss -to $to -i "$input" -c copy "$out"';
    final session = await FFmpegKit.execute(cmd);
    final rc = await session.getReturnCode();
    if (!ReturnCode.isSuccess(rc)) {
      throw Exception('trim failed: ${await session.getAllLogsAsString()}');
    }
    return out;
  }

  // Convert any audio file to 192k MP3. Returns mp3 path.
  // MP3 for a Spotify song: named, tagged and given cover art from Spotify, not
  // from the YouTube match. Arguments go as a list, so quotes in titles are safe.
  static Future<String> toTaggedMp3(String src,
      {required String fileName,
      required Map<String, String> tags,
      String? coverPath}) async {
    final out = p.join(p.dirname(src), '$fileName.mp3');
    final hasCover = coverPath != null && coverPath.isNotEmpty && File(coverPath).existsSync();
    final args = <String>[
      '-y', '-i', src,
      if (hasCover) ...['-i', coverPath!],
      '-map', '0:a',
      if (hasCover) ...['-map', '1:v', '-c:v', 'copy', '-disposition:v', 'attached_pic'],
      '-map_metadata', '-1', '-c:a', 'libmp3lame', '-b:a', '192k', '-id3v2_version', '3',
      for (final t in tags.entries)
        if (t.value.isNotEmpty) ...['-metadata', '${t.key}=${t.value}'],
      out,
    ];
    final session = await FFmpegKit.executeWithArguments(args);
    final rc = await session.getReturnCode();
    if (!ReturnCode.isSuccess(rc)) {
      throw Exception('mp3 convert failed: ${await session.getAllLogsAsString()}');
    }
    return out;
  }

  static Future<String> toMp3(String audioPath) async {
    final dir = p.dirname(audioPath);
    final base = p.basenameWithoutExtension(audioPath).replaceFirst(RegExp(r'\.audio$'), '');
    final out = p.join(dir, '$base.mp3');
    final cmd =
        '-y -i "$audioPath" -vn -c:a libmp3lame -b:a 192k "$out"';
    final session = await FFmpegKit.execute(cmd);
    final rc = await session.getReturnCode();
    if (!ReturnCode.isSuccess(rc)) {
      throw Exception(
          'mp3 convert failed: ${await session.getAllLogsAsString()}');
    }
    return out;
  }
}
