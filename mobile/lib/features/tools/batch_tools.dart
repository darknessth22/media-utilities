// Compress, Metadata Scrubber and Watermark: free for one file, and Pro (or a
// free daily run) for a batch, through ToolShell(batch: true).
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../../core/theme/videl_theme.dart';
import '../../shared/widgets/tool_shell.dart';

const _imageExts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'};
bool _isImage(String path) => _imageExts.contains(p.extension(path).toLowerCase());

Widget _chips<T>(List<(T, String)> items, T value, ValueChanged<T> onPick) => Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final (v, label) in items)
          ChoiceChip(
            label: Text(label),
            selected: value == v,
            selectedColor: VidelColors.accent.withOpacity(0.3),
            onSelected: (_) => onPick(v),
          ),
      ],
    );

// ── COMPRESS ────────────────────────────────────────────────────────────────

class CompressPage extends StatefulWidget {
  const CompressPage({super.key});
  @override
  State<CompressPage> createState() => _CompressPageState();
}

class _CompressPageState extends State<CompressPage> {
  // x264 CRF: higher is smaller.
  int _crf = 28;

  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Compress',
      icon: Icons.compress_rounded,
      toolKey: 'compress',
      outputExt: 'mp4',
      outputDir: 'Movies/Videl',
      suffix: '_compressed',
      batch: true,
      buildCommand: (i, o) => '-y -i "$i" -c:v libx264 -crf $_crf -preset veryfast '
          '-c:a aac -b:a 128k -movflags +faststart "$o"',
      paramsBuilder: (ctx) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('How much smaller', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        _chips<int>(const [(23, 'A little'), (28, 'Balanced'), (32, 'A lot')], _crf,
            (v) => setState(() => _crf = v)),
      ]),
    );
  }
}

// ── METADATA SCRUBBER ───────────────────────────────────────────────────────

class ScrubPage extends StatelessWidget {
  const ScrubPage({super.key});

  // Videos and audio keep their streams untouched; a photo is re-encoded,
  // because its EXIF (GPS, camera, date) sits inside the image data.
  static String _cmd(String i, String o) => _isImage(i)
      ? '-y -i "$i" -map_metadata -1 -q:v 2 "$o"'
      : '-y -i "$i" -map 0 -map_metadata -1 -map_chapters -1 -c copy "$o"';

  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Metadata Scrubber',
      icon: Icons.privacy_tip_rounded,
      toolKey: 'scrub',
      outputExt: '',
      outputDir: 'Download/Videl',
      suffix: '_clean',
      batch: true,
      fileType: FileType.media,
      buildCommand: _cmd,
      paramsBuilder: (ctx) => const Text(
        'Removes location, dates, camera and other hidden details. The picture and sound stay the same.',
        style: TextStyle(color: VidelColors.textSecondary),
      ),
    );
  }
}

// ── WATERMARK ───────────────────────────────────────────────────────────────

class WatermarkPage extends StatefulWidget {
  const WatermarkPage({super.key});
  @override
  State<WatermarkPage> createState() => _WatermarkPageState();
}

class _WatermarkPageState extends State<WatermarkPage> {
  final _text = TextEditingController(text: '© ');
  String _corner = 'br';

  static const _pos = {
    'br': 'x=w-tw-h/30:y=h-th-h/30',
    'bl': 'x=h/30:y=h-th-h/30',
    'tr': 'x=w-tw-h/30:y=h/30',
    'tl': 'x=h/30:y=h/30',
    'c': 'x=(w-tw)/2:y=(h-th)/2',
  };

  // The text sits in single quotes inside the -vf "..." argument: quotes would
  // end it early (curly ones look the same), a backslash is dropped, and % is
  // escaped for drawtext's own %{...} expansion.
  static String _esc(String s) => s
      .replaceAll(r'\', '')
      .replaceAll("'", '’')
      .replaceAll('"', '”')
      .replaceAll('%', r'\%');

  String _cmd(String i, String o) {
    final draw = "drawtext=fontfile=/system/fonts/Roboto-Regular.ttf:text='${_esc(_text.text.trim())}'"
        ':fontcolor=white@0.85:fontsize=h/18:borderw=2:bordercolor=black@0.45:${_pos[_corner]}';
    return _isImage(i)
        ? '-y -i "$i" -vf "$draw" -q:v 2 "$o"'
        : '-y -i "$i" -vf "$draw" -c:v libx264 -crf 22 -preset veryfast -c:a copy "$o"';
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ToolShell(
      title: 'Watermark',
      icon: Icons.branding_watermark_rounded,
      toolKey: 'watermark',
      outputExt: '',
      outputDir: 'Movies/Videl',
      suffix: '_wm',
      batch: true,
      fileType: FileType.media,
      buildCommand: _cmd,
      paramsBuilder: (ctx) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextField(
          controller: _text,
          decoration: const InputDecoration(labelText: 'Watermark text'),
          maxLength: 60,
        ),
        const Text('Position', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        StatefulBuilder(
          builder: (ctx, set) => _chips<String>(
              const [('br', 'Bottom right'), ('bl', 'Bottom left'), ('tr', 'Top right'),
                ('tl', 'Top left'), ('c', 'Centre')],
              _corner, (v) => set(() => _corner = v)),
        ),
      ]),
    );
  }
}
