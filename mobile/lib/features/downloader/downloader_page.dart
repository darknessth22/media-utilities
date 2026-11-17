import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:permission_handler/permission_handler.dart';
import 'package:video_player/video_player.dart';

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
  int _duration = 0; // seconds
  String _streamUrl = ''; // direct stream URL for preview
  List<Map<String, dynamic>> _formats = [];
  // Songs of a Spotify link (videl_dl.spotify_tracks): each one is found on
  // YouTube and saved as a tagged MP3, like the desktop app does.
  List<Map<String, dynamic>> _spotify = [];
  String _songLabel = ''; // "Song 2 of 12" while a Spotify list downloads

  // Time range
  bool _useRange = false;
  double _rangeStart = 0;
  double _rangeEnd = 0;

  // Preview player
  VideoPlayerController? _previewCtrl;
  bool _previewLoading = false;

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
        _status = _songLabel.isEmpty ? 'Downloading · $speed' : '$_songLabel · $speed';
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
    _previewCtrl?.dispose();
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

  String _fmtSec(double s) {
    final total = s.toInt();
    final h = total ~/ 3600;
    final m = (total % 3600) ~/ 60;
    final sec = total % 60;
    return h > 0
        ? '$h:${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}'
        : '$m:${sec.toString().padLeft(2, '0')}';
  }

  bool _isAudio(Map<String, dynamic> f) =>
      f['vcodec'] == 'none' && f['acodec'] != 'none';
  // A missing codec means "unknown", not "absent": X labels none of its MP4s,
  // which already carry sound. Only an explicit 'none' rules a stream out.
  bool _isVideo(Map<String, dynamic> f) => f['vcodec'] != 'none';
  bool _hasAudio(Map<String, dynamic> f) => f['acodec'] != 'none';

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
      _spotify = [];
      _useRange = false;
      _previewCtrl?.dispose();
      _previewCtrl = null;
    });
    try {
      final res = await PythonRunner.ytdlpFormats(url);
      final dur = (res['duration'] as num?)?.toInt() ?? 0;
      setState(() {
        _title = res['title'] as String? ?? '';
        _duration = dur;
        _streamUrl = res['stream_url'] as String? ?? '';
        _rangeStart = 0;
        _rangeEnd = dur.toDouble();
        _formats = List<Map<String, dynamic>>.from(
            (res['formats'] as List).map((e) => Map<String, dynamic>.from(e)));
        _spotify = _songsFrom(res);
        _status = _spotify.isEmpty
            ? 'Pick a format to download'
            : '${_spotify.length} song${_spotify.length == 1 ? '' : 's'} from Spotify. Tap Best MP3 to save ${_spotify.length == 1 ? 'it' : 'them'}.';
      });
      if (_spotify.isNotEmpty) _tab.animateTo(1);
    } catch (e) {
      _showError(e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadPreview() async {
    if (_streamUrl.isEmpty) {
      setState(() => _status = 'No stream URL available for preview');
      return;
    }
    setState(() => _previewLoading = true);
    try {
      _previewCtrl?.dispose();
      _previewCtrl = null;
      final ctrl = VideoPlayerController.networkUrl(
        Uri.parse(_streamUrl),
        httpHeaders: {'User-Agent': 'Mozilla/5.0'},
      );
      await ctrl.initialize();
      ctrl.setVolume(1.0);
      ctrl.addListener(() {
        if (mounted) setState(() {});
      });
      setState(() {
        _previewCtrl = ctrl;
        _previewLoading = false;
      });
    } catch (e) {
      setState(() {
        _previewLoading = false;
        _status = 'Preview failed: stream URL may have expired';
      });
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
      String out;
      if (f != null && _hasAudio(f)) {
        out = await PythonRunner.ytdlpDownload(
            url: url, outDir: dir, format: videoFmt);
      } else {
        setState(() => _status = 'Downloading video + audio...');
        final results = await Future.wait([
          PythonRunner.ytdlpDownload(url: url, outDir: dir, format: videoFmt),
          PythonRunner.ytdlpDownload(url: url, outDir: dir, format: 'ba[ext=m4a]/ba'),
        ]);
        final vPath = results[0];
        final aPath = results[1];
        // Only a video-only part ("….video.<ext>", see videl_dl.py) needs the audio.
        // Otherwise the video already has sound: no audio stream at all (most X
        // posts), or the best video was a file with sound built in.
        final videoOnly = vPath.contains(RegExp(r'\.video\.[^./\\]+$'));
        if (aPath.isEmpty || !videoOnly) {
          out = vPath;
          if (aPath.isNotEmpty) {
            try { File(aPath).deleteSync(); } catch (_) {}
          }
        } else {
          setState(() => _status = 'Merging streams...');
          out = await FfmpegRunner.mux(vPath, aPath);
          try { File(vPath).deleteSync(); } catch (_) {}
          try { File(aPath).deleteSync(); } catch (_) {}
        }
      }
      if (_useRange) {
        setState(() => _status = 'Trimming...');
        final trimmed = await FfmpegRunner.trim(out, _rangeStart, _rangeEnd);
        try { File(out).deleteSync(); } catch (_) {}
        out = trimmed;
      }
      await PythonRunner.mediaScan(out);
      setState(() => _status = 'Saved · ${out.split('/').last}');
    } catch (e) {
      _showError(e);
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
      String src = await PythonRunner.ytdlpDownload(
          url: url, outDir: dir, format: fmt);
      if (src.isEmpty) {
        // No audio-only stream (most X posts): take the video, the MP3 step keeps only its sound.
        src = await PythonRunner.ytdlpDownload(url: url, outDir: dir, format: 'b');
      }
      if (_useRange) {
        setState(() => _status = 'Trimming...');
        final trimmed = await FfmpegRunner.trim(src, _rangeStart, _rangeEnd);
        try { File(src).deleteSync(); } catch (_) {}
        src = trimmed;
      }
      setState(() => _status = 'Converting to MP3...');
      final mp3 = await FfmpegRunner.toMp3(src);
      try { File(src).deleteSync(); } catch (_) {}
      await PythonRunner.mediaScan(mp3);
      setState(() => _status = 'Saved · ${mp3.split('/').last}');
    } catch (e) {
      _showError(e);
    } finally {
      await PythonRunner.fgStop();
      if (mounted) setState(() => _busy = false);
    }
  }

  void _download(Map<String, dynamic>? f) {
    if (_isSpotify(_urlCtrl.text)) {
      _downloadSpotify();
    } else if (_filter == _Filter.audio) {
      _downloadAudio(f);
    } else {
      _downloadVideo(f);
    }
  }

  bool _isSpotify(String url) => url.contains('open.spotify.com/');

  List<Map<String, dynamic>> _songsFrom(Map<String, dynamic> res) =>
      List<Map<String, dynamic>>.from(((res['spotify'] ?? const []) as List)
          .map((e) => Map<String, dynamic>.from(e)));

  // Spotify can't be downloaded directly (DRM). Each song is found on YouTube
  // ("ytsearch1:Artist - Title", handled by videl_dl.download) and saved as an
  // MP3 named and tagged from Spotify, with the cover art.
  Future<void> _downloadSpotify() async {
    if (!await _ensureStorage()) {
      setState(() => _status = 'Storage permission required');
      return;
    }
    await _ensureNotifications();
    await PythonRunner.fgStart();
    setState(() {
      _busy = true;
      _pct = 0;
      _status = 'Reading the Spotify link...';
    });
    const dir = '/storage/emulated/0/Music/Videl';
    final covers = <String, String>{}; // cover URL -> local file; album songs share one
    final failed = <String>[];
    var saved = 0;
    try {
      var songs = _spotify;
      if (songs.isEmpty) {
        songs = _songsFrom(await PythonRunner.ytdlpFormats(_urlCtrl.text.trim()));
      }
      for (var i = 0; i < songs.length; i++) {
        final s = songs[i];
        final name = s['name'] as String? ?? '';
        _songLabel = songs.length > 1 ? 'Song ${i + 1} of ${songs.length}' : 'Downloading';
        setState(() {
          _pct = 0;
          _status = '$_songLabel: $name';
        });
        try {
          final query = s['query'] as String;
          var src = await PythonRunner.ytdlpDownload(url: query, outDir: dir, format: 'ba');
          if (src.isEmpty) {
            src = await PythonRunner.ytdlpDownload(url: query, outDir: dir, format: 'b');
          }
          final coverUrl = s['cover'] as String? ?? '';
          if (coverUrl.isNotEmpty && !covers.containsKey(coverUrl)) {
            covers[coverUrl] = await _fetchCover(coverUrl, dir);
          }
          setState(() => _status = 'Converting to MP3: $name');
          final mp3 = await FfmpegRunner.toTaggedMp3(
            src,
            fileName: s['file'] as String? ?? name,
            tags: {
              'title': s['title'] as String? ?? '',
              'artist': s['artist'] as String? ?? '',
              'album': s['album'] as String? ?? '',
              'track': (s['track'] ?? 0) == 0 ? '' : '${s['track']}',
            },
            coverPath: covers[coverUrl],
          );
          try { File(src).deleteSync(); } catch (_) {}
          await PythonRunner.mediaScan(mp3);
          saved++;
        } catch (_) {
          failed.add(name);
        }
      }
      setState(() => _status = failed.isEmpty
          ? 'Saved $saved song${saved == 1 ? '' : 's'} to Music/Videl'
          : 'Saved $saved of ${songs.length}. Not found: ${failed.take(3).join(', ')}${failed.length > 3 ? '...' : ''}');
    } catch (e) {
      _showError(e);
    } finally {
      _songLabel = '';
      for (final path in covers.values) {
        if (path.isEmpty) continue;
        try { File(path).deleteSync(); } catch (_) {}
      }
      await PythonRunner.fgStop();
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String> _fetchCover(String url, String dir) async {
    try {
      final r = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return '';
      final f = File('$dir/.cover-${url.hashCode}.jpg');
      await f.writeAsBytes(r.bodyBytes);
      return f.path;
    } catch (_) {
      return ''; // a song without a cover is still worth saving
    }
  }

  void _showError(Object e) {
    final msg = e is PlatformException
        ? 'PlatformException(${e.code})\n\n${e.message ?? ''}\n\n${e.details ?? ''}'
        : e.toString();
    setState(() => _status = 'Failed — tap ⓘ for details');
    if (!mounted) return;
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: VidelColors.surface,
        title: const Row(children: [
          Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 20),
          SizedBox(width: 8),
          Text('Error', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ]),
        content: SizedBox(
          width: double.maxFinite,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                constraints: const BoxConstraints(maxHeight: 300),
                decoration: BoxDecoration(
                  color: VidelColors.raised,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: VidelColors.border),
                ),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(10),
                  child: SelectableText(
                    msg,
                    style: const TextStyle(
                        fontSize: 11,
                        fontFamily: 'monospace',
                        color: VidelColors.textSecondary,
                        height: 1.5),
                  ),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: msg));
              Navigator.pop(context);
              setState(() => _status = 'Error copied to clipboard');
            },
            icon: const Icon(Icons.copy_rounded, size: 15),
            label: const Text('Copy'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  String _videoLabel(Map<String, dynamic> f) {
    final res = f['resolution'] ?? '';
    final fps = (f['fps'] ?? 0) > 0 ? ' ${f['fps']}fps' : '';
    return '$res$fps';
  }
  String _audioLabel(Map<String, dynamic> f) {
    final tbr = (f['tbr'] ?? 0).toStringAsFixed(0);
    return '$tbr kbps → mp3';
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

          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Video info card
                  if (_title.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 10),
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
                                    color: VidelColors.textSecondary,
                                    fontSize: 12)),
                        ]),
                      ),
                    ),

                  // Time range card
                  if (_duration > 0) ...[
                    const SizedBox(height: 10),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Container(
                        decoration: BoxDecoration(
                          color: VidelColors.surface,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: _useRange
                                ? VidelColors.accent.withOpacity(0.5)
                                : VidelColors.border,
                            width: _useRange ? 1.5 : 1,
                          ),
                        ),
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            // Header row
                            Row(children: [
                              const Icon(Icons.content_cut_rounded,
                                  size: 16, color: VidelColors.accent),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text('Time Range',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13)),
                              ),
                              Switch.adaptive(
                                value: _useRange,
                                activeColor: VidelColors.accent,
                                onChanged: _busy
                                    ? null
                                    : (v) => setState(() => _useRange = v),
                              ),
                            ]),

                            if (_useRange) ...[
                              const SizedBox(height: 6),
                              // Range labels
                              Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    _RangeLabel(
                                        icon: Icons.play_arrow_rounded,
                                        label: _fmtSec(_rangeStart)),
                                    _RangeLabel(
                                        icon: Icons.stop_rounded,
                                        label: _fmtSec(_rangeEnd),
                                        isEnd: true),
                                  ]),
                              const SizedBox(height: 2),
                              SliderTheme(
                                data: SliderTheme.of(context).copyWith(
                                  trackHeight: 4,
                                  rangeThumbShape:
                                      const RoundRangeSliderThumbShape(
                                          enabledThumbRadius: 10),
                                  overlayShape:
                                      SliderComponentShape.noOverlay,
                                  activeTrackColor: VidelColors.accent,
                                  inactiveTrackColor:
                                      VidelColors.accent.withOpacity(0.2),
                                  thumbColor: VidelColors.accent,
                                ),
                                child: RangeSlider(
                                  min: 0,
                                  max: _duration.toDouble(),
                                  values: RangeValues(_rangeStart, _rangeEnd),
                                  onChanged: _busy
                                      ? null
                                      : (v) => setState(() {
                                            _rangeStart = v.start;
                                            _rangeEnd = v.end;
                                            // seek preview if loaded
                                            _previewCtrl?.seekTo(Duration(
                                                seconds:
                                                    v.start.toInt()));
                                          }),
                                ),
                              ),
                              // Duration badge
                              Center(
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 10, vertical: 3),
                                  decoration: BoxDecoration(
                                    color:
                                        VidelColors.accent.withOpacity(0.12),
                                    borderRadius: BorderRadius.circular(20),
                                    border: Border.all(
                                        color: VidelColors.accent
                                            .withOpacity(0.3)),
                                  ),
                                  child: Text(
                                    'Clip: ${_fmtSec(_rangeEnd - _rangeStart)}',
                                    style: const TextStyle(
                                        fontSize: 11,
                                        color: VidelColors.accent,
                                        fontWeight: FontWeight.w600),
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],

                  // Preview card (not for Spotify: there is nothing to stream until a song is found)
                  if (_title.isNotEmpty && _spotify.isEmpty) ...[
                    const SizedBox(height: 10),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Container(
                        decoration: BoxDecoration(
                          color: VidelColors.surface,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: VidelColors.border),
                        ),
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(children: [
                              const Icon(Icons.preview_rounded,
                                  size: 16, color: VidelColors.accent),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text('Preview',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13)),
                              ),
                              if (_previewCtrl == null && !_previewLoading)
                                TextButton.icon(
                                  onPressed: _loadPreview,
                                  icon: const Icon(Icons.play_circle_outline,
                                      size: 16),
                                  label: const Text('Load',
                                      style: TextStyle(fontSize: 12)),
                                  style: TextButton.styleFrom(
                                      foregroundColor: VidelColors.accent,
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 10, vertical: 4)),
                                ),
                              if (_previewCtrl != null)
                                GestureDetector(
                                  onTap: () => setState(() {
                                    _previewCtrl!.value.isPlaying
                                        ? _previewCtrl!.pause()
                                        : _previewCtrl!.play();
                                  }),
                                  child: Icon(
                                    _previewCtrl!.value.isPlaying
                                        ? Icons.pause_circle_rounded
                                        : Icons.play_circle_rounded,
                                    size: 28,
                                    color: VidelColors.accent,
                                  ),
                                ),
                            ]),
                            if (_previewLoading) ...[
                              const SizedBox(height: 12),
                              const Center(
                                  child: CircularProgressIndicator()),
                              const SizedBox(height: 12),
                            ],
                            if (_previewCtrl != null) ...[
                              const SizedBox(height: 10),
                              AspectRatio(
                                aspectRatio:
                                    _previewCtrl!.value.aspectRatio,
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(10),
                                  child: VideoPlayer(_previewCtrl!),
                                ),
                              ),
                              const SizedBox(height: 6),
                              // Playback scrubber
                              Row(children: [
                                Text(
                                  _fmtSec(_previewCtrl!
                                      .value.position.inSeconds
                                      .toDouble()),
                                  style: const TextStyle(
                                      fontSize: 10,
                                      color: VidelColors.textSecondary),
                                ),
                                Expanded(
                                  child: SliderTheme(
                                    data: SliderThemeData(
                                        trackHeight: 3,
                                        overlayShape:
                                            SliderComponentShape.noOverlay),
                                    child: Slider(
                                      value: _previewCtrl!.value.duration
                                                  .inMilliseconds ==
                                              0
                                          ? 0
                                          : (_previewCtrl!
                                                      .value
                                                      .position
                                                      .inMilliseconds /
                                                  _previewCtrl!.value
                                                      .duration.inMilliseconds)
                                              .clamp(0.0, 1.0),
                                      onChanged: (v) {
                                        final ms = (v *
                                                _previewCtrl!.value.duration
                                                    .inMilliseconds)
                                            .toInt();
                                        _previewCtrl!.seekTo(
                                            Duration(milliseconds: ms));
                                      },
                                    ),
                                  ),
                                ),
                                Text(
                                  _fmtSec(_previewCtrl!
                                      .value.duration.inSeconds
                                      .toDouble()),
                                  style: const TextStyle(
                                      fontSize: 10,
                                      color: VidelColors.textSecondary),
                                ),
                              ]),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],

                  // Tabs
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 8),
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
                              color: VidelColors.accent.withOpacity(0.4),
                              width: 1),
                        ),
                        indicatorSize: TabBarIndicatorSize.tab,
                        indicatorPadding: const EdgeInsets.all(4),
                        dividerColor: Colors.transparent,
                        tabs: const [
                          Tab(
                            height: 42,
                            icon: Icon(Icons.movie_rounded, size: 18),
                            iconMargin: EdgeInsets.zero,
                            child:
                                Text('Video', style: TextStyle(fontSize: 13)),
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

                  // Format list, or the songs of a Spotify link
                  if (_spotify.isNotEmpty)
                    _SpotifyList(songs: _spotify)
                  else if (list.isEmpty)
                    _EmptyState(busy: _busy)
                  else
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
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
                          useRange: _useRange,
                          rangeLabel: _useRange
                              ? '${_fmtSec(_rangeStart)} – ${_fmtSec(_rangeEnd)}'
                              : null,
                          onTap: _busy ? null : () => _download(f),
                        );
                      },
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RangeLabel extends StatelessWidget {
  const _RangeLabel(
      {required this.icon, required this.label, this.isEnd = false});
  final IconData icon;
  final String label;
  final bool isEnd;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (!isEnd) ...[
          Icon(icon, size: 13, color: VidelColors.textSecondary),
          const SizedBox(width: 3),
        ],
        Text(label,
            style: const TextStyle(
                fontSize: 11,
                color: VidelColors.textSecondary,
                fontWeight: FontWeight.w500)),
        if (isEnd) ...[
          const SizedBox(width: 3),
          Icon(icon, size: 13, color: VidelColors.textSecondary),
        ],
      ],
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

