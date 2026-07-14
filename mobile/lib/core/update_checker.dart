import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _apiUrl =
    'https://api.github.com/repos/darknessth22/media-utilities/releases/latest';
const _apkAssetName = 'videl-android-arm64-v8a.apk';

// Current build version — must stay in sync with pubspec.yaml version field.
const kAppVersion = '4.2.20';

const _prefSkipKey = 'update_skip_version';

const _installChannel = MethodChannel('videl/python');

class UpdateInfo {
  const UpdateInfo({
    required this.latestVersion,
    required this.apkUrl,
    required this.releaseNotes,
  });
  final String latestVersion;
  final String apkUrl;
  final String releaseNotes;
}

class UpdateState {
  const UpdateState({
    this.info,
    this.dismissed = false,
    this.checking = false,
    this.downloading = false,
    this.downloadProgress = 0.0,
    this.downloadError,
  });
  final UpdateInfo? info;
  final bool dismissed;
  final bool checking;
  final bool downloading;
  final double downloadProgress; // 0.0 – 1.0
  final String? downloadError;

  bool get hasUpdate => info != null && !dismissed;

  UpdateState copyWith({
    UpdateInfo? info,
    bool? dismissed,
    bool? checking,
    bool? downloading,
    double? downloadProgress,
    Object? downloadError = _sentinel,
  }) =>
      UpdateState(
        info: info ?? this.info,
        dismissed: dismissed ?? this.dismissed,
        checking: checking ?? this.checking,
        downloading: downloading ?? this.downloading,
        downloadProgress: downloadProgress ?? this.downloadProgress,
        downloadError: downloadError == _sentinel
            ? this.downloadError
            : downloadError as String?,
      );
}

// Sentinel so copyWith can null-out downloadError explicitly.
const _sentinel = Object();

class UpdateNotifier extends Notifier<UpdateState> {
  @override
  UpdateState build() => const UpdateState();

  Future<void> check() async {
    state = state.copyWith(checking: true);
    try {
      final prefs = await SharedPreferences.getInstance();
      final skipped = prefs.getString(_prefSkipKey);

      final resp = await http
          .get(Uri.parse(_apiUrl),
              headers: {'Accept': 'application/vnd.github+json'})
          .timeout(const Duration(seconds: 8));

      if (resp.statusCode != 200) return;

      final json = jsonDecode(resp.body) as Map<String, dynamic>;
      final tag = (json['tag_name'] as String? ?? '').replaceAll(RegExp(r'^v'), '');
      if (tag.isEmpty) return;

      if (!_isNewer(tag, kAppVersion)) return;
      if (tag == skipped) return;

      final assets = (json['assets'] as List? ?? []);
      final asset = assets.cast<Map<String, dynamic>>().firstWhere(
            (a) => (a['name'] as String?) == _apkAssetName,
            orElse: () => {},
          );
      final apkUrl = asset['browser_download_url'] as String? ?? '';
      if (apkUrl.isEmpty) return;

      final body = json['body'] as String? ?? '';
      state = state.copyWith(
        checking: false,
        info: UpdateInfo(
          latestVersion: tag,
          apkUrl: apkUrl,
          releaseNotes: body.length > 300 ? '${body.substring(0, 300)}…' : body,
        ),
      );
    } catch (_) {
      // silent fail — update check is non-critical
    } finally {
      if (state.checking) state = state.copyWith(checking: false);
    }
  }

  Future<void> downloadAndInstall() async {
    final info = state.info;
    if (info == null) return;

    state = state.copyWith(
      downloading: true,
      downloadProgress: 0.0,
      downloadError: null,
    );

    try {
      final cacheDir = await getTemporaryDirectory();
      final apkFile = File('${cacheDir.path}/videl-update-${info.latestVersion}.apk');

      // Stream download with progress
      final client = http.Client();
      try {
        final request = http.Request('GET', Uri.parse(info.apkUrl));
        final response = await client.send(request);

        if (response.statusCode != 200) {
          state = state.copyWith(
            downloading: false,
            downloadError: 'Server returned ${response.statusCode}',
          );
          return;
        }

        final total = response.contentLength ?? 0;
        int received = 0;

        final sink = apkFile.openWrite();
        await for (final chunk in response.stream) {
          sink.add(chunk);
          received += chunk.length;
          if (total > 0) {
            state = state.copyWith(
              downloadProgress: received / total,
            );
          }
        }
        await sink.flush();
        await sink.close();
      } finally {
        client.close();
      }

      state = state.copyWith(downloading: false, downloadProgress: 1.0);

      // Trigger system install prompt via native channel
      await _installChannel.invokeMethod<bool>(
        'install_apk',
        {'path': apkFile.path},
      );
    } catch (e) {
      state = state.copyWith(
        downloading: false,
        downloadError: e.toString(),
      );
    }
  }

  Future<void> dismiss({bool skipVersion = false}) async {
    if (skipVersion && state.info != null) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefSkipKey, state.info!.latestVersion);
    }
    state = state.copyWith(dismissed: true);
  }
}

bool _isNewer(String remote, String local) {
  try {
    final r = _parse(remote);
    final l = _parse(local);
    for (var i = 0; i < 3; i++) {
      if (r[i] > l[i]) return true;
      if (r[i] < l[i]) return false;
    }
    return false;
  } catch (_) {
    return false;
  }
}

List<int> _parse(String v) {
  final clean = v.split('-').first;
  final parts = clean.split('.').map((p) => int.tryParse(p) ?? 0).toList();
  while (parts.length < 3) parts.add(0);
  return parts;
}

final updateProvider =
    NotifierProvider<UpdateNotifier, UpdateState>(UpdateNotifier.new);
