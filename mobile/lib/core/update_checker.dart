import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

const _apiUrl =
    'https://api.github.com/repos/darknessth22/media-utilities/releases/latest';
const _apkAssetName = 'videl-android-arm64-v8a.apk';

// Current build version — must stay in sync with pubspec.yaml version field.
const kAppVersion = '4.2.12';

const _prefSkipKey = 'update_skip_version';

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
  });
  final UpdateInfo? info;
  final bool dismissed;
  final bool checking;

  bool get hasUpdate => info != null && !dismissed;

  UpdateState copyWith({UpdateInfo? info, bool? dismissed, bool? checking}) =>
      UpdateState(
        info: info ?? this.info,
        dismissed: dismissed ?? this.dismissed,
        checking: checking ?? this.checking,
      );
}

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

      // Compare versions — skip if latest <= current or user dismissed this tag
      if (!_isNewer(tag, kAppVersion)) return;
      if (tag == skipped) return;

      // Find APK asset URL
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
  final clean = v.split('-').first; // strip "-rc1" etc.
  final parts = clean.split('.').map((p) => int.tryParse(p) ?? 0).toList();
  while (parts.length < 3) parts.add(0);
  return parts;
}

final updateProvider =
    NotifierProvider<UpdateNotifier, UpdateState>(UpdateNotifier.new);