class _SpotifyList extends StatelessWidget {
  const _SpotifyList({required this.songs});
  final List<Map<String, dynamic>> songs;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
      itemCount: songs.length,
      itemBuilder: (ctx, i) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          SizedBox(
            width: 28,
            child: Text('${i + 1}',
                style: const TextStyle(color: VidelColors.textMuted, fontSize: 12)),
          ),
          const Icon(Icons.music_note_rounded, size: 16, color: VidelColors.accent),
          const SizedBox(width: 8),
          Expanded(
            child: Text(songs[i]['name'] as String? ?? '',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13)),
          ),
        ]),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.busy});
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 40),
      child: Center(
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
    required this.useRange,
    required this.onTap,
    this.rangeLabel,
  });
  final String label;
  final String ext;
  final String size;
  final String codec;
  final bool isAudio;
  final bool needsMerge;
  final bool useRange;
  final String? rangeLabel;
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
                    if (useRange && rangeLabel != null) ...[
                      const SizedBox(height: 3),
                      Row(children: [
                        const Icon(Icons.content_cut_rounded,
                            size: 10, color: VidelColors.accent),
                        const SizedBox(width: 4),
                        Text(rangeLabel!,
                            style: const TextStyle(
                                fontSize: 10,
                                color: VidelColors.accent,
                                fontWeight: FontWeight.w500)),
                      ]),
                    ],
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
