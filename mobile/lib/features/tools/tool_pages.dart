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

class TrimPage extends StatefulWidget {
  const TrimPage({super.key});
  @override
  State<TrimPage> createState() => _TrimPageState();
}

class _TrimPageState extends State<TrimPage> {
  String? _input;
  Duration _pos = Duration.zero;
  int _start = 0, _end = 60;
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
    final outDir = '/storage/emulated/0/Movies/Videl';
    await Directory(outDir).create(recursive: true);
    final out =
        p.join(outDir, '${p.basenameWithoutExtension(_input!)}_trim.mp4');
    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Trimming...';
    });
    await PythonRunner.fgStart();
    String s = 'success';
    try {
      final dur = (_end - _start).clamp(1, 99999).toDouble();
      await FfmpegRunner.run(
        '-y -ss $_start -to $_end -i "$_input" -c copy "$out"',
        durationSec: dur,
        onProgress: (pp) {
          if (!mounted) return;
          setState(() => _pct = pp);
          PythonRunner.fgUpdate(title: 'Trim', text: 'Trimming', pct: pp.toInt());
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
          tool: 'trim',
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
      appBar: AppBar(title: const Text('Trim')),
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
                label: 'End',
                seconds: _end,
                onUseCurrent: _input == null
                    ? null
                    : () => setState(() => _end = cur),
                onChanged: (v) => setState(() => _end = v),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          Text('Length: ${_hms((_end - _start).clamp(0, 99999))}',
              style: const TextStyle(
                  color: VidelColors.textSecondary, fontSize: 12)),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _input == null) ? null : _run,
            icon: const Icon(Icons.content_cut_rounded),
            label: const Text('Trim'),
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

class _TimeCard extends StatelessWidget {
  const _TimeCard(
      {required this.label,
      required this.seconds,
      required this.onUseCurrent,
      required this.onChanged});
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
          decoration: const InputDecoration(
              isDense: true, suffixText: 's'),
          onChanged: (v) => onChanged(int.tryParse(v) ?? seconds),
        ),
        TextButton.icon(
          onPressed: onUseCurrent,
          icon: const Icon(Icons.flag_rounded, size: 14),
          label: const Text('Use current', style: TextStyle(fontSize: 11)),
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

class ConvertPage extends StatefulWidget {
  const ConvertPage({super.key});
  @override
  State<ConvertPage> createState() => _ConvertPageState();
}

class _ConvertPageState extends State<ConvertPage> {
  String _target = 'mp4';
  static const _exts = ['mp4', 'mov', 'mkv', 'webm'];

  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Convert',
      icon: Icons.swap_horiz_rounded,
      toolKey: 'convert',
      outputExt: _target,
      outputDir: 'Movies/Videl',
      suffix: '_$_target',
      buildCommand: (i, o) => _target == 'webm'
          ? '-y -i "$i" -c:v libvpx-vp9 -c:a libopus "$o"'
          : '-y -i "$i" -c copy "$o"',
      paramsBuilder: (ctx) => Wrap(
        spacing: 8,
        children: _exts
            .map((e) => ChoiceChip(
                  label: Text(e.toUpperCase()),
                  selected: _target == e,
                  selectedColor: VidelColors.accent.withOpacity(0.3),
                  onSelected: (_) => setState(() => _target = e),
                ))
            .toList(),
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
