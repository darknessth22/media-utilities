import 'package:flutter/material.dart';

import '../../core/recent_jobs.dart';
import '../../core/theme/videl_theme.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key});
  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  List<RecentJob> _jobs = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final j = await RecentJobs.all();
    if (mounted) setState(() => _jobs = j);
  }

  String _ago(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'just now';
    if (d.inMinutes < 60) return '${d.inMinutes}m';
    if (d.inHours < 24) return '${d.inHours}h';
    return '${d.inDays}d';
  }

  @override
  Widget build(BuildContext context) {
    if (_jobs.isEmpty) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.history_rounded, size: 56, color: VidelColors.border),
          SizedBox(height: 12),
          Text('No jobs yet',
              style: TextStyle(color: VidelColors.textSecondary)),
        ]),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _jobs.length,
        itemBuilder: (_, i) {
          final j = _jobs[i];
          final ok = j.status == 'success';
          return Container(
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: VidelColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: VidelColors.border),
            ),
            child: ListTile(
              leading: CircleAvatar(
                radius: 18,
                backgroundColor:
                    (ok ? VidelColors.success : VidelColors.error)
                        .withOpacity(0.2),
                child: Icon(
                  ok ? Icons.check_rounded : Icons.close_rounded,
                  size: 18,
                  color: ok ? VidelColors.success : VidelColors.error,
                ),
              ),
              title: Text(j.tool.toUpperCase(),
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 13)),
              subtitle: Text(
                ok ? j.output.split('/').last : j.input.split('/').last,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: VidelColors.textSecondary, fontSize: 12),
              ),
              trailing: Text(_ago(j.createdAt ?? DateTime.now()),
                  style: const TextStyle(
                      color: VidelColors.textMuted, fontSize: 11)),
            ),
          );
        },
      ),
    );
  }
}
