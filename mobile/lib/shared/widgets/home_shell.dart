import 'package:flutter/material.dart';

import '../../core/theme/videl_theme.dart';
import '../../features/downloader/downloader_page.dart';
import '../../features/history/history_page.dart';
import '../../features/tools/tools_dashboard.dart';

enum _Section { home, tools, history }

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
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

  @override
  Widget build(BuildContext context) {
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
      ),
      body: _body(),
    );
  }
}

class _VidelDrawer extends StatelessWidget {
  const _VidelDrawer({required this.active, required this.onPick});
  final _Section active;
  final ValueChanged<_Section> onPick;

  @override
  Widget build(BuildContext context) {
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
            const Spacer(),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('v0.1.0',
                  style:
                      TextStyle(color: VidelColors.textMuted, fontSize: 11)),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem(
      {required this.icon,
      required this.label,
      required this.active,
      required this.onTap});
  final IconData icon;
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color:
            active ? VidelColors.accent.withOpacity(0.15) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(children: [
              Icon(icon,
                  size: 20,
                  color: active
                      ? VidelColors.accent
                      : VidelColors.textSecondary),
              const SizedBox(width: 14),
              Text(label,
                  style: TextStyle(
                      color: active
                          ? VidelColors.accent
                          : VidelColors.textPrimary,
                      fontWeight:
                          active ? FontWeight.w700 : FontWeight.w500)),
            ]),
          ),
        ),
      ),
    );
  }
}

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
