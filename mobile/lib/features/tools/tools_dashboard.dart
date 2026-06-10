import 'package:flutter/material.dart';

import '../../core/theme/videl_theme.dart';
import '../downloader/downloader_page.dart';
import 'tool_pages.dart';

class _Tool {
  const _Tool(this.icon, this.title, this.subtitle, this.builder, this.color);
  final IconData icon;
  final String title;
  final String subtitle;
  final WidgetBuilder builder;
  final Color color;
}

final _tools = <_Tool>[
  _Tool(Icons.cloud_download_rounded, 'Downloader', 'yt-dlp · video & MP3',
      (_) => const DownloaderPage(), VidelColors.accent),
  _Tool(Icons.content_cut_rounded, 'Trim', 'video & audio · cut start / end',
      (_) => const TrimPage(), const Color(0xFFEAB308)),
  _Tool(Icons.crop_rounded, 'Crop', 'rectangle crop',
      (_) => const CropPage(), const Color(0xFFEC4899)),
  _Tool(Icons.swap_horiz_rounded, 'Convert', 'video · audio · image',
      (_) => const ConvertPage(), const Color(0xFF06B6D4)),
  _Tool(Icons.merge_rounded, 'Merge', 'concat videos',
      (_) => const MergePage(), const Color(0xFFA855F7)),
  _Tool(Icons.volume_off_rounded, 'Mute', 'strip audio',
      (_) => const MutePage(), const Color(0xFF8B5CF6)),
  _Tool(Icons.gif_box_rounded, 'GIF', 'video → gif',
      (_) => const GifPage(), const Color(0xFFF97316)),
  _Tool(Icons.image_outlined, 'Frame Grab', 'video → still png',
      (_) => const FrameGrabPage(), const Color(0xFF14B8A6)),
  _Tool(Icons.palette_rounded, 'Hex Palette', 'k-means dominant colors',
      (_) => const PalettePage(), const Color(0xFFEF4444)),
];

class ToolsDashboard extends StatelessWidget {
  const ToolsDashboard({super.key});

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 0.95,
      ),
      itemCount: _tools.length,
      itemBuilder: (ctx, i) {
        final t = _tools[i];
        return _ToolCard(tool: t);
      },
    );
  }
}

class _ToolCard extends StatelessWidget {
  const _ToolCard({required this.tool});
  final _Tool tool;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: VidelColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: VidelColors.border),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => Navigator.push(
              context, MaterialPageRoute(builder: tool.builder)),
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: tool.color.withOpacity(0.18),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: tool.color.withOpacity(0.4)),
                  ),
                  child: Icon(tool.icon, color: tool.color, size: 22),
                ),
                const SizedBox(height: 8),
                Text(tool.title,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w700)),
                Text(tool.subtitle,
                    maxLines: 2,
                    style: const TextStyle(
                        color: VidelColors.textSecondary, fontSize: 11)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
