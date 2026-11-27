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

/// "Pro: 3 of 5 free runs left today" under a batch picker; nothing with Pro.
/// Reads the count once; give it a new key after a counted run to read it again
/// (a const or same-key hint would keep showing the old number).
class FreeRunsHint extends StatefulWidget {
  const FreeRunsHint({super.key});
  @override
  State<FreeRunsHint> createState() => _FreeRunsHintState();
}

class _FreeRunsHintState extends State<FreeRunsHint> {
  late final Future<String?> _label = Pro.freeRunsLabel();

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
