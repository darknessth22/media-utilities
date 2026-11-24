import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// The web app's palette (web/css/app.css tokens), so the phone, the website and
// the desktop app look like one product. Names are kept from the earlier
// desktop-based palette so every screen picks the new values up.
class VidelColors {
  static const bg = Color(0xFF05070F);          // --ink
  static const sidebar = Color(0xFF0B1224);     // drawer, sheets
  static const surface = Color(0xFF0F172A);     // --panel-solid: cards
  static const raised = Color(0xFF131C33);      // --panel-2: inputs, chips
  static const border = Color(0xFF1E2D45);      // --line
  static const accent = Color(0xFF3B7BFF);      // --ribbon
  static const accentHover = Color(0xFF2563EB); // --ribbon-deep
  static const accentPressed = Color(0xFF1D4ED8);
  static const accentLight = Color(0xFF9DBBFF); // --ribbon-light: focus, links
  static const glowBlue = Color(0xFF1D4ED8);    // --glow-a
  static const glowViolet = Color(0xFF7C3AED);  // --glow-b
  static const textPrimary = Color(0xFFE7ECF5); // --paper
  static const textSecondary = Color(0xFFA3AFC6); // --muted
  static const textMuted = Color(0xFF6B7894);
  static const success = Color(0xFF5FD3A2);     // --ok
  static const error = Color(0xFFFF7A85);       // --danger
  static const warning = Color(0xFFFFB547);     // --amber
}

// Headings use the website's display face; body text uses Inter, the closest
// match to the site's Geist that google_fonts ships.
TextStyle videlDisplay({double size = 22, FontWeight weight = FontWeight.w700, Color? color}) =>
    GoogleFonts.bricolageGrotesque(
        fontSize: size, fontWeight: weight, color: color ?? VidelColors.textPrimary, letterSpacing: -0.3);

const videlBackgroundGradient = LinearGradient(
  begin: Alignment.topCenter,
  end: Alignment.bottomCenter,
  colors: [Color(0xFF070B18), VidelColors.bg],
);

// The website's backdrop: near-black ink, a blue glow top left, a violet glow
// bottom right, and a faint grid that fades out. Static, so it costs nothing
// while scrolling.
class VidelBackdrop extends StatelessWidget {
  const VidelBackdrop({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(gradient: videlBackgroundGradient),
      child: Stack(children: [
        const Positioned.fill(child: _Glow(alignment: Alignment(-1.1, -1.0), color: VidelColors.glowBlue, opacity: 0.32)),
        const Positioned.fill(child: _Glow(alignment: Alignment(1.2, 0.9), color: VidelColors.glowViolet, opacity: 0.22)),
        const Positioned.fill(child: CustomPaint(painter: _GridPainter())),
        child,
      ]),
    );
  }
}

class _Glow extends StatelessWidget {
  const _Glow({required this.alignment, required this.color, required this.opacity});
  final Alignment alignment;
  final Color color;
  final double opacity;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: alignment,
              radius: 0.9,
              colors: [color.withValues(alpha: opacity), color.withValues(alpha: 0)],
            ),
          ),
        ),
      );
}

class _GridPainter extends CustomPainter {
  const _GridPainter();

