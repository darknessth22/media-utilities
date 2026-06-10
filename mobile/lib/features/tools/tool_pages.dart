import 'dart:io';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_colorpicker/flutter_colorpicker.dart';
import 'package:image/image.dart' as img;
import 'package:path/path.dart' as p;
import 'package:permission_handler/permission_handler.dart';
import 'package:video_player/video_player.dart';

import '../../core/native_bridges/ffmpeg_runner.dart';
import '../../core/native_bridges/python_runner.dart';
import '../../core/recent_jobs.dart';
import '../../core/theme/videl_theme.dart';
import '../../shared/widgets/tool_shell.dart';
import '../../shared/widgets/video_scrubber.dart';

// ────────────────────────────────────────────────────────────────────────
// Helpers

String _hms(int s) {
  final h = s ~/ 3600;
  final m = (s % 3600) ~/ 60;
  final sec = s % 60;
  final ts = '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  return h > 0 ? '$h:$ts' : ts;
}

// ────────────────────────────────────────────────────────────────────────
// TRIM

const _audioExts = {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'opus', 'wma'};
const _videoExts = {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv', 'ts', 'm4v'};

bool _isAudioFile(String path) =>
    _audioExts.contains(p.extension(path).toLowerCase().replaceFirst('.', ''));

// ── Trim range bar ────────────────────────────────────────────────────────────
// Shows a draggable start/end handle over the full duration.
class _TrimRangeBar extends StatefulWidget {
  const _TrimRangeBar({
    required this.durationSec,
    required this.startSec,
    required this.endSec,
    required this.currentSec,
    required this.onStartChanged,
    required this.onEndChanged,
  });
  final double durationSec;
  final double startSec;
  final double endSec;
  final double currentSec;
  final ValueChanged<double> onStartChanged;
  final ValueChanged<double> onEndChanged;

  @override
  State<_TrimRangeBar> createState() => _TrimRangeBarState();
}

class _TrimRangeBarState extends State<_TrimRangeBar> {
  static const _handleW = 18.0;
  static const _barH = 36.0;

  double _clamp(double v) => v.clamp(0.0, widget.durationSec);

  @override
  Widget build(BuildContext context) {
    if (widget.durationSec <= 0) return const SizedBox(height: _barH);
    return LayoutBuilder(builder: (ctx, box) {
      final trackW = box.maxWidth - _handleW * 2;
      final startFrac = (widget.startSec / widget.durationSec).clamp(0.0, 1.0);
      final endFrac = (widget.endSec / widget.durationSec).clamp(0.0, 1.0);
      final curFrac = (widget.currentSec / widget.durationSec).clamp(0.0, 1.0);

      return SizedBox(
        height: _barH,
        child: Stack(alignment: Alignment.centerLeft, children: [
          // Full track background
          Positioned(
            left: _handleW / 2,
            right: _handleW / 2,
            child: Container(
              height: 6,
              decoration: BoxDecoration(
                color: VidelColors.border,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
          // Selected region highlight
          Positioned(
            left: _handleW / 2 + startFrac * trackW,
            width: (endFrac - startFrac) * trackW,
            child: Container(
              height: 6,
              color: VidelColors.accent.withOpacity(0.55),
            ),
          ),
          // Playhead
          Positioned(
            left: _handleW / 2 + curFrac * trackW - 1,
            child: Container(width: 2, height: _barH, color: Colors.white54),
          ),
          // Start handle
          Positioned(
            left: startFrac * trackW,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onHorizontalDragUpdate: (d) {
                final newFrac = ((startFrac * trackW + d.delta.dx) / trackW)
                    .clamp(0.0, endFrac - 0.01);
                widget.onStartChanged(
                    _clamp(newFrac * widget.durationSec));
              },
              child: _Handle(icon: Icons.chevron_right_rounded),
            ),
          ),
          // End handle
          Positioned(
            left: endFrac * trackW,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onHorizontalDragUpdate: (d) {
                final newFrac = ((endFrac * trackW + d.delta.dx) / trackW)
                    .clamp(startFrac + 0.01, 1.0);
                widget.onEndChanged(
                    _clamp(newFrac * widget.durationSec));
              },
              child: _Handle(icon: Icons.chevron_left_rounded),
            ),
          ),
        ]),
      );
    });
  }
}

class _Handle extends StatelessWidget {
  const _Handle({required this.icon});
  final IconData icon;
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 18,
      height: 36,
      decoration: BoxDecoration(
        color: VidelColors.accent,
        borderRadius: BorderRadius.circular(5),
      ),
      child: Icon(icon, size: 14, color: Colors.white),
    );
  }
}

// ── Audio-only player card ────────────────────────────────────────────────────
class _AudioPlayer extends StatefulWidget {
  const _AudioPlayer({super.key, required this.path, required this.onPositionChanged});
  final String path;
  final ValueChanged<Duration> onPositionChanged;
  @override
  State<_AudioPlayer> createState() => _AudioPlayerState();
}

