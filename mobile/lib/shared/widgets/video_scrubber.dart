import 'dart:io';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../core/theme/videl_theme.dart';

class VidelScrubber extends StatefulWidget {
  const VidelScrubber({
    super.key,
    required this.path,
    required this.onPositionChanged,
  });
  final String path;
  final ValueChanged<Duration> onPositionChanged;

  @override
  State<VidelScrubber> createState() => VidelScrubberState();
}

class VidelScrubberState extends State<VidelScrubber> {
  VideoPlayerController? _vp;
  Duration _pos = Duration.zero;
  Duration _dur = Duration.zero;
  bool _loaded = false;

  Duration get position => _pos;
  Duration get duration => _dur;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void didUpdateWidget(covariant VidelScrubber old) {
    super.didUpdateWidget(old);
    if (old.path != widget.path) {
      _vp?.dispose();
      _loaded = false;
      _init();
    }
  }

  Future<void> _init() async {
    final c = VideoPlayerController.file(File(widget.path));
    await c.initialize();
    c.setVolume(0);
    c.addListener(() {
      if (!mounted) return;
      setState(() => _pos = c.value.position);
      widget.onPositionChanged(c.value.position);
    });
    setState(() {
      _vp = c;
      _dur = c.value.duration;
      _loaded = true;
    });
  }

  @override
  void dispose() {
    _vp?.dispose();
    super.dispose();
  }

  String _hms(Duration d) {
    final s = d.inSeconds;
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final sec = s % 60;
    final t = '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
    return h > 0 ? '$h:$t' : t;
  }

  void _seek(double v) {
    final c = _vp;
    if (c == null) return;
    final pos = Duration(milliseconds: (v * _dur.inMilliseconds).toInt());
    c.seekTo(pos);
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return Container(
        height: 200,
        decoration: BoxDecoration(
          color: VidelColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: VidelColors.border),
        ),
        child: const Center(child: CircularProgressIndicator()),
      );
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      AspectRatio(
        aspectRatio: _vp!.value.aspectRatio,
        child: Container(
          decoration: BoxDecoration(
            color: VidelColors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: VidelColors.border),
          ),
          clipBehavior: Clip.hardEdge,
          child: Stack(children: [
            VideoPlayer(_vp!),
            Positioned.fill(
              child: GestureDetector(
                onTap: () {
                  setState(() {
                    _vp!.value.isPlaying ? _vp!.pause() : _vp!.play();
                  });
                },
                child: AnimatedOpacity(
                  duration: const Duration(milliseconds: 200),
                  opacity: _vp!.value.isPlaying ? 0 : 1,
                  child: Container(
                    color: Colors.black26,
                    child: const Center(
                      child: Icon(Icons.play_circle_fill_rounded,
                          size: 64, color: Colors.white70),
                    ),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Row(children: [
          Text(_hms(_pos),
              style: const TextStyle(fontSize: 11, color: VidelColors.textSecondary)),
          Expanded(
            child: SliderTheme(
              data: SliderThemeData(
                  trackHeight: 3,
                  overlayShape: SliderComponentShape.noOverlay),
              child: Slider(
                value: _dur.inMilliseconds == 0
                    ? 0
                    : (_pos.inMilliseconds / _dur.inMilliseconds)
                        .clamp(0.0, 1.0),
                onChanged: _seek,
              ),
            ),
          ),
          Text(_hms(_dur),
              style:
                  const TextStyle(fontSize: 11, color: VidelColors.textSecondary)),
        ]),
      ),
    ]);
  }
}
