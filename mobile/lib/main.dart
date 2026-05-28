import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/videl_theme.dart';
import 'core/native_bridges/python_runner.dart';
import 'features/downloader/downloader_page.dart';
import 'features/onboarding/onboarding_page.dart';
import 'shared/widgets/home_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: VidelApp()));
}

final _navKey = GlobalKey<NavigatorState>();

class VidelApp extends StatefulWidget {
  const VidelApp({super.key});
  @override
  State<VidelApp> createState() => _VidelAppState();
}

class _VidelAppState extends State<VidelApp> {
  bool? _needsOnboarding;

  @override
  void initState() {
    super.initState();
    shouldShowOnboarding().then((v) {
      if (mounted) setState(() => _needsOnboarding = v);
    });
    _handlePending();
    ShareBridge.incoming().listen(_openDownloader);
  }

  Future<void> _handlePending() async {
    final url = await ShareBridge.pending();
    if (url != null && url.isNotEmpty) _openDownloader(url);
  }

  void _openDownloader(String url) {
    final nav = _navKey.currentState;
    if (nav == null) return;
    nav.push(MaterialPageRoute(
        builder: (_) => DownloaderPage(initialUrl: url, autoFetch: true)));
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Videl',
      debugShowCheckedModeBanner: false,
      navigatorKey: _navKey,
      theme: buildVidelTheme(),
      builder: (ctx, child) => VidelBackdrop(child: child ?? const SizedBox()),
      home: _needsOnboarding == null
          ? const SizedBox()
          : _needsOnboarding!
              ? OnboardingPage(
                  onDone: () => setState(() => _needsOnboarding = false))
              : const HomeShell(),
    );
  }
}