class _AudioPlayerState extends State<_AudioPlayer> {
  VideoPlayerController? _vp; // video_player handles audio too
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
  void didUpdateWidget(covariant _AudioPlayer old) {
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
    c.setVolume(1.0);
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

  String _fmt(Duration d) {
    final s = d.inSeconds;
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final sec = s % 60;
    final t =
        '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
    return h > 0 ? '$h:$t' : t;
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return Container(
        height: 80,
        decoration: BoxDecoration(
          color: VidelColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: VidelColors.border),
        ),
        child: const Center(child: CircularProgressIndicator()),
      );
    }
    final playing = _vp?.value.isPlaying ?? false;
    final frac = _dur.inMilliseconds == 0
        ? 0.0
        : (_pos.inMilliseconds / _dur.inMilliseconds).clamp(0.0, 1.0);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: VidelColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: VidelColors.border),
      ),
      child: Column(children: [
        // Waveform placeholder + play button row
        Row(children: [
          IconButton(
            onPressed: () => playing ? _vp!.pause() : _vp!.play(),
            icon: Icon(
              playing
                  ? Icons.pause_circle_filled_rounded
                  : Icons.play_circle_filled_rounded,
              size: 40,
              color: VidelColors.accent,
            ),
            padding: EdgeInsets.zero,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Simple waveform bar (visual placeholder — real waveform
                  // would need ffmpeg thumbnail extraction)
                  _WaveformBar(progress: frac),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_fmt(_pos),
                          style: const TextStyle(
                              fontSize: 10,
                              color: VidelColors.textSecondary,
                              fontFamily: 'monospace')),
                      Text(_fmt(_dur),
                          style: const TextStyle(
                              fontSize: 10,
                              color: VidelColors.textSecondary,
                              fontFamily: 'monospace')),
                    ],
                  ),
                ]),
          ),
        ]),
        // Scrub slider
        SliderTheme(
          data: SliderThemeData(
              trackHeight: 2,
              overlayShape: SliderComponentShape.noOverlay,
              thumbShape:
                  const RoundSliderThumbShape(enabledThumbRadius: 6)),
          child: Slider(
            value: frac,
            onChanged: (v) {
              final pos =
                  Duration(milliseconds: (v * _dur.inMilliseconds).toInt());
              _vp?.seekTo(pos);
            },
          ),
        ),
      ]),
    );
  }
}

class _WaveformBar extends StatelessWidget {
  const _WaveformBar({required this.progress});
  final double progress;
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (_, box) {
      const barCount = 40;
      final barW = (box.maxWidth - barCount * 2) / barCount;
      final playedBars = (progress * barCount).round();
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: List.generate(barCount, (i) {
          // Pseudo-random heights for visual variety (deterministic)
          final h = 8.0 + 16.0 * (0.4 + 0.6 * math.sin(i * 1.3 + i * 0.7).abs());
          return Container(
            width: barW,
            height: h,
            margin: const EdgeInsets.symmetric(horizontal: 1),
            decoration: BoxDecoration(
              color: i < playedBars
                  ? VidelColors.accent
                  : VidelColors.border,
              borderRadius: BorderRadius.circular(2),
            ),
          );
        }),
      );
    });
  }
}

// ── TrimPage ─────────────────────────────────────────────────────────────────

class TrimPage extends StatefulWidget {
  const TrimPage({super.key});
  @override
  State<TrimPage> createState() => _TrimPageState();
}

