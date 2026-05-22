import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/theme/videl_theme.dart';

const _kSeenKey = 'onboarding_seen_v1';

Future<bool> shouldShowOnboarding() async {
  final p = await SharedPreferences.getInstance();
  return !(p.getBool(_kSeenKey) ?? false);
}

Future<void> markOnboardingSeen() async {
  final p = await SharedPreferences.getInstance();
  await p.setBool(_kSeenKey, true);
}

class OnboardingPage extends StatefulWidget {
  const OnboardingPage({super.key, required this.onDone});
  final VoidCallback onDone;

  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  final _pc = PageController();
  int _i = 0;

  final _slides = const [
    _Slide(
      icon: Icons.cloud_download_rounded,
      title: 'Universal Downloader',
      body:
          'Grab videos and audio from YouTube, TikTok, Instagram, X, Facebook and 1000+ sites — all offline, no accounts.',
    ),
    _Slide(
      icon: Icons.high_quality_rounded,
      title: 'Any Quality, Any Format',
      body:
          'Pick from every available stream. 4K MP4 with merged audio, 192kbps MP3 — handled on-device with FFmpeg.',
    ),
    _Slide(
      icon: Icons.share_rounded,
      title: 'Share & Go',
      body:
          'Copy a URL or share from any app — Videl appears in the share sheet and auto-fills your link.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: PageView.builder(
              controller: _pc,
              itemCount: _slides.length,
              onPageChanged: (i) => setState(() => _i = i),
              itemBuilder: (_, i) => _slides[i],
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(_slides.length, (i) {
              final active = i == _i;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.symmetric(horizontal: 4),
                width: active ? 22 : 7,
                height: 7,
                decoration: BoxDecoration(
                  color: active ? VidelColors.accent : VidelColors.border,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () async {
                  if (_i < _slides.length - 1) {
                    _pc.nextPage(
                        duration: const Duration(milliseconds: 280),
                        curve: Curves.easeOut);
                  } else {
                    await markOnboardingSeen();
                    widget.onDone();
                  }
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text(_i == _slides.length - 1
                      ? 'Get Started'
                      : 'Continue'),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Slide extends StatelessWidget {
  const _Slide({required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [VidelColors.accent, VidelColors.accentPressed],
              ),
              borderRadius: BorderRadius.circular(28),
              boxShadow: [
                BoxShadow(
                  color: VidelColors.accent.withOpacity(0.4),
                  blurRadius: 30,
                  offset: const Offset(0, 12),
                ),
              ],
            ),
            child: Icon(icon, size: 60, color: Colors.white),
          ),
          const SizedBox(height: 36),
          Text(title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.3)),
          const SizedBox(height: 14),
          Text(body,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: VidelColors.textSecondary,
                  fontSize: 15,
                  height: 1.5)),
        ],
      ),
    );
  }
}
