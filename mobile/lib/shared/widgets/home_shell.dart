import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/videl_theme.dart';
import '../../core/update_checker.dart';
import '../../features/bug_reporter/bug_reporter_page.dart';
import '../../features/downloader/downloader_page.dart';
import '../../features/history/history_page.dart';
import '../../features/tools/tools_dashboard.dart';

export '../../core/update_checker.dart' show updateProvider;

enum _Section { home, tools, history }

class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});
  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  _Section _section = _Section.home;

  String _titleOf(_Section s) {
    switch (s) {
      case _Section.home:
        return 'Videl';
      case _Section.tools:
        return 'Tools';
      case _Section.history:
        return 'History';
    }
  }

  Widget _body() {
    switch (_section) {
      case _Section.home:
        return const _HomePage();
      case _Section.tools:
        return const ToolsDashboard();
      case _Section.history:
        return const HistoryPage();
    }
  }

  void _showUpdateSheet(BuildContext context, UpdateInfo info) {
    showModalBottomSheet(
      context: context,
      backgroundColor: VidelColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _UpdateSheet(info: info),
    );
  }

  @override
  Widget build(BuildContext context) {
    final update = ref.watch(updateProvider);

    return Scaffold(
      drawer: _VidelDrawer(
        active: _section,
        onPick: (s) {
          Navigator.pop(context);
          setState(() => _section = s);
        },
      ),
      appBar: AppBar(
        titleSpacing: 8,
        title: Row(children: [
          Container(
            width: 28,
            height: 28,
            clipBehavior: Clip.hardEdge,
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(7)),
            child: Image.asset('assets/videl_icon.png', fit: BoxFit.cover),
          ),
          const SizedBox(width: 12),
          Text(_titleOf(_section),
              style: const TextStyle(
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w700,
                  fontSize: 20)),
        ]),
        actions: [
          if (update.hasUpdate)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _UpdateBadge(
                version: update.info!.latestVersion,
                onTap: () => _showUpdateSheet(context, update.info!),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(child: _body()),
        ],
      ),
    );
  }
}

// ── Update badge in AppBar ─────────────────────────────────────────────────

class _UpdateBadge extends StatelessWidget {
  const _UpdateBadge({required this.version, required this.onTap});
  final String version;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: VidelColors.accent.withOpacity(0.18),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: VidelColors.accent.withOpacity(0.5)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.system_update_rounded,
              size: 13, color: VidelColors.accent),
          const SizedBox(width: 5),
          Text('v$version',
              style: const TextStyle(
                  fontSize: 11,
                  color: VidelColors.accent,
                  fontWeight: FontWeight.w700)),
        ]),
      ),
    );
  }
}

// ── Update bottom sheet ────────────────────────────────────────────────────

class _UpdateSheet extends ConsumerWidget {
  const _UpdateSheet({required this.info});
  final UpdateInfo info;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final updateState = ref.watch(updateProvider);
    final isDownloading = updateState.downloading;
    final progress = updateState.downloadProgress;
    final error = updateState.downloadError;

    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Handle
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: VidelColors.border,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Header
          Row(children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                    colors: [VidelColors.accent, VidelColors.accentPressed]),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.system_update_rounded,
                  size: 24, color: Colors.white),
            ),
            const SizedBox(width: 14),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Update available',
                  style: TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w700)),
              Text('v$kAppVersion  →  v${info.latestVersion}',
                  style: const TextStyle(
                      fontSize: 12, color: VidelColors.textSecondary)),
            ]),
          ]),
          const SizedBox(height: 16),

          // Release notes
          if (info.releaseNotes.isNotEmpty) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: VidelColors.raised,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: VidelColors.border),
              ),
              child: Text(
                info.releaseNotes,
                style: const TextStyle(
                    fontSize: 12,
                    color: VidelColors.textSecondary,
                    height: 1.5),
              ),
            ),
            const SizedBox(height: 14),
          ],

          // Error banner
          if (error != null) ...[
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.red.withOpacity(0.4)),
              ),
              child: Text(
                'Download failed: $error',
                style: const TextStyle(
                    fontSize: 11, color: Colors.redAccent, height: 1.4),
              ),
            ),
            const SizedBox(height: 10),
          ],

          // Progress bar (visible while downloading)
          if (isDownloading) ...[
            Row(children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: progress > 0 ? progress : null,
                    backgroundColor: VidelColors.border,
                    color: VidelColors.accent,
                    minHeight: 6,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                progress > 0
                    ? '${(progress * 100).toStringAsFixed(0)}%'
                    : '…',
                style: const TextStyle(
                    fontSize: 12, color: VidelColors.textSecondary),
              ),
            ]),
            const SizedBox(height: 6),
            const Text(
              'Downloading update…',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: VidelColors.textSecondary),
            ),
            const SizedBox(height: 12),
          ],

          // Download / Install button
          ElevatedButton.icon(
            onPressed: isDownloading
                ? null
                : () {
                    ref.read(updateProvider.notifier).downloadAndInstall();
                  },
            icon: Icon(
              isDownloading
                  ? Icons.hourglass_top_rounded
                  : Icons.download_rounded,
              size: 18,
            ),
            label: Text(
              isDownloading
                  ? 'Downloading…'
                  : error != null
                      ? 'Retry download'
                      : 'Download & Install v${info.latestVersion}',
            ),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
          const SizedBox(height: 8),

          // Skip this version
          TextButton(
            onPressed: isDownloading
                ? null
                : () {
                    Navigator.pop(context);
                    ref
                        .read(updateProvider.notifier)
                        .dismiss(skipVersion: true);
                  },
            child: const Text('Skip this version',
                style: TextStyle(color: VidelColors.textSecondary)),
          ),
        ],
      ),
    );
  }
}