class _TrimPageState extends State<TrimPage> {
  String? _input;
  bool _isAudio = false;
  Duration _pos = Duration.zero;
  Duration _mediaDur = Duration.zero;
  double _startSec = 0;
  double _endSec = 60;
  bool _busy = false;
  double _pct = 0;
  String _status = 'Pick a video or audio file';

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: [
        ..._videoExts,
        ..._audioExts,
      ],
    );
    if (r == null) return;
    final path = r.files.single.path!;
    final audio = _isAudioFile(path);
    // Probe duration so we can initialise end handle correctly
    final durSec = await FfmpegRunner.duration(path);
    setState(() {
      _input = path;
      _isAudio = audio;
      _pos = Duration.zero;
      _mediaDur = Duration(milliseconds: (durSec * 1000).toInt());
      _startSec = 0;
      _endSec = durSec > 0 ? durSec : 60;
      _status = p.basename(path);
    });
  }

  void _onPositionChanged(Duration d) {
    setState(() => _pos = d);
  }

  Future<void> _run() async {
    if (_input == null) return;
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    final ext = _isAudio
        ? p.extension(_input!).toLowerCase().replaceFirst('.', '')
        : 'mp4';
    final subDir =
        _isAudio ? 'Music/Videl' : 'Movies/Videl';
    final outDir = '/storage/emulated/0/$subDir';
    await Directory(outDir).create(recursive: true);
    final out = p.join(
        outDir, '${p.basenameWithoutExtension(_input!)}_trim.$ext');

    final startInt = _startSec.toInt();
    final endInt = _endSec.toInt();
    final dur = (endInt - startInt).clamp(1, 999999).toDouble();

    // Stream-copy for both audio and video — fast & lossless.
    // For audio the container is preserved so -c copy works for all formats.
    final cmd =
        '-y -ss $startInt -to $endInt -i "$_input" -c copy "$out"';

    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Trimming...';
    });
    await PythonRunner.fgStart();
    String s = 'success';
    try {
      await FfmpegRunner.run(cmd,
          durationSec: dur,
          onProgress: (pp) {
            if (!mounted) return;
            setState(() => _pct = pp);
            PythonRunner.fgUpdate(
                title: 'Trim', text: 'Trimming', pct: pp.toInt());
          });
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      s = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
          tool: 'trim',
          input: _input!,
          output: s == 'success' ? out : '',
          status: s));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final curSec = _pos.inMilliseconds / 1000.0;
    final durSec = _mediaDur.inMilliseconds / 1000.0;

    return Scaffold(
      appBar: AppBar(title: const Text('Trim')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
          // ── Preview area ────────────────────────────────────────────
          if (_input == null)
            Container(
              height: 180,
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              child: const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.cut_rounded, size: 48, color: VidelColors.border),
                    SizedBox(height: 8),
                    Text('Pick a video or audio file',
                        style: TextStyle(color: VidelColors.textMuted)),
                  ],
                ),
              ),
            )
          else if (_isAudio)
            _AudioPlayer(
              path: _input!,
              onPositionChanged: _onPositionChanged,
            )
          else
            VidelScrubber(
              path: _input!,
              onPositionChanged: _onPositionChanged,
            ),

          const SizedBox(height: 12),

          // ── Trim range bar ──────────────────────────────────────────
          if (_input != null) ...[
            _TrimRangeBar(
              durationSec: durSec,
              startSec: _startSec,
              endSec: _endSec,
              currentSec: curSec,
              onStartChanged: (v) => setState(() => _startSec = v),
              onEndChanged: (v) => setState(() => _endSec = v),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_hms(_startSec.toInt()),
                    style: const TextStyle(
                        fontSize: 11,
                        color: VidelColors.accent,
                        fontFamily: 'monospace')),
                Text(
                    'Length: ${_hms((_endSec - _startSec).clamp(0, 999999).toInt())}',
                    style: const TextStyle(
                        fontSize: 11, color: VidelColors.textSecondary)),
                Text(_hms(_endSec.toInt()),
                    style: const TextStyle(
                        fontSize: 11,
                        color: VidelColors.accent,
                        fontFamily: 'monospace')),
              ],
            ),
            const SizedBox(height: 12),
          ],

          // ── File picker ─────────────────────────────────────────────
          OutlinedButton.icon(
            onPressed: _busy ? null : _pick,
            icon: const Icon(Icons.file_open_outlined),
            label: Text(_input == null
                ? 'Pick video / audio'
                : 'Change file'),
          ),
          const SizedBox(height: 12),

          // ── Time cards ──────────────────────────────────────────────
          Row(children: [
            Expanded(
              child: _TimeCard(
                label: 'Start',
                seconds: _startSec.toInt(),
                onUseCurrent: _input == null
                    ? null
                    : () => setState(
                        () => _startSec = curSec.clamp(0, _endSec - 1)),
                onChanged: (v) => setState(
                    () => _startSec = v.toDouble().clamp(0, _endSec - 1)),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _TimeCard(
                label: 'End',
                seconds: _endSec.toInt(),
                onUseCurrent: _input == null
                    ? null
                    : () => setState(() =>
                        _endSec = curSec.clamp(_startSec + 1, durSec)),
                onChanged: (v) => setState(() =>
                    _endSec = v.toDouble().clamp(_startSec + 1, durSec > 0 ? durSec : 999999)),
              ),
            ),
          ]),

          const SizedBox(height: 16),

          // ── Action button ───────────────────────────────────────────
          ElevatedButton.icon(
            onPressed: (_busy || _input == null) ? null : _run,
            icon: const Icon(Icons.content_cut_rounded),
            label: const Text('Trim'),
          ),
          const SizedBox(height: 12),
          if (_busy)
            LinearProgressIndicator(
                value: _pct == 0 ? null : _pct / 100),
          const SizedBox(height: 6),
          Text(_status,
              style:
                  const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

class _TimeCard extends StatelessWidget {
  const _TimeCard({
    required this.label,
    required this.seconds,
    required this.onUseCurrent,
    required this.onChanged,
  });
  final String label;
  final int seconds;
  final VoidCallback? onUseCurrent;
  final ValueChanged<int> onChanged;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: VidelColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: VidelColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(
                color: VidelColors.textSecondary,
                fontSize: 11,
                letterSpacing: 1.2)),
        const SizedBox(height: 4),
        TextFormField(
          key: ValueKey('$label$seconds'),
          initialValue: '$seconds',
          keyboardType: TextInputType.number,
          style: const TextStyle(
              fontWeight: FontWeight.w700, fontFamily: 'monospace'),
          decoration:
              const InputDecoration(isDense: true, suffixText: 's'),
          onChanged: (v) => onChanged(int.tryParse(v) ?? seconds),
        ),
        TextButton.icon(
          onPressed: onUseCurrent,
          icon: const Icon(Icons.flag_rounded, size: 14),
          label:
              const Text('Use current', style: TextStyle(fontSize: 11)),
          style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              minimumSize: const Size(0, 30)),
        ),
      ]),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// CROP

class CropPage extends StatefulWidget {
  const CropPage({super.key});
  @override
  State<CropPage> createState() => _CropPageState();
}

class _CropPreset {
  const _CropPreset(this.label, this.ratio);
  final String label;
  final double? ratio; // null = free / source
}

const _cropPresets = [
  _CropPreset('Source', null),
  _CropPreset('1:1', 1.0),
  _CropPreset('16:9', 16 / 9),
  _CropPreset('9:16', 9 / 16),
  _CropPreset('4:3', 4 / 3),
  _CropPreset('3:4', 3 / 4),
  _CropPreset('21:9', 21 / 9),
];

class _CropPageState extends State<CropPage> {
  String? _input;
  VideoPlayerController? _vp;
  int _srcW = 0, _srcH = 0;
  _CropPreset _preset = _cropPresets[1];
  bool _busy = false;
  double _pct = 0;
  String _status = 'Pick a video';

