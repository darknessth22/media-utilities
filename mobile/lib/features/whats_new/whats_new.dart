// What's new: the only place the app shows its version. The notes are
// mobile/assets/changelog.json, newest first ({version, date, en: [...]}),
// separate from the desktop's assets/changelog.json because the phone has its
// own features and releases.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/theme/videl_theme.dart';
import '../../core/update_checker.dart' show kAppVersion;
import '../onboarding/onboarding_page.dart' show shouldShowOnboarding;

class Release {
  const Release(this.version, this.date, this.notes);
  final String version;
  final String date;
  final List<String> notes;
}

List<Release> parseChangelog(String json) => [
      for (final e in jsonDecode(json) as List)
        Release(e['version'] as String, (e['date'] ?? '') as String,
            List<String>.from(e['en'] as List)),
    ];

Future<List<Release>> loadChangelog() async =>
    parseChangelog(await rootBundle.loadString('assets/changelog.json'));

const _kSeen = 'seen_version';

/// Before the first frame: a fresh install (onboarding not done yet) records
/// this version, so its notes never pop up on top of the welcome screens.
/// Installs from before 5.3.0 have no record but finished onboarding, so they
/// count as an update.
Future<void> recordFreshInstall() async {
  final p = await SharedPreferences.getInstance();
  if (p.getString(_kSeen) == null && await shouldShowOnboarding()) {
    await p.setString(_kSeen, kAppVersion);
  }
}

/// After an update, this version's notes once.
Future<void> maybeShowWhatsNew(BuildContext context) async {
  final p = await SharedPreferences.getInstance();
  if (p.getString(_kSeen) == kAppVersion) return;
  await p.setString(_kSeen, kAppVersion);
  final all = await loadChangelog();
  if (context.mounted && all.any((r) => r.version == kAppVersion)) {
    showWhatsNew(context, all: all);
  }
}

/// This version's notes in a sheet, with See more for every version.
Future<void> showWhatsNew(BuildContext context, {List<Release>? all}) async {
  all ??= await loadChangelog();
  if (!context.mounted || all.isEmpty) return;
  final list = all;
  final current = list.firstWhere((r) => r.version == kAppVersion, orElse: () => list.first);
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: VidelColors.surface,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (ctx) => ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.8),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                      color: VidelColors.border, borderRadius: BorderRadius.circular(2)),
                ),
              ),
              const SizedBox(height: 16),
              Row(children: [
                const Icon(Icons.auto_awesome_rounded, color: VidelColors.accent, size: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Text("What's new in Videl ${current.version}",
                      style: videlDisplay(size: 20)),
                ),
              ]),
              const SizedBox(height: 12),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(children: [for (final n in current.notes) _Bullet(n)]),
                ),
              ),
              const SizedBox(height: 12),
              Row(children: [
                if (list.length > 1)
                  TextButton(
                    onPressed: () {
                      Navigator.pop(ctx);
                      Navigator.push(context,
                          MaterialPageRoute(builder: (_) => WhatsNewPage(releases: list)));
                    },
                    child: const Text('See more'),
                  ),
                const Spacer(),
                ElevatedButton(onPressed: () => Navigator.pop(ctx), child: const Text('Got it')),
              ]),
            ],
          ),
        ),
      ),
    ),
  );
}

/// Every version, newest first.
class WhatsNewPage extends StatelessWidget {
  const WhatsNewPage({super.key, this.releases});
  final List<Release>? releases;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("What's new")),
      body: releases != null
          ? _list(releases!)
          : FutureBuilder<List<Release>>(
              future: loadChangelog(),
              builder: (_, s) => s.hasData
                  ? _list(s.data!)
                  : const Center(child: CircularProgressIndicator()),
            ),
    );
  }

  Widget _list(List<Release> all) => ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        itemCount: all.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (_, i) {
          final r = all[i];
          final mine = r.version == kAppVersion;
          return Container(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
            decoration: BoxDecoration(
              color: VidelColors.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: mine ? VidelColors.accent : VidelColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text('Version ${r.version}', style: videlDisplay(size: 17)),
                    if (mine)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: VidelColors.accent.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Text('This version',
                            style: TextStyle(
                                fontSize: 11,
                                color: VidelColors.accentLight,
                                fontWeight: FontWeight.w700)),
                      ),
                    if (r.date.isNotEmpty)
                      Text(r.date,
                          style: const TextStyle(fontSize: 12, color: VidelColors.textMuted)),
                  ],
                ),
                const SizedBox(height: 6),
                for (final n in r.notes) _Bullet(n),
              ],
            ),
          );
        },
      );
}

class _Bullet extends StatelessWidget {
  const _Bullet(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Padding(
          padding: EdgeInsets.only(top: 7, right: 10),
          child: CircleAvatar(radius: 2.5, backgroundColor: VidelColors.accent),
        ),
        Expanded(
          child: Text(text,
              style: const TextStyle(
                  fontSize: 14, height: 1.45, color: VidelColors.textSecondary)),
        ),
      ]),
    );
  }
}