  @override
  void paint(Canvas canvas, Size size) {
    const step = 56.0;
    // Fades from the top, like the site's masked grid.
    final paint = Paint()
      ..strokeWidth = 1
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Colors.white.withValues(alpha: 0.045), Colors.white.withValues(alpha: 0)],
        stops: const [0, 0.7],
      ).createShader(Offset.zero & size);
    for (var x = 0.0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (var y = 0.0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

ThemeData buildVidelTheme() {
  final base = ThemeData.dark(useMaterial3: true);
  final body = GoogleFonts.interTextTheme(base.textTheme);
  final display = GoogleFonts.bricolageGrotesqueTextTheme(base.textTheme);
  const pill = StadiumBorder();
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    colorScheme: const ColorScheme.dark(
      surface: VidelColors.surface,
      surfaceContainerHighest: VidelColors.raised,
      primary: VidelColors.accent,
      secondary: VidelColors.accentHover,
      tertiary: VidelColors.glowViolet,
      error: VidelColors.error,
      onSurface: VidelColors.textPrimary,
      onSurfaceVariant: VidelColors.textSecondary,
      onPrimary: Colors.white,
      outline: VidelColors.border,
      outlineVariant: VidelColors.border,
    ),
    textTheme: body
        .copyWith(
          displayLarge: display.displayLarge,
          displayMedium: display.displayMedium,
          displaySmall: display.displaySmall,
          headlineLarge: display.headlineLarge,
          headlineMedium: display.headlineMedium,
          headlineSmall: display.headlineSmall,
          titleLarge: display.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        )
        .apply(bodyColor: VidelColors.textPrimary, displayColor: VidelColors.textPrimary),
    cardTheme: CardThemeData(
      color: VidelColors.surface.withValues(alpha: 0.82),
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 5),
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: VidelColors.border),
        borderRadius: BorderRadius.circular(16),
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: VidelColors.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: videlDisplay(size: 20),
    ),
    drawerTheme: const DrawerThemeData(backgroundColor: VidelColors.sidebar, surfaceTintColor: Colors.transparent),
    dialogTheme: DialogThemeData(
      backgroundColor: VidelColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: VidelColors.border),
      ),
      titleTextStyle: videlDisplay(size: 19),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: VidelColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: VidelColors.raised,
      contentTextStyle: const TextStyle(color: VidelColors.textPrimary),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: VidelColors.border),
      ),
    ),
    dividerTheme: const DividerThemeData(color: VidelColors.border, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: VidelColors.raised,
      hintStyle: const TextStyle(color: VidelColors.textMuted),
      labelStyle: const TextStyle(color: VidelColors.textSecondary),
      prefixIconColor: VidelColors.textSecondary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.accentLight, width: 1.5),
      ),
    ),
    // Buttons and choices are pills, as on the website.
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: VidelColors.accent,
        foregroundColor: Colors.white,
        disabledBackgroundColor: VidelColors.raised,
        disabledForegroundColor: VidelColors.textMuted,
        elevation: 0,
        shadowColor: VidelColors.accent,
        shape: pill,
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: VidelColors.accent,
        foregroundColor: Colors.white,
        shape: pill,
        minimumSize: const Size(0, 48),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: VidelColors.textPrimary,
        side: const BorderSide(color: VidelColors.border),
        shape: pill,
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: VidelColors.accentLight, shape: pill),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: Colors.transparent,
      selectedColor: VidelColors.accent,
      disabledColor: VidelColors.raised,
      side: const BorderSide(color: VidelColors.border),
      shape: pill,
      labelStyle: const TextStyle(color: VidelColors.textPrimary, fontWeight: FontWeight.w500),
      secondaryLabelStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
      checkmarkColor: Colors.white,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        shape: const WidgetStatePropertyAll(pill),
        side: const WidgetStatePropertyAll(BorderSide(color: VidelColors.border)),
        backgroundColor: WidgetStateProperty.resolveWith(
            (s) => s.contains(WidgetState.selected) ? VidelColors.accent : Colors.transparent),
        foregroundColor: WidgetStateProperty.resolveWith(
            (s) => s.contains(WidgetState.selected) ? Colors.white : VidelColors.textPrimary),
      ),
    ),
    sliderTheme: const SliderThemeData(
      activeTrackColor: VidelColors.accent,
      inactiveTrackColor: VidelColors.raised,
      thumbColor: Colors.white,
      overlayColor: Color(0x333B7BFF),
    ),
    switchTheme: SwitchThemeData(
      trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? VidelColors.accent : VidelColors.raised),
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackOutlineColor: const WidgetStatePropertyAll(VidelColors.border),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: VidelColors.accent,
      linearTrackColor: VidelColors.raised,
    ),
    // Tabs look like the website's segmented choices: the active one is a filled pill.
    tabBarTheme: TabBarThemeData(
      labelColor: Colors.white,
      unselectedLabelColor: VidelColors.textSecondary,
      indicator: BoxDecoration(color: VidelColors.accent, borderRadius: BorderRadius.circular(999)),
      indicatorSize: TabBarIndicatorSize.tab,
      dividerColor: Colors.transparent,
      labelStyle: const TextStyle(fontWeight: FontWeight.w700),
      // No splashBorderRadius here: TabBarThemeData in Flutter 3.27 (CI) lacks it.
    ),
    listTileTheme: const ListTileThemeData(iconColor: VidelColors.textSecondary),
  );
}