  @override
  void dispose() {
    _vp?.dispose();
    super.dispose();
  }

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.video);
    if (r == null) return;
    _vp?.dispose();
    final c = VideoPlayerController.file(File(r.files.single.path!));
    await c.initialize();
    c.setVolume(0);
    c.play();
    c.setLooping(true);
    setState(() {
      _input = r.files.single.path;
      _vp = c;
      _srcW = c.value.size.width.toInt();
      _srcH = c.value.size.height.toInt();
      _status = '${_srcW}x${_srcH}';
    });
  }

  // Compute crop W,H,X,Y from preset ratio centered on source.
  List<int> _computeCrop() {
    if (_srcW == 0 || _srcH == 0) return [0, 0, 0, 0];
    final r = _preset.ratio;
    if (r == null) return [_srcW, _srcH, 0, 0];
    int w, h;
    if (_srcW / _srcH > r) {
      // source wider → crop width
      h = _srcH;
      w = (h * r).toInt();
    } else {
      w = _srcW;
      h = (w / r).toInt();
    }
    // even dimensions for x264
    w -= w % 2;
    h -= h % 2;
    final x = (_srcW - w) ~/ 2;
    final y = (_srcH - h) ~/ 2;
    return [w, h, x, y];
  }

  Future<void> _run() async {
    if (_input == null) return;
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    final c = _computeCrop();
    final outDir = '/storage/emulated/0/Movies/Videl';
    await Directory(outDir).create(recursive: true);
    final out = p.join(outDir,
        '${p.basenameWithoutExtension(_input!)}_crop.mp4');
    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Cropping ${c[0]}x${c[1]}...';
    });
    await PythonRunner.fgStart();
    String s = 'success';
    try {
      final dur = await FfmpegRunner.duration(_input!);
      await FfmpegRunner.run(
        '-y -i "$_input" -vf "crop=${c[0]}:${c[1]}:${c[2]}:${c[3]}" -c:a copy "$out"',
        durationSec: dur,
        onProgress: (pp) {
          if (!mounted) return;
          setState(() => _pct = pp);
          PythonRunner.fgUpdate(
              title: 'Crop', text: 'Cropping', pct: pp.toInt());
        },
      );
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      s = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
          tool: 'crop',
          input: _input!,
          output: s == 'success' ? out : '',
          status: s));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final crop = _computeCrop();
    return Scaffold(
      appBar: AppBar(title: const Text('Crop')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Preview
          AspectRatio(
            aspectRatio: _vp?.value.aspectRatio ?? 16 / 9,
            child: Container(
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              clipBehavior: Clip.hardEdge,
              child: _vp == null
                  ? const Center(
                      child: Icon(Icons.movie_outlined,
                          size: 64, color: VidelColors.border))
                  : Stack(children: [
                      VideoPlayer(_vp!),
                      // Crop overlay
                      LayoutBuilder(builder: (ctx, box) {
                        if (_srcW == 0) return const SizedBox();
                        final r = _preset.ratio;
                        if (r == null) return const SizedBox();
                        final boxRatio = _vp!.value.aspectRatio;
                        double w, h;
                        if (boxRatio > r) {
                          h = box.maxHeight;
                          w = h * r;
                        } else {
                          w = box.maxWidth;
                          h = w / r;
                        }
                        return Center(
                          child: Container(
                            width: w,
                            height: h,
                            decoration: BoxDecoration(
                              border: Border.all(
                                  color: VidelColors.accent, width: 2),
                            ),
                          ),
                        );
                      }),
                    ]),
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _pick,
            icon: const Icon(Icons.video_file_outlined),
            label: Text(_input == null
                ? 'Pick video'
                : p.basename(_input!)),
          ),
          const SizedBox(height: 12),
          const Text('Aspect ratio',
              style: TextStyle(
                  color: VidelColors.textSecondary,
                  fontSize: 12,
                  letterSpacing: 1.2,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _cropPresets
                .map((pr) => ChoiceChip(
                      label: Text(pr.label),
                      selected: _preset == pr,
                      selectedColor: VidelColors.accent.withOpacity(0.3),
                      onSelected: (_) => setState(() => _preset = pr),
                    ))
                .toList(),
          ),
          if (_input != null) ...[
            const SizedBox(height: 10),
            Text(
                'Output ${crop[0]}×${crop[1]} from ${_srcW}×${_srcH}',
                style: const TextStyle(
                    color: VidelColors.textMuted, fontSize: 11)),
          ],
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _input == null) ? null : _run,
            icon: const Icon(Icons.crop_rounded),
            label: const Text('Crop'),
          ),
          const SizedBox(height: 12),
          if (_busy)
            LinearProgressIndicator(value: _pct == 0 ? null : _pct / 100),
          const SizedBox(height: 6),
          Text(_status,
              style: const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// CONVERT FORMAT

// ── Convert format tables ─────────────────────────────────────────────────────

const _cvtVideoFmts = ['mp4', 'mkv', 'mov', 'webm', 'avi'];
const _cvtAudioFmts = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'];
const _cvtImageFmts = ['jpg', 'png', 'bmp', 'gif'];

const _cvtVideoExts = {
  'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv', 'ts', 'm4v'
};
const _cvtAudioExts = {
  'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'opus', 'wma'
};
const _cvtImageExts = {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp'};

String _cvtDetectType(String path) {
  final ext = p.extension(path).toLowerCase().replaceFirst('.', '');
  if (_cvtVideoExts.contains(ext)) return 'video';
  if (_cvtAudioExts.contains(ext)) return 'audio';
  if (_cvtImageExts.contains(ext)) return 'image';
  return 'unknown';
}

/// Build FFmpeg command for audio/video conversion.
String _cvtFfmpegCmd(String input, String output, String targetFmt) {
  final isWebm = targetFmt == 'webm';
  final isAudioOut = _cvtAudioFmts.contains(targetFmt);
  final srcIsVideo = _cvtVideoExts.contains(
    p.extension(input).toLowerCase().replaceFirst('.', ''),
  );
  if (isWebm) {
    return '-y -i "$input" -c:v libvpx-vp9 -c:a libopus "$output"';
  }
  if (srcIsVideo && isAudioOut) {
    return '-y -i "$input" -vn "$output"';
  }
  return '-y -i "$input" -c copy "$output"';
}

class ConvertPage extends StatefulWidget {
  const ConvertPage({super.key});
  @override
  State<ConvertPage> createState() => _ConvertPageState();
}

class _ConvertPageState extends State<ConvertPage> {
  String? _input;
  String _mediaType = 'unknown';
  String _target = '';
  bool _busy = false;
  double _pct = 0;
  String _status = 'Pick a file to begin';

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.any);
    if (r == null) return;
    final path = r.files.first.path!;
    final mt = _cvtDetectType(path);
    String defaultTarget = '';
    if (mt == 'video') defaultTarget = 'mp4';
    if (mt == 'audio') defaultTarget = 'mp3';
    if (mt == 'image') defaultTarget = 'jpg';
    setState(() {
      _input = path;
      _mediaType = mt;
      _target = defaultTarget;
      _status = p.basename(path);
    });
  }

  Future<void> _run() async {
    if (_input == null || _target.isEmpty) return;
    if (_mediaType == 'unknown') {
      setState(() => _status = 'Unsupported file type');
      return;
    }
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }

    final base = p.basenameWithoutExtension(_input!);
    final String outDir;
    if (_mediaType == 'video') {
      outDir = '/storage/emulated/0/Movies/Videl';
    } else if (_mediaType == 'audio') {
      outDir = '/storage/emulated/0/Music/Videl';
    } else {
      outDir = '/storage/emulated/0/Pictures/Videl';
    }
    await Directory(outDir).create(recursive: true);
    final out = p.join(outDir, '${base}_$_target.$_target');

    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Converting...';
    });
    await PythonRunner.fgStart();
    String jobStatus = 'success';
    try {
      if (_mediaType == 'image') {
        await _convertImage(_input!, out, _target);
      } else {
        final cmd = _cvtFfmpegCmd(_input!, out, _target);
        final dur = await FfmpegRunner.duration(_input!);
        await FfmpegRunner.run(cmd, durationSec: dur, onProgress: (prog) {
          if (!mounted) return;
          setState(() => _pct = prog);
          PythonRunner.fgUpdate(title: 'Convert', text: 'Converting', pct: prog.toInt());
        });
      }
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      jobStatus = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
        tool: 'convert',
        input: _input!,
        output: jobStatus == 'success' ? out : '',
        status: jobStatus,
      ));
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _convertImage(String src, String out, String fmt) async {
    final bytes = await File(src).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) throw Exception('Could not decode image');
    final List<int> encoded;
    switch (fmt) {
      case 'jpg':
        encoded = img.encodeJpg(decoded, quality: 92);
        break;
      case 'png':
        encoded = img.encodePng(decoded);
        break;
      case 'gif':
        encoded = img.encodeGif(decoded);
        break;
      case 'bmp':
        encoded = img.encodeBmp(decoded);
        break;
      default:
        encoded = img.encodeJpg(decoded, quality: 92);
    }
    await File(out).writeAsBytes(encoded);
  }

  List<String> get _formats {
    if (_mediaType == 'video') return _cvtVideoFmts;
    if (_mediaType == 'audio') return _cvtAudioFmts;
    if (_mediaType == 'image') return _cvtImageFmts;
    return [];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Convert')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Hero
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: [
                VidelColors.accent.withOpacity(0.15),
                VidelColors.surface,
              ]),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: VidelColors.border),
            ),
            child: Row(children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                      colors: [VidelColors.accent, VidelColors.accentPressed]),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.swap_horiz_rounded, size: 26, color: Colors.white),
              ),
              const SizedBox(width: 14),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Convert',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                Text(
                  _mediaType == 'unknown' ? 'video · audio · image' : _mediaType,
                  style: const TextStyle(
                      fontSize: 12, color: VidelColors.textSecondary),
                ),
              ]),
            ]),
          ),
          const SizedBox(height: 16),
          // File picker
          InkWell(
            onTap: _busy ? null : _pick,
            borderRadius: BorderRadius.circular(14),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: _input == null
                      ? VidelColors.border
                      : VidelColors.accent.withOpacity(0.5),
                  width: _input == null ? 1 : 1.5,
                ),
              ),
              child: Row(children: [
                const Icon(Icons.attach_file_rounded,
                    color: VidelColors.accent, size: 22),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _input == null ? 'Tap to pick file' : p.basename(_input!),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w500),
                  ),
                ),
              ]),
            ),
          ),
          // Format chips (shown only after file picked)
          if (_formats.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Output format',
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: VidelColors.textSecondary,
                          letterSpacing: 0.8)),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _formats
                        .map((e) => ChoiceChip(
                              label: Text(e.toUpperCase()),
                              selected: _target == e,
                              selectedColor: VidelColors.accent.withOpacity(0.3),
                              onSelected: _busy
                                  ? null
                                  : (_) => setState(() => _target = e),
                            ))
                        .toList(),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _input == null || _target.isEmpty) ? null : _run,
            icon: const Icon(Icons.swap_horiz_rounded),
            label: const Text('Convert'),
          ),
          const SizedBox(height: 14),
          if (_busy)
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                minHeight: 6,
                value: (_mediaType == 'image' || _pct == 0) ? null : _pct / 100,
              ),
            ),
          const SizedBox(height: 8),
          Text(_status,
              style: const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// MERGE / CONCAT

class MergePage extends StatefulWidget {
  const MergePage({super.key});
  @override
  State<MergePage> createState() => _MergePageState();
}

class _MergePageState extends State<MergePage> {
  List<String> _inputs = [];
  String _status = 'Pick 2+ videos';
  double _pct = 0;
  bool _busy = false;

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(
        type: FileType.video, allowMultiple: true);
    if (r == null) return;
    setState(() {
      _inputs = r.files.map((f) => f.path!).toList();
      _status = '${_inputs.length} videos';
    });
  }

  Future<void> _merge() async {
    if (_inputs.length < 2) return;
    final outDir = '/storage/emulated/0/Movies/Videl';
    await Directory(outDir).create(recursive: true);
    final listPath = p.join(
        (await Directory.systemTemp.createTemp('merge')).path, 'list.txt');
    await File(listPath).writeAsString(
        _inputs.map((f) => "file '${f.replaceAll("'", r"'\''")}'").join('\n'));
    final out = p.join(outDir,
        'merged_${DateTime.now().millisecondsSinceEpoch}.mp4');
    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Merging...';
    });
    await PythonRunner.fgStart();
    String s = 'success';
    try {
      await FfmpegRunner.run(
        '-y -f concat -safe 0 -i "$listPath" -c copy "$out"',
      );
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      s = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
          tool: 'merge',
          input: _inputs.join(' | '),
          output: s == 'success' ? out : '',
          status: s));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Merge')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          OutlinedButton.icon(
            onPressed: _pick,
            icon: const Icon(Icons.video_library_outlined),
            label: Text(_inputs.isEmpty
                ? 'Pick 2+ videos'
                : '${_inputs.length} selected'),
          ),
          if (_inputs.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              constraints: const BoxConstraints(maxHeight: 200),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: VidelColors.border),
              ),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _inputs.length,
                itemBuilder: (_, i) => ListTile(
                  dense: true,
                  leading: CircleAvatar(
                      radius: 12,
                      backgroundColor: VidelColors.accent,
                      child: Text('${i + 1}',
                          style: const TextStyle(fontSize: 11))),
                  title: Text(p.basename(_inputs[i]),
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _inputs.length < 2) ? null : _merge,
            icon: const Icon(Icons.merge_rounded),
            label: const Text('Merge'),
          ),
          const SizedBox(height: 12),
          if (_busy) LinearProgressIndicator(value: _pct == 0 ? null : _pct / 100),
          const SizedBox(height: 6),
          Text(_status,
              style: const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// MUTE

class MutePage extends StatelessWidget {
  const MutePage({super.key});
  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Mute',
      icon: Icons.volume_off_rounded,
      toolKey: 'mute',
      outputExt: 'mp4',
      outputDir: 'Movies/Videl',
      suffix: '_muted',
      buildCommand: (i, o) => '-y -i "$i" -c:v copy -an "$o"',
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// EXTRACT AUDIO

class ExtractAudioPage extends StatefulWidget {
  const ExtractAudioPage({super.key});
  @override
  State<ExtractAudioPage> createState() => _ExtractAudioPageState();
}

class _ExtractAudioPageState extends State<ExtractAudioPage> {
  String _fmt = 'mp3';
  static const _fmts = ['mp3', 'm4a', 'aac', 'flac', 'wav', 'ogg'];

  String _ffmpegCmd(String i, String o) => '-y -i "$i" -vn "$o"';

  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Extract Audio',
      icon: Icons.audio_file_rounded,
      toolKey: 'extract_audio',
      outputExt: _fmt,
      outputDir: 'Music/Videl',
      suffix: '_audio',
      buildCommand: _ffmpegCmd,
      paramsBuilder: (ctx) => Wrap(
        spacing: 8,
        children: _fmts
            .map((e) => ChoiceChip(
                  label: Text(e.toUpperCase()),
                  selected: _fmt == e,
                  selectedColor: VidelColors.accent.withOpacity(0.3),
                  onSelected: (_) => setState(() => _fmt = e),
                ))
            .toList(),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// GIF CREATOR

class GifPage extends StatefulWidget {
  const GifPage({super.key});
  @override
  State<GifPage> createState() => _GifPageState();
}

class _GifPageState extends State<GifPage> {
  String? _input;
  Duration _pos = Duration.zero;
  int _fps = 12, _w = 480, _start = 0, _len = 5;
  bool _busy = false;
  double _pct = 0;
  String _status = 'Pick a video';

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.video);
    if (r == null) return;
    setState(() {
      _input = r.files.single.path;
      _status = p.basename(_input!);
    });
  }

  Future<void> _run() async {
    if (_input == null) return;
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    final outDir = '/storage/emulated/0/DCIM/Videl';
    await Directory(outDir).create(recursive: true);
    final out =
        p.join(outDir, '${p.basenameWithoutExtension(_input!)}.gif');
    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Encoding GIF...';
    });
    await PythonRunner.fgStart();
    String s = 'success';
    try {
      await FfmpegRunner.run(
        '-y -ss $_start -t $_len -i "$_input" -vf "fps=$_fps,scale=$_w:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" "$out"',
        durationSec: _len.toDouble(),
        onProgress: (pp) {
          if (!mounted) return;
          setState(() => _pct = pp);
          PythonRunner.fgUpdate(title: 'GIF', text: 'Encoding', pct: pp.toInt());
        },
      );
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      s = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
          tool: 'gif',
          input: _input!,
          output: s == 'success' ? out : '',
          status: s));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cur = _pos.inSeconds;
    return Scaffold(
      appBar: AppBar(title: const Text('GIF')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (_input == null)
            Container(
              height: 180,
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              child: const Center(
                child: Icon(Icons.movie_outlined,
                    size: 64, color: VidelColors.border),
              ),
            )
          else
            VidelScrubber(
              path: _input!,
              onPositionChanged: (d) => setState(() => _pos = d),
            ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _pick,
            icon: const Icon(Icons.video_file_outlined),
            label: Text(_input == null ? 'Pick video' : 'Change video'),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: _TimeCard(
                label: 'Start',
                seconds: _start,
                onUseCurrent: _input == null
                    ? null
                    : () => setState(() => _start = cur),
                onChanged: (v) => setState(() => _start = v),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _TimeCard(
                label: 'Length',
                seconds: _len,
                onUseCurrent: null,
                onChanged: (v) => setState(() => _len = v),
              ),
            ),
          ]),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: VidelColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: VidelColors.border),
            ),
            child: Column(children: [
              Row(children: [
                const SizedBox(width: 40, child: Text('FPS')),
                Expanded(
                  child: Slider(
                    value: _fps.toDouble(),
                    min: 5,
                    max: 30,
                    divisions: 25,
                    label: '$_fps',
                    onChanged: (v) => setState(() => _fps = v.toInt()),
                  ),
                ),
                SizedBox(width: 30, child: Text('$_fps', textAlign: TextAlign.end)),
              ]),
              Row(children: [
                const SizedBox(width: 40, child: Text('W')),
                Expanded(
                  child: Slider(
                    value: _w.toDouble(),
                    min: 160,
                    max: 720,
                    divisions: 28,
                    label: '$_w',
                    onChanged: (v) => setState(() => _w = v.toInt()),
                  ),
                ),
                SizedBox(width: 40, child: Text('$_w', textAlign: TextAlign.end)),
              ]),
            ]),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _input == null) ? null : _run,
            icon: const Icon(Icons.gif_box_rounded),
            label: const Text('Create GIF'),
          ),
          const SizedBox(height: 12),
          if (_busy) LinearProgressIndicator(value: _pct == 0 ? null : _pct / 100),
          const SizedBox(height: 6),
          Text(_status,
              style: const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// FRAME GRAB

class FrameGrabPage extends StatefulWidget {
  const FrameGrabPage({super.key});
  @override
  State<FrameGrabPage> createState() => _FrameGrabPageState();
}

class _FrameGrabPageState extends State<FrameGrabPage> {
  String? _input;
  Duration _pos = Duration.zero;
  int _t = 0;
  bool _busy = false;
  String _status = 'Pick a video, then scrub';

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.video);
    if (r == null) return;
    setState(() {
      _input = r.files.single.path;
      _status = p.basename(_input!);
    });
  }

  Future<void> _run() async {
    if (_input == null) return;
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    final outDir = '/storage/emulated/0/DCIM/Videl';
    await Directory(outDir).create(recursive: true);
    final out = p.join(outDir,
        '${p.basenameWithoutExtension(_input!)}_frame${_t}s.jpg');
    setState(() {
      _busy = true;
      _status = 'Grabbing frame at ${_t}s...';
    });
    String s = 'success';
    try {
      await FfmpegRunner.run(
          '-y -ss $_t -i "$_input" -frames:v 1 -q:v 2 "$out"');
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${p.basename(out)}');
    } catch (e) {
      s = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await RecentJobs.add(RecentJob(
          tool: 'frame_grab',
          input: _input!,
          output: s == 'success' ? out : '',
          status: s));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cur = _pos.inSeconds;
    return Scaffold(
      appBar: AppBar(title: const Text('Frame Grab')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (_input == null)
            Container(
              height: 180,
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              child: const Center(
                child: Icon(Icons.movie_outlined,
                    size: 64, color: VidelColors.border),
              ),
            )
          else
            VidelScrubber(
              path: _input!,
              onPositionChanged: (d) => setState(() => _pos = d),
            ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _pick,
            icon: const Icon(Icons.video_file_outlined),
            label: Text(_input == null ? 'Pick video' : 'Change video'),
          ),
          const SizedBox(height: 12),
          _TimeCard(
            label: 'Timestamp',
            seconds: _t,
            onUseCurrent: _input == null
                ? null
                : () => setState(() => _t = cur),
            onChanged: (v) => setState(() => _t = v),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _input == null) ? null : _run,
            icon: const Icon(Icons.camera_alt_rounded),
            label: const Text('Grab frame'),
          ),
          const SizedBox(height: 12),
          Text(_status,
              style: const TextStyle(color: VidelColors.textSecondary)),
        ]),
      ),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// HEX PALETTE