// ── Drawer ─────────────────────────────────────────────────────────────────

class _VidelDrawer extends ConsumerWidget {
  const _VidelDrawer({required this.active, required this.onPick});
  final _Section active;
  final ValueChanged<_Section> onPick;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(updateProvider);

    return Drawer(
      backgroundColor: VidelColors.sidebar,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(children: [
                Container(
                  width: 44,
                  height: 44,
                  clipBehavior: Clip.hardEdge,
                  decoration:
                      BoxDecoration(borderRadius: BorderRadius.circular(12)),
                  child: Image.asset('assets/videl_icon.png',
                      fit: BoxFit.cover),
                ),
                const SizedBox(width: 14),
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Videl',
                        style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 2)),
                    Text('Offline media toolkit',
                        style: TextStyle(
                            color: VidelColors.textSecondary, fontSize: 11)),
                  ],
                ),
              ]),
            ),
            const Divider(height: 1),
            const SizedBox(height: 8),
            _NavItem(
              icon: Icons.home_rounded,
              label: 'Home',
              active: active == _Section.home,
              onTap: () => onPick(_Section.home),
            ),
            _NavItem(
              icon: Icons.apps_rounded,
              label: 'Tools',
              active: active == _Section.tools,
              onTap: () => onPick(_Section.tools),
            ),
            _NavItem(
              icon: Icons.history_rounded,
              label: 'History',
              active: active == _Section.history,
              onTap: () => onPick(_Section.history),
            ),
            _NavItem(
              icon: Icons.bug_report_rounded,
              label: 'Report a Bug',
              active: false,
              onTap: () {
                Navigator.pop(context);
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const BugReporterPage()),
                );
              },
            ),
            // Update nav item (shown only when update available)
            if (update.hasUpdate)
              _NavItem(
                icon: Icons.system_update_rounded,
                label: 'Update v${update.info!.latestVersion}',
                active: false,
                accent: true,
                onTap: () {
                  Navigator.pop(context);
                  showModalBottomSheet(
                    context: context,
                    backgroundColor: VidelColors.surface,
                    shape: const RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.vertical(top: Radius.circular(20)),
                    ),
                    builder: (_) => _UpdateSheet(info: update.info!),
                  );
                },
              ),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                'v$kAppVersion',
                style: const TextStyle(
                    color: VidelColors.textMuted, fontSize: 11),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.active,
    required this.onTap,
    this.accent = false,
  });
  final IconData icon;
  final String label;
  final bool active;
  final bool accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = accent
        ? VidelColors.accent
        : active
            ? VidelColors.accent
            : VidelColors.textSecondary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: active
            ? VidelColors.accent.withOpacity(0.15)
            : accent
                ? VidelColors.accent.withOpacity(0.08)
                : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(children: [
              Icon(icon, size: 20, color: color),
              const SizedBox(width: 14),
              Expanded(
                child: Text(label,
                    style: TextStyle(
                        color: (active || accent)
                            ? VidelColors.accent
                            : VidelColors.textPrimary,
                        fontWeight: (active || accent)
                            ? FontWeight.w700
                            : FontWeight.w500)),
              ),
              if (accent)
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: VidelColors.accent,
                    shape: BoxShape.circle,
                  ),
                ),
            ]),
          ),
        ),
      ),
    );
  }
}

// ── Home page ──────────────────────────────────────────────────────────────

class _HomePage extends StatelessWidget {
  const _HomePage();
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        _HeroCard(
          icon: Icons.cloud_download_rounded,
          title: 'Downloader',
          subtitle: 'yt-dlp · video & MP3',
          onTap: () => Navigator.push(context,
              MaterialPageRoute(builder: (_) => const DownloaderPage())),
        ),
        const SizedBox(height: 14),
        const _InfoBlurb(
          icon: Icons.apps_rounded,
          title: 'All tools live in the Tools tab',
          body:
              'Open the drawer (☰) → Tools to access Trim, Crop, Compress, Convert, Merge, GIF, Frame Grab, Hex Palette and more.',
        ),
        const SizedBox(height: 10),
        const _InfoBlurb(
          icon: Icons.history_rounded,
          title: 'History',
          body:
              'Every job is logged. Last 30 entries are kept; older ones are pruned automatically.',
        ),
      ]),
    );
  }
}

class _InfoBlurb extends StatelessWidget {
  const _InfoBlurb(
      {required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: VidelColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: VidelColors.border),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 22, color: VidelColors.accent),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.w700, fontSize: 14)),
            const SizedBox(height: 4),
            Text(body,
                style: const TextStyle(
                    color: VidelColors.textSecondary,
                    fontSize: 12,
                    height: 1.45)),
          ]),
        ),
      ]),
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            VidelColors.accent.withOpacity(0.25),
            VidelColors.surface,
          ],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: VidelColors.border),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [
                    VidelColors.accent,
                    VidelColors.accentPressed
                  ]),
                  borderRadius: BorderRadius.circular(15),
                  boxShadow: [
                    BoxShadow(
                      color: VidelColors.accent.withOpacity(0.5),
                      blurRadius: 20,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Icon(icon, size: 28, color: Colors.white),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w800)),
                    Text(subtitle,
                        style: const TextStyle(
                            color: VidelColors.textSecondary, fontSize: 13)),
                  ],
                ),
              ),
              const Icon(Icons.arrow_forward_rounded,
                  color: VidelColors.accent),
            ]),
          ),
        ),
      ),
    );
  }
}
