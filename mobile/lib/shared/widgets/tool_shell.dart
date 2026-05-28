import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:permission_handler/permission_handler.dart';

import '../../core/native_bridges/ffmpeg_runner.dart';
import '../../core/native_bridges/python_runner.dart';
import '../../core/recent_jobs.dart';
import '../../core/theme/videl_theme.dart';

typedef CommandBuilder = String Function(String input, String output);

class ToolShell extends StatefulWidget {
  const ToolShell({
    super.key,
    required this.title,
    required this.icon,
    required this.toolKey,
    required this.outputExt,
    required this.outputDir, // e.g. 'Movies/Videl' or 'Pictures/Videl'
    required this.buildCommand,
    this.allowMulti = false,
    this.fileType = FileType.video,
    this.paramsBuilder,
    this.suffix = '',
  });

  final String title;
  final IconData icon;
  final String toolKey;
  final String outputExt; // e.g. 'mp4', 'gif', 'mp3'
  final String outputDir; // relative under /storage/emulated/0/
  final CommandBuilder buildCommand;
  final bool allowMulti;
  final FileType fileType;
  final Widget Function(BuildContext)? paramsBuilder;
  final String suffix; // appended to output basename, e.g. '_trim'

  @override
  State<ToolShell> createState() => _ToolShellState();
}

class _ToolShellState extends State<ToolShell> {
  List<String> _inputs = [];
  bool _busy = false;
  double _pct = 0;
  String _status = 'Pick a file to begin';
  String? _outPath;

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final r = await Permission.manageExternalStorage.request();
    if (r.isGranted) return true;
    if (r.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(
      type: widget.fileType,
      allowMultiple: widget.allowMulti,
    );
    if (r == null) return;
    setState(() {
      _inputs = r.files.map((f) => f.path!).toList();
      _status = widget.allowMulti
          ? '${_inputs.length} files'
          : p.basename(_inputs.first);
    });
  }

  Future<void> _run() async {
    if (_inputs.isEmpty) return;
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    await PythonRunner.fgStart();
    final input = _inputs.first;
    final outDir = '/storage/emulated/0/${widget.outputDir}';
    await Directory(outDir).create(recursive: true);
    final base = p.basenameWithoutExtension(input);
    final out = p.join(outDir, '$base${widget.suffix}.${widget.outputExt}');
    final cmd = widget.buildCommand(_inputs.join(';'), out);

    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Processing...';
      _outPath = null;
    });

    String jobStatus = 'success';
    try {
      final dur = await FfmpegRunner.duration(input);
      await FfmpegRunner.run(cmd, durationSec: dur, onProgress: (p) {
        if (!mounted) return;
        setState(() => _pct = p);
        PythonRunner.fgUpdate(
            title: widget.title, text: 'Processing', pct: p.toInt());
      });
      await PythonRunner.mediaScan(out);
      setState(() {
        _outPath = out;
        _status = 'Saved · ${p.basename(out)}';
      });
    } catch (e) {
      jobStatus = 'failed';
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      await RecentJobs.add(RecentJob(
        tool: widget.toolKey,
        input: _inputs.join(' | '),
        output: jobStatus == 'success' ? (_outPath ?? '') : '',
        status: jobStatus,
      ));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _Hero(icon: widget.icon, title: widget.title),
          const SizedBox(height: 16),
          _PickerCard(
            inputs: _inputs,
            onPick: _pick,
            multi: widget.allowMulti,
          ),
          if (widget.paramsBuilder != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VidelColors.border),
              ),
              child: widget.paramsBuilder!(context),
            ),
          ],
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: (_busy || _inputs.isEmpty) ? null : _run,
            icon: const Icon(Icons.play_arrow_rounded),
            label: const Text('Run'),
          ),
          const SizedBox(height: 14),
          if (_busy)
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                minHeight: 6,
                value: _pct == 0 ? null : _pct / 100,
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

class _Hero extends StatelessWidget {
  const _Hero({required this.icon, required this.title});
  final IconData icon;
  final String title;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            VidelColors.accent.withOpacity(0.15),
            VidelColors.surface,
          ],
        ),
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
          child: Icon(icon, size: 26, color: Colors.white),
        ),
        const SizedBox(width: 14),
        Text(title,
            style:
                const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _PickerCard extends StatelessWidget {
  const _PickerCard(
      {required this.inputs, required this.onPick, required this.multi});
  final List<String> inputs;
  final VoidCallback onPick;
  final bool multi;
  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPick,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: VidelColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: inputs.isEmpty
                  ? VidelColors.border
                  : VidelColors.accent.withOpacity(0.5),
              width: inputs.isEmpty ? 1 : 1.5),
        ),
        child: Row(children: [
          const Icon(Icons.attach_file_rounded,
              color: VidelColors.accent, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              inputs.isEmpty
                  ? (multi ? 'Tap to pick files' : 'Tap to pick file')
                  : (multi
                      ? '${inputs.length} files selected'
                      : inputs.first.split('/').last),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
        ]),
      ),
    );
  }
}
