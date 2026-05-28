import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/native_bridges/ffmpeg_runner.dart';
import '../../core/native_bridges/python_runner.dart';
import '../../core/theme/videl_theme.dart';

enum _Filter { video, audio }

class DownloaderPage extends StatefulWidget {
  const DownloaderPage({super.key, this.initialUrl, this.autoFetch = false});
  final String? initialUrl;
  final bool autoFetch;

  @override
  State<DownloaderPage> createState() => _DownloaderPageState();
}

class _DownloaderPageState extends State<DownloaderPage>
    with SingleTickerProviderStateMixin {
  late final TextEditingController _urlCtrl;
  late final TabController _tab;
  _Filter _filter = _Filter.video;
  String _status = 'Paste a URL to begin';
  double _pct = 0;
  bool _busy = false;
  String _title = '';
  int _duration = 0;
  List<Map<String, dynamic>> _formats = [];

  @override
  void initState() {
    super.initState();
    _urlCtrl = TextEditingController(text: widget.initialUrl ?? '');
    _tab = TabController(length: 2, vsync: this);
    _tab.addListener(() {
      if (!mounted) return;
      setState(() => _filter = _tab.index == 0 ? _Filter.video : _Filter.audio);
    });
    PythonRunner.progress().listen((e) {
      if (!mounted) return;
      final pct = (e['pct'] as num?)?.toDouble() ?? 0;
      final speed = e['speed'] ?? '';
      setState(() {
        _pct = pct;
        _status = 'Downloading · $speed';
      });
      PythonRunner.fgUpdate(
          title: _title.isEmpty ? 'Videl' : _title,
          text: 'Downloading · $speed',
          pct: pct.toInt());
    });
    if (widget.autoFetch && (widget.initialUrl ?? '').isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _fetchFormats());
    } else if ((widget.initialUrl ?? '').isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _tryClipboard());
    }
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _tab.dispose();
    super.dispose();
  }

  Future<void> _tryClipboard() async {
    final data = await Clipboard.getData('text/plain');
    final t = data?.text?.trim();
    if (t == null || t.isEmpty || !RegExp(r'^https?://').hasMatch(t)) return;
    if (!mounted) return;
    setState(() {
      _urlCtrl.text = t;
      _status = 'Pasted from clipboard';
    });
  }

  Future<String> _publicDir() async => _filter == _Filter.audio
      ? '/storage/emulated/0/Music/Videl'
      : '/storage/emulated/0/Movies/Videl';

  Future<bool> _ensureStorage() async {
    if (await Permission.manageExternalStorage.isGranted) return true;
    final res = await Permission.manageExternalStorage.request();
    if (res.isGranted) return true;
    if (res.isPermanentlyDenied) await openAppSettings();
    return false;
  }

  Future<void> _ensureNotifications() async {
    if (await Permission.notification.isGranted) return;
    await Permission.notification.request();
  }

  String _fmtSize(num bytes) {
    if (bytes <= 0) return '?';
    const u = ['B', 'KB', 'MB', 'GB'];
    var b = bytes.toDouble();
    var i = 0;
    while (b >= 1024 && i < u.length - 1) {
      b /= 1024;
      i++;
    }
    return '${b.toStringAsFixed(b < 10 ? 1 : 0)}${u[i]}';
  }

  String _fmtDuration(int s) {
    if (s <= 0) return '';
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final sec = s % 60;
    return h > 0
        ? '$h:${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}'
        : '$m:${sec.toString().padLeft(2, '0')}';
  }

  bool _isAudio(Map<String, dynamic> f) =>
      f['vcodec'] == 'none' && f['acodec'] != 'none';
  bool _isVideo(Map<String, dynamic> f) {
    final v = f['vcodec'];
    return v != null && v != '' && v != 'none';
  }
  bool _hasAudio(Map<String, dynamic> f) {
    final a = f['acodec'];
    return a != null && a != '' && a != 'none';
  }

  List<Map<String, dynamic>> _visible() {
    final list = _formats
        .where((f) => _filter == _Filter.audio ? _isAudio(f) : _isVideo(f))
        .toList();
    list.sort((a, b) =>
        ((b['tbr'] ?? 0) as num).compareTo((a['tbr'] ?? 0) as num));
    return list;
  }

  Future<void> _fetchFormats() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _busy = true;
      _status = 'Fetching formats...';
      _formats = [];
    });
    try {
      final res = await PythonRunner.ytdlpFormats(url);
      setState(() {
        _title = res['title'] as String? ?? '';
        _duration = (res['duration'] as num?)?.toInt() ?? 0;
        _formats = List<Map<String, dynamic>>.from(
            (res['formats'] as List).map((e) => Map<String, dynamic>.from(e)));
        _status = 'Pick a format to download';
      });
    } catch (e) {
      setState(() => _status = 'Failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _downloadVideo(Map<String, dynamic>? f) async {
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    await _ensureNotifications();
    await PythonRunner.fgStart();
    final dir = await _publicDir();
    setState(() {
      _busy = true;
      _status = 'Starting...';
      _pct = 0;
    });
    try {
      final url = _urlCtrl.text.trim();
      final videoFmt = f == null ? 'bv*' : '${f['format_id']}';
      if (f != null && _hasAudio(f)) {
        final out = await PythonRunner.ytdlpDownload(
            url: url, outDir: dir, format: videoFmt);
        await PythonRunner.mediaScan(out);
        setState(() => _status = 'Saved · ${out.split('/').last}');
        return;
      }
      setState(() => _status = 'Downloading video + audio...');
      final results = await Future.wait([
        PythonRunner.ytdlpDownload(url: url, outDir: dir, format: videoFmt),
        PythonRunner.ytdlpDownload(
            url: url, outDir: dir, format: 'ba[ext=m4a]/ba'),
      ]);
      final vPath = results[0];
      final aPath = results[1];
      setState(() => _status = 'Merging streams...');
      final merged = await FfmpegRunner.mux(vPath, aPath);
      try { File(vPath).deleteSync(); } catch (_) {}
      try { File(aPath).deleteSync(); } catch (_) {}
      await PythonRunner.mediaScan(merged);
      setState(() => _status = 'Saved · ${merged.split('/').last}');
    } catch (e) {
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _downloadAudio(Map<String, dynamic>? f) async {
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    await _ensureNotifications();
    await PythonRunner.fgStart();
    final dir = await _publicDir();
    setState(() {
      _busy = true;
      _status = 'Starting...';
      _pct = 0;
    });
    try {
      final url = _urlCtrl.text.trim();
      final fmt = f == null ? 'ba' : '${f['format_id']}';
      setState(() => _status = 'Downloading audio...');
      final src = await PythonRunner.ytdlpDownload(
          url: url, outDir: dir, format: fmt);
      setState(() => _status = 'Converting to MP3...');
      final mp3 = await FfmpegRunner.toMp3(src);
      try { File(src).deleteSync(); } catch (_) {}
      await PythonRunner.mediaScan(mp3);
      setState(() => _status = 'Saved · ${mp3.split('/').last}');
    } catch (e) {
      setState(() => _status = 'Failed: $e');
    } finally {
      await PythonRunner.fgStop();
      if (mounted) setState(() => _busy = false);
    }
  }

  void _download(Map<String, dynamic>? f) =>
      _filter == _Filter.audio ? _downloadAudio(f) : _downloadVideo(f);

  String _videoLabel(Map<String, dynamic> f) {
    final res = f['resolution'] ?? '';
    final fps = (f['fps'] ?? 0) > 0 ? ' ${f['fps']}fps' : '';
    return '$res$fps';
  }
  String _audioLabel(Map<String, dynamic> f) {
    final tbr = (f['tbr'] ?? 0).toStringAsFixed(0);
    return '${tbr} kbps → mp3';
  }

  @override
  Widget build(BuildContext context) {
    final list = _visible();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Downloader',
            style: TextStyle(fontWeight: FontWeight.w600)),
        actions: [
          IconButton(
            icon: const Icon(Icons.paste_rounded),
            tooltip: 'Paste from clipboard',
            onPressed: _tryClipboard,
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // URL hero card
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
            child: Container(
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: VidelColors.border),
              ),
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _urlCtrl,
                    decoration: const InputDecoration(
                      hintText: 'https://...',
                      prefixIcon: Icon(Icons.link_rounded),
                      isDense: true,
                    ),
                    keyboardType: TextInputType.url,
                    textInputAction: TextInputAction.search,
                    onSubmitted: (_) => _fetchFormats(),
                  ),
                  const SizedBox(height: 10),
                  Row(children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: _busy ? null : _fetchFormats,
                        icon: const Icon(Icons.search_rounded, size: 18),
                        label: const Text('Fetch formats'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton.icon(
                      onPressed: _busy ? null : () => _download(null),
                      icon: Icon(
                          _filter == _Filter.audio
                              ? Icons.music_note_rounded
                              : Icons.flash_on_rounded,
                          size: 18,
                          color: VidelColors.accent),
                      label: Text(_filter == _Filter.audio
                          ? 'Best MP3'
                          : 'Best video'),
                    ),
                  ]),
                ],
              ),
            ),
          ),

          // Status strip
          _StatusStrip(status: _status, pct: _pct, busy: _busy),

          // Video info card
          if (_title.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: VidelColors.raised,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: VidelColors.border),
                ),
                child: Row(children: [
                  const Icon(Icons.movie_outlined,
                      size: 18, color: VidelColors.accent),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(_title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600, fontSize: 13)),
                  ),
                  if (_duration > 0)
                    Text(_fmtDuration(_duration),
                        style: const TextStyle(
                            color: VidelColors.textSecondary, fontSize: 12)),
                ]),
              ),
            ),

          // Tabs
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Container(
              decoration: BoxDecoration(
                color: VidelColors.raised,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: VidelColors.border),
              ),
              child: TabBar(
                controller: _tab,
                splashFactory: NoSplash.splashFactory,
                indicator: BoxDecoration(
                  color: VidelColors.accent.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                      color: VidelColors.accent.withOpacity(0.4), width: 1),
                ),
                indicatorSize: TabBarIndicatorSize.tab,
                indicatorPadding: const EdgeInsets.all(4),
                dividerColor: Colors.transparent,
                tabs: const [
                  Tab(
                    height: 42,
                    icon: Icon(Icons.movie_rounded, size: 18),
                    iconMargin: EdgeInsets.zero,
                    child: Text('Video',
                        style: TextStyle(fontSize: 13)),
                  ),
                  Tab(
                    height: 42,
                    icon: Icon(Icons.audiotrack_rounded, size: 18),
                    iconMargin: EdgeInsets.zero,
                    child: Text('Audio (MP3)',
                        style: TextStyle(fontSize: 13)),
                  ),
                ],
              ),
            ),
          ),

          // Format list
          Expanded(
            child: list.isEmpty
                ? _EmptyState(busy: _busy)
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                    itemCount: list.length,
                    itemBuilder: (ctx, i) {
                      final f = list[i];
                      final isAudio = _filter == _Filter.audio;
                      return _FormatRow(
                        label: isAudio ? _audioLabel(f) : _videoLabel(f),
                        ext: '${f['ext'] ?? ''}',
                        size: _fmtSize(f['filesize'] ?? 0),
                        codec: '${f['vcodec'] ?? ''}'.split('.').first,
                        isAudio: isAudio,
                        needsMerge: !isAudio && !_hasAudio(f),
                        onTap: _busy ? null : () => _download(f),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _StatusStrip extends StatelessWidget {
  const _StatusStrip(
      {required this.status, required this.pct, required this.busy});
  final String status;
  final double pct;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            minHeight: 4,
            value: !busy ? 0 : (pct == 0 ? null : pct / 100),
          ),
        ),
        const SizedBox(height: 6),
        Row(children: [
          Icon(busy ? Icons.sync_rounded : Icons.info_outline_rounded,
              size: 13, color: VidelColors.textSecondary),
          const SizedBox(width: 6),
          Expanded(
            child: Text(status,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: VidelColors.textSecondary, fontSize: 12)),
          ),
          if (busy && pct > 0)
            Text('${pct.toStringAsFixed(0)}%',
                style: const TextStyle(
                    color: VidelColors.accent,
                    fontSize: 12,
                    fontWeight: FontWeight.w600)),
        ]),
      ]),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.busy});
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            busy ? Icons.hourglass_top_rounded : Icons.cloud_download_outlined,
            size: 56,
            color: VidelColors.border,
          ),
          const SizedBox(height: 12),
          Text(
            busy ? 'Working...' : 'No formats yet',
            style: const TextStyle(
                color: VidelColors.textSecondary, fontSize: 14),
          ),
          const SizedBox(height: 4),
          const Text(
            'Paste URL above, tap Fetch formats',
            style: TextStyle(color: VidelColors.textMuted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _FormatRow extends StatelessWidget {
  const _FormatRow({
    required this.label,
    required this.ext,
    required this.size,
    required this.codec,
    required this.isAudio,
    required this.needsMerge,
    required this.onTap,
  });
  final String label;
  final String ext;
  final String size;
  final String codec;
  final bool isAudio;
  final bool needsMerge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: VidelColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: VidelColors.border),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: VidelColors.raised,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                      color: VidelColors.accent.withOpacity(0.3)),
                ),
                child: Icon(
                  isAudio
                      ? Icons.audiotrack_rounded
                      : Icons.movie_rounded,
                  size: 18,
                  color: VidelColors.accent,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Flexible(
                        child: Text(label,
                            style: const TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 14)),
                      ),
                      const SizedBox(width: 8),
                      _Pill(text: ext.toUpperCase()),
                      if (needsMerge) ...[
                        const SizedBox(width: 6),
                        const _Pill(
                            text: '+AUDIO',
                            color: VidelColors.warning),
                      ],
                    ]),
                    const SizedBox(height: 4),
                    Text('$codec · $size',
                        style: const TextStyle(
                            color: VidelColors.textSecondary, fontSize: 11)),
                  ],
                ),
              ),
              const Icon(Icons.download_rounded,
                  size: 22, color: VidelColors.accent),
            ]),
          ),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.text, this.color = VidelColors.accent});
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 9, fontWeight: FontWeight.w700)),
    );
  }
}
