import 'package:flutter/material.dart';
import 'package:videl_pro_mobile/videl_pro_mobile.dart';

/// Run [check] (a Pro.gate call); on [ProRequired] explain why and offer the
/// License page. Returns false when the job must not start.
Future<bool> proAllows(BuildContext context, Future<void> Function() check) async {
  try {
    await check();
    return true;
  } on ProRequired catch (e) {
    if (!context.mounted) return false;
    final page = Pro.licensePage();
    final get = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Videl Pro'),
        content: Text(e.message),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          if (page != null)
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Get Pro')),
        ],
      ),
    );
    if (get == true && page != null && context.mounted) {
      await Navigator.push(context, MaterialPageRoute(builder: (_) => page));
    }
    return false;
  }
}

/// Bumped after every counted job, so each FreeRunsHint reads the count again.
final jobsCounted = ValueNotifier<int>(0);

/// Before every job (the Downloader excepted): one of today's free jobs, or no
/// limit with Pro. [files] is how many a batch has. False when it must not start.
Future<bool> jobAllowed(BuildContext context, {int files = 1}) async {
  final ok = await proAllows(context, () => Pro.gate('job', files: files));
  if (ok) jobsCounted.value++;
  return ok;
}

/// "Free: 7 of 10 jobs left today" under a tool's button; nothing with Pro.
/// Reads the count again whenever a job is counted (jobsCounted).
class FreeRunsHint extends StatefulWidget {
  const FreeRunsHint({super.key});
  @override
  State<FreeRunsHint> createState() => _FreeRunsHintState();
}

class _FreeRunsHintState extends State<FreeRunsHint> {
  late Future<String?> _label = Pro.freeRunsLabel();

  void _reread() => setState(() => _label = Pro.freeRunsLabel());

  @override
  void initState() {
    super.initState();
    jobsCounted.addListener(_reread);
  }

  @override
  void dispose() {
    jobsCounted.removeListener(_reread);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: _label,
      builder: (ctx, snap) => snap.data == null
          ? const SizedBox.shrink()
          : Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(snap.data!,
                  style: TextStyle(color: Theme.of(ctx).hintColor, fontSize: 12)),
            ),
    );
  }
}
