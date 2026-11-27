// Compress, Metadata Scrubber and Watermark: each run, one file or a batch of
// several, is one free daily job (or no limit with Pro), through ToolShell(batch: true).
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

// Text or a logo, like the desktop's Batch Watermark (core/watermarker.py).
// Sizes follow the picture, so a phone-sized and a 4K file look alike: text is
// a share of the shorter side, a logo a share of the width (the desktop's 15%
// default). Expressions that hold a comma are in single quotes, which FFmpeg
// reads as one value inside the filter.
class _WatermarkPageState extends State<WatermarkPage> {
  final _text = TextEditingController(text: '© ');
  bool _logoMode = false;
  String? _logo;
  String _corner = 'br';
  double _textSize = 4;     // % of the shorter side
  double _logoSize = 15;    // % of the width
  double _opacity = 80;     // %
  bool _white = true;

  // x, y for drawtext (w, h, tw, th) and for overlay (W, H, w, h).
  static const _textPos = {
    'br': ("w-tw-min(w,h)/30", "h-th-min(w,h)/30"),
    'bl': ("min(w,h)/30", "h-th-min(w,h)/30"),
    'tr': ("w-tw-min(w,h)/30", "min(w,h)/30"),
    'tl': ("min(w,h)/30", "min(w,h)/30"),
    'c': ("(w-tw)/2", "(h-th)/2"),
  };
  static const _logoPos = {
    'br': ("W-w-min(W,H)/30", "H-h-min(W,H)/30"),
    'bl': ("min(W,H)/30", "H-h-min(W,H)/30"),
    'tr': ("W-w-min(W,H)/30", "min(W,H)/30"),
    'tl': ("min(W,H)/30", "min(W,H)/30"),
    'c': ("(W-w)/2", "(H-h)/2"),
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
    final a = (_opacity / 100).toStringAsFixed(2);
    final String args;
    if (_logoMode) {
      final (x, y) = _logoPos[_corner]!;
      // scale2ref: iw is the picture's width, mdar the logo's shape. The logo is
      // looped so every video frame has it; shortest=1 ends with the video.
      final fc = "[1:v][0:v]scale2ref=w='iw*${(_logoSize / 100).toStringAsFixed(3)}':h='ow/mdar'[wm][base];"
          "[wm]format=rgba,colorchannelmixer=aa=$a[wm2];[base][wm2]overlay=x='$x':y='$y':shortest=1";
      args = '-y -i "$i" -loop 1 -i "$_logo" -filter_complex "$fc"';
    } else {
      final (x, y) = _textPos[_corner]!;
      final ink = _white ? 'white' : 'black';
      final edge = _white ? 'black' : 'white';
      final draw = "drawtext=fontfile=/system/fonts/Roboto-Regular.ttf:text='${_esc(_text.text.trim())}'"
          ":fontcolor=$ink@$a:fontsize='min(w,h)*${(_textSize / 100).toStringAsFixed(3)}'"
          ":borderw=2:bordercolor=$edge@${(_opacity / 250).toStringAsFixed(2)}:x='$x':y='$y'";
      args = '-y -i "$i" -vf "$draw"';
    }
    return _isImage(i)
        ? '$args -frames:v 1 -q:v 2 "$o"'
        : '$args -c:v libx264 -crf 22 -preset veryfast -c:a copy "$o"';
  }

  String? _check() {
    if (_logoMode && _logo == null) return 'Pick a logo image first.';
    if (!_logoMode && _text.text.trim().isEmpty) return 'Type the watermark text first.';
    return null;
  }

  Future<void> _pickLogo(void Function(void Function()) set) async {
    final r = await FilePicker.platform.pickFiles(type: FileType.image);
    final path = r?.files.single.path;
    if (path != null) set(() => _logo = path);
  }

  Widget _slider(String label, double value, double min, double max, String unit,
          ValueChanged<double> onChanged) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SizedBox(height: 12),
        Text('$label: ${value.round()}$unit', style: const TextStyle(fontWeight: FontWeight.w600)),
        Slider(value: value, min: min, max: max, divisions: (max - min).round(), onChanged: onChanged),
      ]);

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
      validate: _check,
      paramsBuilder: (ctx) => StatefulBuilder(
        builder: (ctx, set) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _chips<bool>(const [(false, 'Text'), (true, 'Logo')], _logoMode, (v) => set(() => _logoMode = v)),
          const SizedBox(height: 12),
          if (_logoMode) ...[
            OutlinedButton.icon(
              onPressed: () => _pickLogo(set),
              icon: const Icon(Icons.image_rounded, size: 18),
              label: Text(_logo == null ? 'Pick a logo (PNG with a clear background works best)' : p.basename(_logo!),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
            _slider('Logo size', _logoSize, 5, 50, '% of the width', (v) => set(() => _logoSize = v)),
          ] else ...[
            TextField(
              controller: _text,
              decoration: const InputDecoration(labelText: 'Watermark text'),
              maxLength: 60,
            ),
            _slider('Text size', _textSize, 2, 12, '%', (v) => set(() => _textSize = v)),
            const Text('Colour', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            _chips<bool>(const [(true, 'White'), (false, 'Black')], _white, (v) => set(() => _white = v)),
          ],
          _slider('Opacity', _opacity, 10, 100, '%', (v) => set(() => _opacity = v)),
          const Text('Position', style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          _chips<String>(
              const [('br', 'Bottom right'), ('bl', 'Bottom left'), ('tr', 'Top right'),
                ('tl', 'Top left'), ('c', 'Centre')],
              _corner, (v) => set(() => _corner = v)),
        ]),
      ),
    );
  }
}