class PalettePage extends StatefulWidget {
  const PalettePage({super.key});
  @override
  State<PalettePage> createState() => _PalettePageState();
}

class _PalettePageState extends State<PalettePage> {
  List<int> _colors = [];
  String? _imgPath;
  bool _busy = false;
  int _k = 6;

  Future<void> _pickThenExtract() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.image);
    if (r == null) return;
    setState(() => _imgPath = r.files.single.path);
    await _extract();
  }

  Future<void> _extract() async {
    if (_imgPath == null) return;
    setState(() => _busy = true);
    final bytes = await File(_imgPath!).readAsBytes();
    final src = img.decodeImage(bytes)!;
    final small = img.copyResize(src, width: 100, height: 100);
    final pts = <List<int>>[];
    for (var y = 0; y < small.height; y++) {
      for (var x = 0; x < small.width; x++) {
        final px = small.getPixel(x, y);
        pts.add([px.r.toInt(), px.g.toInt(), px.b.toInt()]);
      }
    }
    final pal = _kmeans(pts, _k, 12);
    setState(() {
      _colors = pal
          .map((c) => (0xFF << 24) | (c[0] << 16) | (c[1] << 8) | c[2])
          .toList();
      _busy = false;
    });
    await RecentJobs.add(RecentJob(
        tool: 'palette',
        input: _imgPath!,
        output: _colors.map(_hex).join(','),
        status: 'success'));
  }

  List<List<int>> _kmeans(List<List<int>> pts, int k, int iters) {
    final rng = math.Random(0);
    var centroids =
        List.generate(k, (_) => pts[rng.nextInt(pts.length)]);
    for (var it = 0; it < iters; it++) {
      final groups = List.generate(k, (_) => <List<int>>[]);
      for (final pp in pts) {
        var best = 0;
        var bd = 1 << 30;
        for (var i = 0; i < k; i++) {
          final c = centroids[i];
          final d = (pp[0] - c[0]) * (pp[0] - c[0]) +
              (pp[1] - c[1]) * (pp[1] - c[1]) +
              (pp[2] - c[2]) * (pp[2] - c[2]);
          if (d < bd) {
            bd = d;
            best = i;
          }
        }
        groups[best].add(pp);
      }
      centroids = groups.map((g) {
        if (g.isEmpty) return pts[rng.nextInt(pts.length)];
        var r = 0, gg = 0, b = 0;
        for (final p in g) {
          r += p[0];
          gg += p[1];
          b += p[2];
        }
        return [r ~/ g.length, gg ~/ g.length, b ~/ g.length];
      }).toList();
    }
    return centroids;
  }

  String _hex(int c) =>
      '#${c.toRadixString(16).padLeft(8, '0').substring(2).toUpperCase()}';

  Color _picked = const Color(0xFF3B82F6);

  String _wheelHex() =>
      '#${_picked.value.toRadixString(16).padLeft(8, '0').substring(2).toUpperCase()}';

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Hex Palette'),
          bottom: const TabBar(tabs: [
            Tab(icon: Icon(Icons.image_search_rounded), text: 'From image'),
            Tab(icon: Icon(Icons.color_lens_rounded), text: 'Color wheel'),
          ]),
        ),
        body: TabBarView(children: [
          _fromImageTab(),
          _wheelTab(),
        ]),
      ),
    );
  }

  Widget _wheelTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: VidelColors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: VidelColors.border),
          ),
          child: ColorPicker(
            pickerColor: _picked,
            onColorChanged: (c) => setState(() => _picked = c),
            paletteType: PaletteType.hueWheel,
            enableAlpha: false,
            labelTypes: const [],
            displayThumbColor: true,
            pickerAreaBorderRadius: BorderRadius.circular(12),
          ),
        ),
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            color: VidelColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: VidelColors.border),
          ),
          child: ListTile(
            leading: Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: _picked,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: VidelColors.border),
              ),
            ),
            title: Text(_wheelHex(),
                style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 16,
                    fontWeight: FontWeight.w700)),
            trailing: IconButton(
              icon: const Icon(Icons.copy_rounded),
              onPressed: () =>
                  Clipboard.setData(ClipboardData(text: _wheelHex())),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _fromImageTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ElevatedButton.icon(
            onPressed: _busy ? null : _pickThenExtract,
            icon: const Icon(Icons.image_search_rounded),
            label: const Text('Pick image'),
          ),
          if (_imgPath != null) ...[
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(File(_imgPath!),
                  height: 180, fit: BoxFit.cover),
            ),
          ],
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: VidelColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: VidelColors.border),
            ),
            child: Row(children: [
              const Text('Colors',
                  style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(width: 8),
              Text('$_k',
                  style: const TextStyle(
                      color: VidelColors.accent,
                      fontWeight: FontWeight.w700)),
              Expanded(
                child: Slider(
                  value: _k.toDouble(),
                  min: 2,
                  max: 12,
                  divisions: 10,
                  label: '$_k',
                  onChanged: (v) => setState(() => _k = v.toInt()),
                  onChangeEnd: (_) => _extract(),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 12),
          for (final c in _colors)
            Container(
              margin: const EdgeInsets.symmetric(vertical: 3),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: VidelColors.border),
              ),
              child: ListTile(
                dense: true,
                leading: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: Color(c),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: VidelColors.border),
                  ),
                ),
                title: Text(_hex(c),
                    style:
                        const TextStyle(fontFamily: 'monospace', fontSize: 14)),
                trailing: IconButton(
                  icon: const Icon(Icons.copy_rounded, size: 18),
                  onPressed: () =>
                      Clipboard.setData(ClipboardData(text: _hex(c))),
                ),
              ),
            ),
        ]),
    );
  }
}

// ────────────────────────────────────────────────────────────────────────
// Reusable

class _NumRow extends StatelessWidget {
  const _NumRow(
      {required this.label, required this.value, required this.onChanged});
  final String label;
  final int value;
  final ValueChanged<int> onChanged;
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      SizedBox(width: 80, child: Text(label)),
      Expanded(
        child: TextFormField(
          initialValue: '$value',
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(isDense: true),
          onChanged: (v) => onChanged(int.tryParse(v) ?? value),
        ),
      ),
    ]);
  }
}
